"""T097: the head agent, where each person's head is in a comic panel's accepted frame (verify.md
§3, §6, §9). MockTransport, no network."""

import ast
import inspect
import json
import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.comic.job as comic_job
import app.frames.attempt as frames_attempt
import app.frames.check as frames_check
import app.storyboard.build as storyboard_build
from app.frames.model import FrameAuditRow
from app.frames.writer import FrameWriter
from app.grounding import Extraction
from app.llm import NebiusChatModel, Usage
from app.script import Screenplay
from app.shots import Shot
from app.verify import loop
from app.verify.audit import HEAD_AGENT_PROMPT, heads_seen
from app.verify.model import (
    Audit,
    Check,
    CheckResult,
    FrameState,
    HeadSeen,
    RenderedFrame,
    Severity,
    Verdict,
)
from app.verify.schema import FrameDescription, HeadAnswer, HeadCheck
from tests.api.test_read import project
from tests.comic.test_job import make_comic, planned
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit as passed
from tests.verify.conftest import described, kitchen_shot
from tests.verify.test_loop import FakeRenderer, Recorder
from tests.verify.test_t095 import MODELS

TWO = [
    {"position": "left", "appearance": "an older woman in an apron"},
    {"position": "right", "appearance": "a boy in a blazer"},
]


def head(person: int, box: tuple[float, float, float, float], visible: bool = True) -> HeadAnswer:
    x0, y0, x1, y1 = box
    return HeadAnswer(person=person, visible=visible, x0=x0, y0=y0, x1=x1, y1=y1)


# --- heads_seen ---------------------------------------------------------------------------------


def test_a_visible_box_is_kept_with_its_character_in_person_order() -> None:
    answer = HeadCheck(heads=[head(1, (0.6, 0.1, 0.7, 0.3)), head(0, (0.1, 0.2, 0.2, 0.4))])
    assert heads_seen(answer, 2, {0: "NANDI"}) == (
        HeadSeen(0, "NANDI", (0.1, 0.2, 0.2, 0.4)),
        HeadSeen(1, None, (0.6, 0.1, 0.7, 0.3)),  # matched to no one
    )


@pytest.mark.parametrize(
    "answer",
    [
        head(2, (0.1, 0.1, 0.2, 0.2)),  # no such person
        head(-1, (0.1, 0.1, 0.2, 0.2)),
        head(0, (0.1, 0.1, 0.2, 0.2), visible=False),
        head(0, (0.2, 0.1, 0.2, 0.3)),  # x0 = x1
        head(0, (0.3, 0.1, 0.2, 0.3)),  # x0 > x1
        head(0, (0.1, 0.3, 0.2, 0.3)),  # y0 = y1
        head(0, (0.1, 0.4, 0.2, 0.3)),  # y0 > y1
        head(0, (-0.1, 0.1, 0.2, 0.3)),
        head(0, (0.1, -0.1, 0.2, 0.3)),
        head(0, (0.1, 0.1, 1.2, 0.3)),
        head(0, (0.1, 0.1, 0.2, 1.01)),
    ],
)
def test_an_answer_out_of_range_or_hidden_is_dropped(answer: HeadAnswer) -> None:
    assert heads_seen(HeadCheck(heads=[answer]), 2, {}) == ()


def test_the_whole_frame_is_a_box() -> None:
    answer = HeadCheck(heads=[head(0, (0.0, 0.0, 1.0, 1.0))])
    assert heads_seen(answer, 1, {}) == (HeadSeen(0, None, (0.0, 0.0, 1.0, 1.0)),)


def test_only_the_first_answer_for_a_person_counts() -> None:
    first_hidden = HeadCheck(
        heads=[head(0, (0.1, 0.1, 0.2, 0.2), visible=False), head(0, (0.5, 0.5, 0.6, 0.6))]
    )
    assert heads_seen(first_hidden, 1, {}) == ()
    twice = HeadCheck(heads=[head(0, (0.1, 0.1, 0.2, 0.2)), head(0, (0.5, 0.5, 0.6, 0.6))])
    assert heads_seen(twice, 1, {}) == (HeadSeen(0, None, (0.1, 0.1, 0.2, 0.2)),)


# --- render_until_accepted(heads=True) ----------------------------------------------------------


