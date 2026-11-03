"""T099: the presence agent, a drawn character the judge didn't match (verify.md §3, §6, §9).
MockTransport, no network."""

import json
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import FrameAuditRow
from app.frames.writer import FrameWriter
from app.grounding import Extraction
from app.llm import NebiusChatModel, Usage
from app.script import Screenplay
from app.verify import Check, RenderedFrame, Verdict, audit_frame, run_checks
from app.verify.audit import PRESENCE_AGENT_PROMPT, SEX_AGENT_PROMPT, present_characters
from app.verify.model import Audit, PersonFound
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.verify.conftest import described, judged, kitchen_shot
from tests.verify.test_t095 import MODELS, PNG, sexed

# The judge calls the older woman no one, with the shot's own line as her support.
NO_ONE = [{"person": 0, "character": None, "support": "Rain hammers the window."}]
OLDER_WOMAN = [{"position": "left", "appearance": "older woman"}]


# --- present_characters -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("person", "accepted", "appearance", "want"),
    [
        (0, {}, "older woman", {"NANDI"}),
        (None, {}, "older woman", set[str]()),  # the agent found no one
        (1, {}, "older woman", set[str]()),  # past the end
        (-1, {}, "older woman", set[str]()),  # negative
        (0, {0: "THABO"}, "older woman", set[str]()),  # already accepted as another character
        (0, {}, "a small child", set[str]()),  # a child for a character introduced at 60
    ],
)
def test_present_characters(
    person: int | None, accepted: dict[int, str], appearance: str, want: set[str]
) -> None:
    description = described(people=[{"position": "left", "appearance": appearance}])
    found = [PersonFound("NANDI", person, "r")]
    got = present_characters(("NANDI",), found, accepted, description, {"NANDI": 60})
    assert got == frozenset(want)


def test_an_answer_for_a_character_not_on_screen_finds_nothing() -> None:
    found = [PersonFound("THABO", 0, "r")]
    assert present_characters(("NANDI",), found, {}, described(), None) == frozenset()


# --- run_checks ---------------------------------------------------------------------------------


def checks_for(
    screenplay: Screenplay, extraction: Extraction, found: list[PersonFound]
) -> tuple[dict[Check, Any], Verdict]:
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judged(people=NO_ONE), extraction,
        on_screen=("NANDI",), found=found,
    )  # fmt: skip
    return {c.check: c for c in checks}, verdict


