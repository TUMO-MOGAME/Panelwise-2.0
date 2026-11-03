"""T104: the layout agent, a frame drawn as several panels or one person drawn twice (verify.md
§3, §6, §9). MockTransport, no network."""

import inspect
import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, withholding
from app.frames.model import FrameAuditRow
from app.frames.writer import FrameWriter
from app.grounding import Extraction
from app.llm import Usage
from app.script import Screenplay
from app.verify import Check, Verdict, audit_frame, run_checks
from app.verify.audit import LAYOUT_AGENT_PROMPT, apply_ladder, frame_layout
from app.verify.model import Audit, FrameLayout, PersonFound
from app.verify.schema import Layout
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.verify.conftest import described, judged, kitchen_shot
from tests.verify.test_t099 import NO_ONE, Scripted, audit, calls

THREE = [
    {"position": "left", "appearance": "a boy in a blazer"},
    {"position": "centre", "appearance": "a boy in a blazer, waving"},
    {"position": "right", "appearance": "a boy in a blazer, running"},
]
TWO = THREE[:2]
# Two people the describer told apart: T124's described_alike flags TWO on its own words.
UNLIKE = [THREE[0], {"position": "right", "appearance": "an old woman with a walking stick"}]


# --- frame_layout -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("panels", "copies", "want_panels", "want_copies"),
    [
        (1, [[1, 0], [0, 1], [2, 0]], 1, ((0, 1), (0, 2))),  # sorted, once
        (2, [[0, 0], [-1, 0], [0, 3], [0], [0, 1, 2]], 2, ()),  # [i, i], out of range, short, long
        (0, [], 1, ()),
        (-1, [[0, 1]], 1, ((0, 1),)),
    ],
)
def test_frame_layout(
    panels: int, copies: list[list[int]], want_panels: int, want_copies: tuple[tuple[int, int], ...]
) -> None:
    got = frame_layout(Layout(panels=panels, copies=copies, reason="r"), 3)
    assert got == FrameLayout(want_panels, want_copies, "r")


# --- run_checks ---------------------------------------------------------------------------------


def checks_for(
    screenplay: Screenplay,
    extraction: Extraction,
    layout: FrameLayout | None,
    people: list[dict[str, Any]] | None = None,
    calls_: list[dict[str, Any]] | None = None,
    found: list[PersonFound] | None = None,
    on_screen: tuple[str, ...] = ("NANDI", "THABO"),
) -> tuple[dict[Check, Any], Verdict]:
    described_people = TWO if people is None else people
    if calls_ is None:
        calls_ = [
            {"person": i, "character": None, "support": None} for i in range(len(described_people))
        ]
    checks, verdict, _ = run_checks(
        kitchen_shot(characters=("NANDI", "THABO")), screenplay.scenes[0],
        described(people=described_people), judged(people=calls_), extraction,
        on_screen=on_screen, layout=layout, found=found or [],
    )  # fmt: skip
    return {c.check: c for c in checks}, verdict


