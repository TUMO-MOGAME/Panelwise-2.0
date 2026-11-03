"""T102: a person the presence agent finds is asked the sex question too (verify.md §3, §6, §9).
MockTransport, no network."""

import json
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import FrameAuditRow
from app.grounding import Extraction
from app.llm import Usage
from app.script import Screenplay
from app.verify import Check, Verdict, run_checks
from app.verify.audit import (
    PRESENCE_AGENT_PROMPT,
    SEX_AGENT_PROMPT,
    apply_ladder,
    found_people,
    present_characters,
)
from app.verify.model import Audit, PersonFound, PersonSeen
from tests.verify.conftest import described, judged, kitchen_shot
from tests.verify.test_t095 import sexed
from tests.verify.test_t099 import NO_ONE, OLDER_WOMAN, Scripted, audit, calls

TWO = [
    {"position": "left", "appearance": "older woman"},
    {"position": "right", "appearance": "boy"},
]


# --- found_people -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("found", "accepted", "appearance", "want"),
    [
        ([PersonFound("NANDI", 0, "r")], {}, "older woman", {"NANDI": 0}),
        ([PersonFound("NANDI", None, "r")], {}, "older woman", {}),
        ([PersonFound("NANDI", 1, "r")], {}, "older woman", {}),  # past the end
        ([PersonFound("NANDI", -1, "r")], {}, "older woman", {}),
        ([PersonFound("NANDI", 0, "r")], {0: "THABO"}, "older woman", {}),  # another's
        ([PersonFound("NANDI", 0, "r")], {}, "a small child", {}),  # age contradicted
        ([PersonFound("THABO", 0, "r")], {}, "older woman", {}),  # not on screen
        # the first answer per character
        (
            [PersonFound("NANDI", 0, "a"), PersonFound("NANDI", None, "b")],
            {},
            "older woman",
            {"NANDI": 0},
        ),
        (
            [PersonFound("NANDI", None, "a"), PersonFound("NANDI", 0, "b")],
            {},
            "older woman",
            {"NANDI": 0},
        ),
    ],
)
def test_found_people(
    found: list[PersonFound], accepted: dict[int, str], appearance: str, want: dict[str, int]
) -> None:
    description = described(people=[{"position": "left", "appearance": appearance}])
    got = found_people(("NANDI",), found, accepted, description, {"NANDI": 60})
    assert got == want
    assert present_characters(("NANDI",), found, accepted, description, {"NANDI": 60}) == frozenset(
        want
    )


def test_the_first_passing_answer_wins() -> None:
    found = [PersonFound("NANDI", 0, "a"), PersonFound("NANDI", 1, "b")]
    assert found_people(("NANDI",), found, {}, described(people=TWO), None) == {"NANDI": 0}


def test_two_characters_found_at_one_person_are_both_kept() -> None:
    found = [PersonFound("JABU", 0, "a"), PersonFound("PIETER", 0, "b")]
    got = found_people(("JABU", "PIETER"), found, {}, described(people=OLDER_WOMAN), None)
    assert got == {"JABU": 0, "PIETER": 0}


# --- run_checks ---------------------------------------------------------------------------------


def checks_for(
    screenplay: Screenplay,
    extraction: Extraction,
    found: list[PersonFound],
    seen: list[PersonSeen],
    sexes: dict[str, str] | None = None,
    appearance: str = "older woman",
) -> tuple[dict[Check, Any], Verdict]:
    description = described(people=[{"position": "left", "appearance": appearance}])
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judged(people=NO_ONE), extraction,
        on_screen=("NANDI",), ages={"NANDI": 60}, found=found, seen=seen,
        sexes={"NANDI": "female"} if sexes is None else sexes,
    )  # fmt: skip
    return {c.check: c for c in checks}, verdict


FOUND = [PersonFound("NANDI", 0, "the woman")]