ANSWER = {
    "heads": [
        {"person": 0, "visible": True, "x0": 0.1, "y0": 0.2, "x1": 0.2, "y1": 0.35},
        {"person": 1, "visible": False, "x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
    ]
}


class Heads:
    """The head agent's side of Token Factory: answers `answer`, or fails; counts the questions."""

    def __init__(self, answer: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.answer = ANSWER if answer is None else answer
        self.fail = fail

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert HEAD_AGENT_PROMPT in str(body["messages"][0]["content"])
        self.bodies.append(body)
        if self.fail:
            return httpx2.Response(400, json={"detail": "bad"})
        return httpx2.Response(
            200,
            json={
                "model": body["model"],
                "choices": [
                    {"message": {"content": json.dumps(self.answer)}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1900, "completion_tokens": 500},
            },
        )


FAILED = CheckResult(Check.UNSCRIPTED_PERSON, Severity.HARD, False, "person 1")


def audits_with(
    monkeypatch: pytest.MonkeyPatch,
    verdicts: list[Verdict],
    description: FrameDescription | None = None,
) -> None:
    """audit_frame answers each attempt with the next verdict, on a description of TWO, NANDI
    accepted at 0, after the audit's own 300 + 60 tokens from "describer-model"."""
    answers: Iterator[Verdict] = iter(verdicts)
    seen = described(people=TWO) if description is None else description

    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        verdict = next(answers)
        checks = (FAILED,) if verdict is Verdict.FAIL else ()
        return Audit(
            frame.shot, frame.attempt, frame.seed, seen, None, checks, verdict, {},
            ("describer-model",), Usage(300, 60, 0), matched={0: "NANDI"},
        )  # fmt: skip

    monkeypatch.setattr(loop, "audit_frame", fake)


def model_for(handler: Heads) -> NebiusChatModel:
    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        max_attempts=1,
    )


async def run(
    handler: Heads, screenplay: Screenplay, extraction: Extraction, rec: Recorder, **kw: Any
) -> Any:
    return await loop.render_until_accepted(
        model_for(handler), FakeRenderer(), kitchen_shot(), screenplay, extraction,
        width=640, height=480, log=rec.log, on_state=rec.on_state, **kw,
    )  # fmt: skip


async def test_asked_once_on_the_accepted_attempt_only(
    monkeypatch: pytest.MonkeyPatch, screenplay: Screenplay, extraction: Extraction
) -> None:
    audits_with(monkeypatch, [Verdict.FAIL, Verdict.WARN])
    handler, rec = Heads(), Recorder()
    outcome = await run(handler, screenplay, extraction, rec, heads=True)
    assert outcome.state is FrameState.WARNED
    (call,) = handler.bodies
    assert call["model"] == "vision-model" and call["max_tokens"] == 4096
    text, image = call["messages"][1]["content"]
    assert text["text"] == (
        "People in the drawing:\n"
        "0: left third, an older woman in an apron\n"
        "1: right third, a boy in a blazer"
    )
    assert image["image_url"]["url"] == "data:image/png;base64,cG5n"  # FakeRenderer's b"png"
    failed, accepted = rec.audits
    assert failed.heads == () and failed.usage == Usage(300, 60, 0)
    assert accepted.heads == (HeadSeen(0, "NANDI", (0.1, 0.2, 0.2, 0.35)),)
    assert accepted.usage == Usage(2200, 560, 0)
    assert accepted.models == ("describer-model", "vision-model")
    assert accepted.verdict is Verdict.WARN and accepted.checks == ()
    assert outcome.audits[-1] is accepted


async def test_a_withheld_frame_is_never_asked(
    monkeypatch: pytest.MonkeyPatch, screenplay: Screenplay, extraction: Extraction
) -> None:
    audits_with(monkeypatch, [Verdict.FAIL, Verdict.ERROR])
    handler, rec = Heads(), Recorder()
    outcome = await run(handler, screenplay, extraction, rec, heads=True)
    assert outcome.state is FrameState.WITHHELD
    assert handler.bodies == []


async def test_the_default_never_asks(
    monkeypatch: pytest.MonkeyPatch, screenplay: Screenplay, extraction: Extraction
) -> None:
    audits_with(monkeypatch, [Verdict.PASS])
    handler, rec = Heads(), Recorder()
    await run(handler, screenplay, extraction, rec)
    assert handler.bodies == []
    assert rec.audits[0].heads == ()


async def test_a_frame_with_no_one_described_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, screenplay: Screenplay, extraction: Extraction
) -> None:
    audits_with(monkeypatch, [Verdict.PASS], described(people=[]))
    handler, rec = Heads(), Recorder()
    await run(handler, screenplay, extraction, rec, heads=True)
    assert handler.bodies == []


async def test_a_failed_question_leaves_the_frame_accepted(
    monkeypatch: pytest.MonkeyPatch,
    screenplay: Screenplay,
    extraction: Extraction,
    caplog: pytest.LogCaptureFixture,
) -> None:
    audits_with(monkeypatch, [Verdict.PASS])
    handler, rec = Heads(fail=True), Recorder()
    outcome = await run(handler, screenplay, extraction, rec, heads=True)
    assert len(handler.bodies) == 1
    assert outcome.state is FrameState.PASSED
    (logged,) = rec.audits
    assert logged.heads == () and logged.usage == Usage(300, 60, 0)
    assert "head agent on shot (0, 1) attempt 1 failed" in caplog.text


async def test_a_malformed_answer_leaves_the_frame_accepted(
    monkeypatch: pytest.MonkeyPatch, screenplay: Screenplay, extraction: Extraction
) -> None:
    audits_with(monkeypatch, [Verdict.PASS])
    handler, rec = Heads(answer={"heads": "everywhere"}), Recorder()
    outcome = await run(handler, screenplay, extraction, rec, heads=True)
    assert outcome.state is FrameState.PASSED and rec.audits[0].heads == ()


async def test_dropped_answers_are_counted_in_one_line(
    monkeypatch: pytest.MonkeyPatch,
    screenplay: Screenplay,
    extraction: Extraction,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.verify.audit")
    audits_with(monkeypatch, [Verdict.PASS])
    answer = {"heads": [*ANSWER["heads"], {**ANSWER["heads"][0], "person": 5}]}
    await run(Heads(answer=answer), screenplay, extraction, Recorder(), heads=True)
    assert "head agent on shot (0, 1) attempt 1 kept 1 of 3 answers" in caplog.text


# --- who asks -----------------------------------------------------------------------------------


def _heads_keywords(module: object) -> list[ast.expr | None]:
    """The `heads=` value of every render_until_accepted call in `module`'s source; None when a
    call leaves it out."""
    out: list[ast.expr | None] = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):  # pyright: ignore[reportArgumentType]
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "render_until_accepted":
            out.append(next((k.value for k in node.keywords if k.arg == "heads"), None))
    return out


@pytest.mark.parametrize("module", [storyboard_build, frames_check, frames_attempt])
def test_the_storyboard_paths_keep_the_default(module: object) -> None:
    keywords = _heads_keywords(module)
    assert keywords and all(k is None for k in keywords)


@pytest.mark.db
async def test_the_comic_job_asks_for_heads(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        return replace(passed(frame.attempt, Verdict.PASS), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)
    asked: list[bool] = []
    real = comic_job.render_until_accepted

    async def spy(*args: Any, **kwargs: Any) -> Any:
        asked.append(kwargs.get("heads", False))
        return await real(*args, **{**kwargs, "heads": False})  # no Token Factory here

    monkeypatch.setattr(comic_job, "render_until_accepted", spy)
    store = MemoryStore()
    row = await planned(sessions, store)
    await make_comic(sessions, store, row.id)
    assert asked and all(asked)


# --- the log ------------------------------------------------------------------------------------


@pytest.mark.db
async def test_the_writer_stores_the_heads(sessions: async_sessionmaker[AsyncSession]) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=True)
    with_heads = Audit(
        (0, 1), 1, 7, None, None, (), Verdict.PASS, {}, ("m",), Usage(0, 0, 0),
        heads=(HeadSeen(0, "NANDI", (0.1, 0.2, 0.2, 0.35)),
               HeadSeen(2, None, (0.5, 0.1, 0.6, 0.3))),
    )  # fmt: skip
    without = Audit((0, 1), 2, 8, None, None, (), Verdict.PASS, {}, ("m",), Usage(0, 0, 0))
    writer = FrameWriter(sessions, pid, jid)
    await writer.log(with_heads, "frames/a.png")
    await writer.log(without, "frames/b.png")
    async with sessions() as s:
        rows = (
            await s.scalars(
                select(FrameAuditRow)
                .where(FrameAuditRow.project_id == pid)
                .order_by(FrameAuditRow.attempt)
            )
        ).all()
    assert [r.heads for r in rows] == [
        [
            {"person": 0, "character": "NANDI", "box": [0.1, 0.2, 0.2, 0.35]},
            {"person": 2, "character": None, "box": [0.5, 0.1, 0.6, 0.3]},
        ],
        None,
    ]