def test_a_split_frame_fails_split_panels(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, verdict = checks_for(screenplay, extraction, FrameLayout(2, ((0, 1),), "r"))
    assert not checks[Check.SPLIT_PANELS].ok
    assert checks[Check.SPLIT_PANELS].detail == "drawn as 2 panels"
    assert checks[Check.DRAWN_TWICE].ok  # the split's own copies
    assert verdict is Verdict.FAIL


def test_one_person_drawn_twice_fails(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, _ = checks_for(screenplay, extraction, FrameLayout(1, ((0, 1),), "r"))
    assert checks[Check.SPLIT_PANELS].ok
    assert checks[Check.DRAWN_TWICE].detail == (
        "person 0 (left, a boy in a blazer) and person 1 (centre, a boy in a blazer, waving): "
        "the same person drawn twice"
    )


def test_three_times_is_three_pairs(screenplay: Screenplay, extraction: Extraction) -> None:
    layout = FrameLayout(1, ((0, 1), (0, 2), (1, 2)), "r")
    checks, _ = checks_for(screenplay, extraction, layout, people=THREE)
    assert checks[Check.DRAWN_TWICE].detail.count("the same person drawn twice") == 3
    assert checks[Check.DRAWN_TWICE].detail.count("; ") == 2


MATCHED = [
    {"person": 0, "character": "NANDI", "support": None},
    {"person": 1, "character": "THABO", "support": None},
]
ONE_MATCHED = [
    {"person": 0, "character": "NANDI", "support": None},
    {"person": 1, "character": None, "support": None},
]


@pytest.mark.parametrize(
    ("calls_", "found", "ok"),
    [
        (MATCHED, [], True),  # two characters, both accepted
        (ONE_MATCHED, [], False),  # one accepted, one not: still a copy
        (None, [], False),  # neither known
        (None, [PersonFound("NANDI", 0, "r"), PersonFound("THABO", 1, "r")], True),  # both found
    ],
)
def test_the_veto(
    screenplay: Screenplay,
    extraction: Extraction,
    calls_: list[dict[str, Any]] | None,
    found: list[PersonFound],
    ok: bool,
) -> None:
    checks, _ = checks_for(
        screenplay, extraction, FrameLayout(1, ((0, 1),), "r"), calls_=calls_, found=found
    )
    assert checks[Check.DRAWN_TWICE].ok is ok


def test_one_accepted_and_one_found_as_another_character_pass(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # NANDI matched at 0, THABO (drawn, unmatched) found at 1.
    checks, _ = checks_for(
        screenplay, extraction, FrameLayout(1, ((0, 1),), "r"), calls_=ONE_MATCHED,
        found=[PersonFound("THABO", 1, "r")],
    )  # fmt: skip
    assert checks[Check.DRAWN_TWICE].ok


def test_no_layout_passes_both(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, _ = checks_for(screenplay, extraction, None, people=UNLIKE)
    assert checks[Check.SPLIT_PANELS].ok and checks[Check.DRAWN_TWICE].ok


def test_the_ladder_withholds_or_warns(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(people=TWO),
        judged(people=[{"person": 0, "character": "NANDI", "support": None},
                       {"person": 1, "character": None, "support": "Rain hammers the window."}]),
        extraction, on_screen=("NANDI",), layout=FrameLayout(2, (), "r"),
    )  # fmt: skip
    logged = Audit((0, 1), 1, 7, None, None, checks, verdict, {}, (), Usage(0, 0, 0))
    assert apply_ladder(logged, None).verdict is Verdict.FAIL  # the default: every hard check
    assert apply_ladder(logged, frozenset({Check.SPLIT_PANELS})).verdict is Verdict.FAIL
    assert apply_ladder(logged, frozenset({Check.DRAWN_SEX})).verdict is Verdict.WARN


def hosted_ladder() -> frozenset[Check] | None:
    """render.yaml's AUDIT_WITHHOLD_CHECKS, read as the API reads it."""
    text = (Path(__file__).parents[4] / "render.yaml").read_text(encoding="utf-8")
    value = re.search(r"key: AUDIT_WITHHOLD_CHECKS\s+value: (\S+)", text)
    assert value is not None
    return withholding(Settings(audit_withhold_checks=value[1]))


def test_the_hosted_ladder_withholds_a_split_and_warns_a_copy(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # render.yaml's ladder (Katlego, 2026-10-17): split_panels withholds, drawn_twice warns. T124
    # put drawn_twice on it for one night; the T109 re-score withheld right frames for it.
    hosted = hosted_ladder()
    assert hosted == frozenset({Check.DRAWN_SEX, Check.NO_CHARACTER, Check.SPLIT_PANELS})
    for layout, want in (
        (FrameLayout(1, ((0, 1),), "r"), Verdict.WARN),
        (FrameLayout(2, (), "r"), Verdict.FAIL),
    ):
        checks, verdict, _ = run_checks(
            kitchen_shot(), screenplay.scenes[0], described(people=TWO),
            judged(people=MATCHED_TWO), extraction, on_screen=("NANDI",), layout=layout,
        )  # fmt: skip
        logged = Audit((0, 1), 1, 7, None, None, checks, verdict, {}, (), Usage(0, 0, 0))
        assert verdict is Verdict.FAIL  # every hard check, before the ladder
        assert apply_ladder(logged, hosted).verdict is want


# --- audit_frame --------------------------------------------------------------------------------


class Laid(Scripted):
    """T099's handler; its layout agent answers `answer`, or fails."""

    def __init__(self, answer: dict[str, Any] | None = None, fail: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self.answer = answer or {"panels": 2, "copies": [], "reason": "a strip of two"}
        self.fail = fail

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if LAYOUT_AGENT_PROMPT in str(body["messages"][0]["content"]):
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
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                },
            )
        return super().__call__(request)


MATCHED_TWO = [
    {"person": 0, "character": "NANDI", "support": None},
    {"person": 1, "character": None, "support": "Rain hammers the window."},
]


async def test_the_agent_asks_once_on_two_or_more_people_and_last(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Laid(people=MATCHED_TWO, described_people=TWO)
    result = await audit(handler, screenplay, extraction)
    (call,) = calls(handler, LAYOUT_AGENT_PROMPT)
    assert handler.bodies[-1] is call  # after the other agents
    assert call["model"] == "vision-model" and call["max_tokens"] == 4096
    text = call["messages"][1]["content"][0]["text"]
    assert text == (
        "People in the drawing:\n[0] left: a boy in a blazer\n[1] centre: a boy in a blazer, waving"
    )
    assert call["messages"][1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert result.layout == FrameLayout(2, (), "a strip of two")
    assert not {c.check: c for c in result.checks}[Check.SPLIT_PANELS].ok
    # describer, judge, the presence agent (NANDI, 60s, as "a boy" is refused for age) and layout
    assert result.usage.prompt_tokens == 400


async def test_no_question_for_one_person(screenplay: Screenplay, extraction: Extraction) -> None:
    handler = Laid(people=[{"person": 0, "character": "NANDI", "support": None}])
    result = await audit(handler, screenplay, extraction)
    assert calls(handler, LAYOUT_AGENT_PROMPT) == []
    assert result.layout is None


async def test_no_question_on_a_malformed_judgement(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Laid(people=NO_ONE * 2, described_people=TWO)
    result = await audit(handler, screenplay, extraction)
    assert calls(handler, LAYOUT_AGENT_PROMPT) == []
    assert result.verdict is Verdict.ERROR


async def test_a_failed_question_checks_nothing(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Laid(people=MATCHED_TWO, described_people=UNLIKE, fail=True)
    result = await audit(handler, screenplay, extraction)
    assert len(calls(handler, LAYOUT_AGENT_PROMPT)) == 1
    assert result.layout is None
    assert result.verdict is not Verdict.ERROR
    checks = {c.check: c for c in result.checks}
    assert checks[Check.SPLIT_PANELS].ok and checks[Check.DRAWN_TWICE].ok


def test_every_target_goes_through_the_same_audit() -> None:
    # audit_frame takes no target: storyboard frames and comic panels are audited alike (loop.py).
    assert "target" not in inspect.signature(audit_frame).parameters


# --- the log and recheck ------------------------------------------------------------------------


@pytest.mark.db
async def test_the_writer_stores_the_layout(sessions: async_sessionmaker[AsyncSession]) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=True)
    logged = Audit(
        (0, 1), 1, 7, None, None, (), Verdict.PASS, {}, ("m",), Usage(0, 0, 0),
        layout=FrameLayout(1, ((0, 2),), "the same boy"),
    )  # fmt: skip
    await FrameWriter(sessions, pid, jid).log(logged, "frames/x.png")
    async with sessions() as s:
        row = (await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == pid))).one()
    assert row.layout == {"panels": 1, "copies": [[0, 2]], "reason": "the same boy"}


@pytest.mark.db
async def test_recheck_passes_the_rows_layout(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.verify.recheck as recheck_module
    from tests.verify.test_recheck import _logged  # pyright: ignore[reportPrivateUsage]

    pid, _, _ = await _logged(sessions)
    async with sessions() as s, s.begin():
        row = (
            await s.scalars(
                select(FrameAuditRow).where(
                    FrameAuditRow.project_id == pid,
                    FrameAuditRow.target == "storyboard",
                    FrameAuditRow.attempt == 1,
                )
            )
        ).one()
        row.layout = {"panels": 3, "copies": [], "reason": "r"}
    got: list[Any] = []
    real = recheck_module.run_checks

    def spy(*args: Any, **kwargs: Any) -> Any:
        got.append(kwargs.get("layout"))
        return real(*args, **kwargs)

    monkeypatch.setattr(recheck_module, "run_checks", spy)
    await recheck_module.recheck(sessions, pid)
    assert FrameLayout(3, (), "r") in got
    assert None in got  # the comic row: no layout, both checks pass