def test_a_found_person_drawn_as_the_other_sex_fails_drawn_sex(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict = checks_for(screenplay, extraction, FOUND, [PersonSeen(0, "NANDI", "male")])
    assert not checks[Check.DRAWN_SEX].ok
    assert checks[Check.DRAWN_SEX].detail == (
        "person 0 (left, older woman): drawn male, but NANDI is female"
    )
    assert checks[Check.NO_CHARACTER].ok  # T099 unchanged
    assert verdict is Verdict.FAIL


@pytest.mark.parametrize(
    ("found", "seen", "sexes", "appearance"),
    [
        (FOUND, [PersonSeen(0, "NANDI", "unclear")], None, "older woman"),
        (FOUND, [PersonSeen(0, "NANDI", "female")], None, "older woman"),
        (FOUND, [PersonSeen(0, "NANDI", "male")], {}, "older woman"),  # no script sex
        (
            FOUND,
            [PersonSeen(0, "THABO", "male")],
            {"THABO": "female"},
            "older woman",
        ),  # filed elsewhere
        ([PersonFound("NANDI", None, "r")], [PersonSeen(0, "NANDI", "male")], None, "older woman"),
        ([PersonFound("NANDI", 0, "r")], [PersonSeen(0, "NANDI", "male")], None, "a small child"),
    ],
)
def test_drawn_sex_passes(
    screenplay: Screenplay,
    extraction: Extraction,
    found: list[PersonFound],
    seen: list[PersonSeen],
    sexes: dict[str, str] | None,
    appearance: str,
) -> None:
    checks, _ = checks_for(screenplay, extraction, found, seen, sexes, appearance)
    assert checks[Check.DRAWN_SEX].ok


THABO_AT_0 = [{"person": 0, "character": "THABO", "support": None}]


def test_a_found_person_the_judge_matched_as_another_character_passes(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # The judge matched person 0 to THABO, so the NANDI answer about them is not NANDI's.
    checks, _, _ = run_checks(
        kitchen_shot(characters=("NANDI", "THABO")), screenplay.scenes[0],
        described(people=OLDER_WOMAN), judged(people=THABO_AT_0),
        extraction, on_screen=("NANDI",), ages={"NANDI": 60}, found=FOUND,
        seen=[PersonSeen(0, "NANDI", "male")], sexes={"NANDI": "female"},
    )  # fmt: skip
    assert {c.check: c for c in checks}[Check.DRAWN_SEX].ok


def test_an_answer_about_a_found_person_out_of_range_passes(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, _ = checks_for(
        screenplay, extraction, [PersonFound("NANDI", 3, "r")], [PersonSeen(3, "NANDI", "male")]
    )
    assert checks[Check.DRAWN_SEX].ok


# --- audit_frame --------------------------------------------------------------------------------


class Sexed(Scripted):
    """T099's handler, its sex agent answering `sex`, or failing."""

    def __init__(self, sex: str = "male", fail_sex: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sex = sex
        self.fail_sex = fail_sex

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if SEX_AGENT_PROMPT in str(body["messages"][0]["content"]):
            self.bodies.append(body)
            if self.fail_sex:
                return httpx2.Response(400, json={"detail": "bad"})
            return httpx2.Response(
                200,
                json={
                    "model": body["model"],
                    "choices": [
                        {
                            "message": {"content": json.dumps({"sex": self.sex})},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                },
            )
        return super().__call__(request)


def order(handler: Scripted) -> list[str]:
    out: list[str] = []
    for b in handler.bodies:
        system = str(b["messages"][0]["content"])
        if SEX_AGENT_PROMPT in system:
            out.append("sex")
        elif PRESENCE_AGENT_PROMPT in system:
            out.append("presence")
    return out


async def test_a_found_person_is_asked_after_the_presence_agent(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed()
    result = await audit(handler, screenplay, sexed(extraction))
    assert order(handler) == ["presence", "sex"]
    (question,) = calls(handler, SEX_AGENT_PROMPT)
    assert question["messages"][1]["content"][0]["text"] == "The person: left, older woman."
    assert result.seen == (PersonSeen(0, "NANDI", "male"),)
    checks = {c.check: c for c in result.checks}
    assert not checks[Check.DRAWN_SEX].ok
    assert checks[Check.NO_CHARACTER].ok
    assert result.verdict is Verdict.FAIL
    assert result.usage.prompt_tokens == 400  # describer, judge, presence and sex agents


async def test_no_question_for_a_found_character_the_script_doesnt_sex(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed()
    result = await audit(handler, screenplay, extraction)
    assert order(handler) == ["presence"]
    assert result.seen == ()


async def test_no_question_when_the_presence_agent_finds_no_one(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed(found=None)
    result = await audit(handler, screenplay, sexed(extraction))
    assert order(handler) == ["presence"]
    assert result.seen == ()


async def test_no_question_when_the_presence_agent_didnt_run(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    people = [{"person": 0, "character": "NANDI", "support": None}]
    handler = Sexed(people=people, sex="female")
    result = await audit(handler, screenplay, sexed(extraction))
    assert order(handler) == ["sex"]  # T095's question about the matched person only
    assert result.seen == (PersonSeen(0, "NANDI", "female"),)


def both_drawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """NANDI and THABO both on screen (the kitchen shot's prompt draws only NANDI)."""
    import app.storyboard.prompt as prompt

    def drawn(*_: object) -> tuple[str, ...]:
        return ("NANDI", "THABO")

    monkeypatch.setattr(prompt, "visible_characters", drawn)


async def test_one_question_per_found_person(
    screenplay: Screenplay, extraction: Extraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    # NANDI and THABO both found at person 0: one question, the answer kept for each.
    both_drawn(monkeypatch)
    handler = Sexed(found=0, sex="male")
    both = sexed(sexed(extraction), "THABO", "male")
    result = await audit(handler, screenplay, both, characters=("NANDI", "THABO"))
    assert order(handler) == ["presence", "presence", "sex"]
    assert result.seen == (PersonSeen(0, "NANDI", "male"), PersonSeen(0, "THABO", "male"))
    checks = {c.check: c for c in result.checks}
    # Opposite script sexes: the answer fails only the character it contradicts.
    assert checks[Check.DRAWN_SEX].detail == (
        "person 0 (left, older woman): drawn male, but NANDI is female"
    )


async def test_the_question_has_room_to_think(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed()
    await audit(handler, screenplay, sexed(extraction))
    (question,) = calls(handler, SEX_AGENT_PROMPT)
    assert question["max_tokens"] == 4096


async def test_a_failed_question_checks_nothing(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed(fail_sex=True)
    result = await audit(handler, screenplay, sexed(extraction))
    assert order(handler) == ["presence", "sex"]
    assert result.seen == ()
    checks = {c.check: c for c in result.checks}
    assert checks[Check.DRAWN_SEX].ok
    assert checks[Check.NO_CHARACTER].ok
    assert result.verdict is not Verdict.ERROR


async def test_the_matched_answers_come_first(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # THABO, in the cast but not drawn, matched at person 1 (T095's question); NANDI, the one drawn,
    # unmatched, so the presence agent runs and finds her at person 0 (T102's question).
    people = [
        {"person": 0, "character": None, "support": "Rain hammers the window."},
        {"person": 1, "character": "THABO", "support": None},
    ]
    handler = Sexed(people=people, described_people=TWO)
    both = sexed(sexed(extraction), "THABO", "male")
    result = await audit(handler, screenplay, both, characters=("NANDI", "THABO"))
    assert order(handler) == ["sex", "presence", "sex"]
    assert result.seen == (PersonSeen(1, "THABO", "male"), PersonSeen(0, "NANDI", "male"))


async def test_no_question_on_a_malformed_judgement(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Sexed(people=NO_ONE * 2)  # person 0 called twice
    result = await audit(handler, screenplay, sexed(extraction))
    assert order(handler) == []
    assert result.found == ()
    assert result.verdict is Verdict.ERROR


def test_off_the_ladder_a_found_person_of_the_other_sex_warns(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(people=OLDER_WOMAN), judged(people=NO_ONE),
        extraction, on_screen=("NANDI",), ages={"NANDI": 60}, found=FOUND,
        seen=[PersonSeen(0, "NANDI", "male")], sexes={"NANDI": "female"},
    )  # fmt: skip
    audit = Audit((0, 1), 1, 7, None, None, checks, verdict, {}, (), Usage(0, 0, 0))
    assert apply_ladder(audit, frozenset({Check.DRAWN_SEX})).verdict is Verdict.FAIL
    assert apply_ladder(audit, frozenset({Check.NO_CHARACTER})).verdict is Verdict.WARN


# --- recheck ------------------------------------------------------------------------------------


@pytest.mark.db
async def test_recheck_passes_the_rows_found_and_seen(
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
        row.seen = [{"person": 0, "character": "NANDI", "sex": "male"}]
    got: list[tuple[Any, Any]] = []
    real = recheck_module.run_checks

    def spy(*args: Any, **kwargs: Any) -> Any:
        got.append((kwargs.get("found"), kwargs.get("seen")))
        return real(*args, **kwargs)

    monkeypatch.setattr(recheck_module, "run_checks", spy)
    await recheck_module.recheck(sessions, pid)
    assert ((PersonFound("NANDI", 0, "r"),), (PersonSeen(0, "NANDI", "male"),)) in got


def test_a_row_from_before_t102_decides_as_before(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # T095's seen only (a matched THABO elsewhere), a found NANDI with no answer: no DRAWN_SEX.
    checks, _ = checks_for(screenplay, extraction, FOUND, [PersonSeen(1, "THABO", "male")])
    assert checks[Check.DRAWN_SEX].ok