def test_a_found_character_passes_no_character_and_nothing_else(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    before, _ = checks_for(screenplay, extraction, [])
    after, _ = checks_for(screenplay, extraction, [PersonFound("NANDI", 0, "the woman")])
    assert not before[Check.NO_CHARACTER].ok
    assert before[Check.NO_CHARACTER].detail == "none of NANDI in frame"
    assert after[Check.NO_CHARACTER].ok
    for check in (Check.UNSCRIPTED_PERSON, Check.MISSING_CHARACTER, Check.DRAWN_SEX):
        assert after[check] == before[check]


def test_an_answer_finding_no_one_fails_as_the_judge_alone(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict = checks_for(screenplay, extraction, [PersonFound("NANDI", None, "nobody")])
    assert not checks[Check.NO_CHARACTER].ok
    assert verdict is Verdict.FAIL


# --- audit_frame --------------------------------------------------------------------------------


class Scripted:
    """The describer, the judge, the sex agent and the presence agent, told apart by model and
    system prompt."""

    def __init__(
        self,
        people: list[dict[str, Any]] | None = None,
        found: int | None = 0,
        fail_agent: bool = False,
        described_people: list[dict[str, Any]] | None = None,
    ) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.people = NO_ONE if people is None else people
        self.found = found
        self.fail_agent = fail_agent
        self.described_people = OLDER_WOMAN if described_people is None else described_people

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        system = str(body["messages"][0]["content"])
        if body["model"] == "judge-model":
            content = judged(people=self.people).model_dump_json()
        elif PRESENCE_AGENT_PROMPT in system:
            if self.fail_agent:
                return httpx2.Response(400, json={"detail": "bad"})
            content = json.dumps({"person": self.found, "reason": "the woman at the stove"})
        elif SEX_AGENT_PROMPT in system:
            content = json.dumps({"sex": "male"})
        else:
            content = described(people=self.described_people).model_dump_json()
        return httpx2.Response(
            200,
            json={
                "model": body["model"],
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )


def calls(handler: Scripted, prompt: str) -> list[dict[str, Any]]:
    return [b for b in handler.bodies if prompt in str(b["messages"][0]["content"])]


async def audit(
    handler: Scripted, screenplay: Screenplay, extraction: Extraction, **shot: Any
) -> Audit:
    model = NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        max_attempts=1,
    )
    frame = RenderedFrame((0, 1), 1, 7, PNG, 1024, 576, "p")
    return await audit_frame(model, frame, kitchen_shot(**shot), screenplay, extraction)


async def test_the_agent_finds_a_character_the_judge_left_unmatched(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted()
    result = await audit(handler, screenplay, extraction)
    (call,) = calls(handler, PRESENCE_AGENT_PROMPT)
    assert call["model"] == "vision-model"
    assert call["max_tokens"] == 4096
    text = call["messages"][1]["content"][0]["text"]
    assert text.startswith("The character:\n- NANDI: ")
    assert "NANDI (60s, oilskin coat)" in text
    assert "Shot text:\n" + kitchen_shot().source in text
    assert text.endswith("People in the drawing:\n[0] left: older woman")
    assert call["messages"][1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert result.found == (PersonFound("NANDI", 0, "the woman at the stove"),)
    checks = {c.check: c for c in result.checks}
    assert checks[Check.NO_CHARACTER].ok
    assert result.usage.prompt_tokens == 300  # describer, judge and the agent


async def test_no_question_when_the_judge_matched_a_drawn_character(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    people = [{"person": 0, "character": "NANDI", "support": None}]
    handler = Scripted(people=people)
    result = await audit(handler, screenplay, extraction)
    assert calls(handler, PRESENCE_AGENT_PROMPT) == []
    assert result.found == ()


async def test_no_question_when_no_one_is_drawn(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted()
    result = await audit(handler, screenplay, extraction, characters=())
    assert calls(handler, PRESENCE_AGENT_PROMPT) == []
    assert result.found == ()


async def test_no_question_on_a_malformed_judgement(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(people=NO_ONE * 2)  # person 0 called twice
    result = await audit(handler, screenplay, extraction)
    assert calls(handler, PRESENCE_AGENT_PROMPT) == []
    assert result.verdict is Verdict.ERROR


async def test_a_failed_question_changes_nothing(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(fail_agent=True)
    result = await audit(handler, screenplay, extraction)
    assert len(calls(handler, PRESENCE_AGENT_PROMPT)) == 1
    assert result.found == ()
    assert result.verdict is Verdict.FAIL  # the judge-alone verdict, never ERROR
    assert not {c.check: c for c in result.checks}[Check.NO_CHARACTER].ok


async def test_the_sex_agent_asks_first(screenplay: Screenplay, extraction: Extraction) -> None:
    # THABO is in the cast but only NANDI is drawn: the judge matches the one person to THABO,
    # whom the script sexes, so the sex agent asks about THABO and the presence agent about NANDI.
    people = [{"person": 0, "character": "THABO", "support": None}]
    handler = Scripted(people=people, found=None)
    result = await audit(
        handler, screenplay, sexed(extraction, "THABO", "male"), characters=("NANDI", "THABO")
    )
    order = [
        "sex" if SEX_AGENT_PROMPT in str(b["messages"][0]["content"]) else "presence"
        for b in handler.bodies
        if SEX_AGENT_PROMPT in str(b["messages"][0]["content"])
        or PRESENCE_AGENT_PROMPT in str(b["messages"][0]["content"])
    ]
    assert order == ["sex", "presence"]
    assert result.found == (PersonFound("NANDI", None, "the woman at the stove"),)


# --- the log and recheck ------------------------------------------------------------------------


@pytest.mark.db
async def test_the_writer_stores_the_answers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=True)
    logged = Audit(
        (0, 1), 1, 7, None, None, (), Verdict.PASS, {}, ("m",), Usage(0, 0, 0),
        found=(PersonFound("NANDI", 0, "the woman"), PersonFound("THABO", None, "no boy")),
    )  # fmt: skip
    await FrameWriter(sessions, pid, jid).log(logged, "frames/x.png")
    async with sessions() as s:
        row = (await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == pid))).one()
    assert row.found == [
        {"character": "NANDI", "person": 0, "reason": "the woman"},
        {"character": "THABO", "person": None, "reason": "no boy"},
    ]


@pytest.mark.db
async def test_recheck_passes_the_rows_answers(
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
        row.found = [{"character": "NANDI", "person": 0, "reason": "r"}]
    seen: list[Any] = []
    real = recheck_module.run_checks

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("found"))
        return real(*args, **kwargs)

    monkeypatch.setattr(recheck_module, "run_checks", spy)
    await recheck_module.recheck(sessions, pid)
    assert (PersonFound("NANDI", 0, "r"),) in seen
    assert () in seen  # the comic row: no answers, as the judge alone
