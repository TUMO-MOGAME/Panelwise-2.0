"""T095: the sex agent, a matched character drawn as the other sex fails DRAWN_SEX; and T094's
ladder demoting a hard check off it (verify.md §3, §6, §9). MockTransport, no network."""

import json
from dataclasses import replace
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import FrameAuditRow
from app.frames.writer import FrameWriter
from app.grounding import EntityKind, Extraction
from app.llm import NebiusChatModel, Tier, Usage
from app.script import Screenplay
from app.verify import Check, RenderedFrame, Verdict, audit_frame, run_checks
from app.verify.audit import SEX_AGENT_PROMPT, apply_ladder, matched_people
from app.verify.model import Audit, CheckResult, PersonSeen, Severity
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.verify.conftest import described, judged, kitchen_shot

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "judge-model", Tier.VISION: "vision-model"}
PNG = b"\x89PNG\r\n\x1a\nnot-really-a-frame"
OLDER_WOMAN = [{"position": "left", "appearance": "older woman"}]


def sexed(extraction: Extraction, name: str = "NANDI", sex: str = "female") -> Extraction:
    """The extraction with `name` given a grounded sex, as T088/T091 would."""
    entities = tuple(
        replace(e, sex=sex, sex_quote=e.quotes[0])
        if e.kind is EntityKind.CHARACTER and e.name == name
        else e
        for e in extraction.entities
    )
    return replace(extraction, entities=entities)


# --- run_checks ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "sexes", "fails"),
    [
        ("male", {"NANDI": "female"}, True),
        ("female", {"NANDI": "female"}, False),
        ("unclear", {"NANDI": "female"}, False),
        ("male", {}, False),  # no sex from the script: never asked, never failed
    ],
)
def test_drawn_sex(
    screenplay: Screenplay, extraction: Extraction, answer: str, sexes: dict[str, str], fails: bool
) -> None:
    checks, verdict = run_checks_for(
        screenplay, extraction, [PersonSeen(0, "NANDI", answer)], sexes
    )
    assert checks[Check.DRAWN_SEX].ok is not fails
    if fails:
        assert verdict is Verdict.FAIL
        assert checks[Check.DRAWN_SEX].detail == (
            "person 0 (left, older woman): drawn male, but NANDI is female"
        )


def run_checks_for(
    screenplay: Screenplay, extraction: Extraction, seen: list[PersonSeen], sexes: dict[str, str]
) -> Any:
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judged(), extraction, seen=seen,
        sexes=sexes,
    )  # fmt: skip
    return {c.check: c for c in checks}, verdict


def test_an_answer_about_a_person_not_accepted_as_that_character_is_ignored(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # person 0 is NANDI; an answer filed against another index or name checks nothing.
    checks, _ = run_checks_for(
        screenplay, extraction, [PersonSeen(0, "THABO", "male")], {"NANDI": "female"}
    )
    assert checks[Check.DRAWN_SEX].ok


def test_matched_people_skips_a_second_call_and_an_unknown_name(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(people=OLDER_WOMAN * 3)
    judgement = judged(
        people=[
            {"person": 0, "character": "NANDI", "support": None},
            {"person": 1, "character": "NANDI", "support": None},
            {"person": 2, "character": "MARIA", "support": None},
        ]
    )
    assert matched_people(kitchen_shot(), description, judgement, extraction) == {0: "NANDI"}


def test_matched_people_skips_a_person_refused_for_their_age(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(people=[{"position": "left", "appearance": "a small child"}])
    out = matched_people(kitchen_shot(), description, judged(), extraction, {"NANDI": 60})
    assert out == {}


# --- audit_frame --------------------------------------------------------------------------------


class Scripted:
    """The describer, the judge and the sex agent, told apart by model and system prompt."""

    def __init__(self, sex: str | None = "female", fail_agent: bool = False) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.sex = sex
        self.fail_agent = fail_agent

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if body["model"] == "judge-model":
            content = judged().model_dump_json()
        elif SEX_AGENT_PROMPT in str(body["messages"][0]["content"]):
            if self.fail_agent:
                return httpx2.Response(400, json={"detail": "bad"})
            content = json.dumps({"sex": self.sex})
        else:
            content = described().model_dump_json()
        return httpx2.Response(
            200,
            json={
                "model": body["model"],
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )


def agent_calls(handler: Scripted) -> list[dict[str, Any]]:
    return [b for b in handler.bodies if SEX_AGENT_PROMPT in str(b["messages"][0]["content"])]


async def audit(handler: Scripted, screenplay: Screenplay, extraction: Extraction) -> Audit:
    model = NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        max_attempts=1,
    )
    frame = RenderedFrame((0, 1), 1, 7, PNG, 1024, 576, "p")
    return await audit_frame(model, frame, kitchen_shot(), screenplay, extraction)


async def test_the_agent_asks_about_a_matched_character_the_script_sexes(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(sex="male")
    result = await audit(handler, screenplay, sexed(extraction))
    (call,) = agent_calls(handler)
    assert call["model"] == "vision-model"
    assert "older woman" in json.dumps(call)
    assert result.seen == (PersonSeen(0, "NANDI", "male"),)
    assert result.verdict is Verdict.FAIL
    assert {c.check for c in result.checks if not c.ok} >= {Check.DRAWN_SEX}
    assert result.usage.prompt_tokens == 300  # describer, judge and the agent


async def test_no_question_without_a_sex_from_the_script(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted()
    result = await audit(handler, screenplay, extraction)
    assert agent_calls(handler) == []
    assert result.seen == ()


async def test_a_failed_question_checks_nothing_and_is_no_error(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(fail_agent=True)
    result = await audit(handler, screenplay, sexed(extraction))
    assert len(agent_calls(handler)) == 1
    assert result.seen == ()
    assert result.verdict is not Verdict.ERROR


# --- the ladder (T094) --------------------------------------------------------------------------


def failed(*checks: Check) -> Audit:
    results = tuple(CheckResult(c, Severity.HARD, False, "x") for c in checks)
    return Audit((0, 1), 1, 7, None, None, results, Verdict.FAIL, {}, ("m",), Usage(0, 0, 0))


def test_the_ladder_demotes_a_hard_check_off_it() -> None:
    out = apply_ladder(failed(Check.UNSCRIPTED_PERSON), frozenset({Check.DRAWN_SEX}))
    assert out.verdict is Verdict.WARN
    assert out.checks[0].severity is Severity.SOFT and not out.checks[0].ok


def test_a_withheld_frame_names_only_a_check_on_the_ladder() -> None:
    out = apply_ladder(
        failed(Check.UNSCRIPTED_PERSON, Check.DRAWN_SEX), frozenset({Check.DRAWN_SEX})
    )
    assert out.verdict is Verdict.FAIL
    hard = [c.check for c in out.checks if not c.ok and c.severity is Severity.HARD]
    assert hard == [Check.DRAWN_SEX]


def test_all_keeps_the_audit() -> None:
    audit_ = failed(Check.UNSCRIPTED_PERSON)
    assert apply_ladder(audit_, None) is audit_


@pytest.mark.db
async def test_the_writer_stores_the_agents_answers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=True)
    logged = replace(failed(Check.DRAWN_SEX), seen=(PersonSeen(0, "NANDI", "male"),))
    await FrameWriter(sessions, pid, jid).log(logged, "frames/x.png")
    async with sessions() as s:
        row = (await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == pid))).one()
    assert row.seen == [{"person": 0, "character": "NANDI", "sex": "male"}]
