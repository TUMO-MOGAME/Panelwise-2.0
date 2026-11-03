"""T080: the judge refuses a wrong sex or look; a frame with none of the people the prompt drew
fails `NO_CHARACTER` (verify.md §3, §6, §9)."""

from typing import Any

from app.grounding import Extraction
from app.script import Screenplay
from app.verify import JUDGE_PROMPT, Check, Severity, Verdict, audit_frame, run_checks
from tests.verify.conftest import described, judged, kitchen_shot
from tests.verify.test_audit import Scripted, frame, model_for

NOBODY: dict[str, Any] = {"people": []}


def _run(
    screenplay: Screenplay,
    extraction: Extraction,
    on_screen: tuple[str, ...],
    who: dict[str, Any] | None = None,
) -> tuple[set[Check], Verdict]:
    who = who if who is not None else NOBODY
    people = [{"position": "left", "appearance": "a child"}] if who["people"] else []
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=people),
        judged(people=who["people"]),
        extraction,
        on_screen=on_screen,
    )
    return {c.check for c in checks if not c.ok}, verdict


def test_no_one_described_fails_when_the_prompt_drew_someone(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    failed, verdict = _run(screenplay, extraction, ("NANDI",))
    assert Check.NO_CHARACTER in failed
    assert verdict is Verdict.FAIL


def test_only_a_stranger_fails_too(screenplay: Screenplay, extraction: Extraction) -> None:
    stranger = {"people": [{"person": 0, "character": None, "support": "a crowd gathers"}]}
    failed, _ = _run(screenplay, extraction, ("NANDI",), stranger)
    assert Check.NO_CHARACTER in failed


def test_the_drawn_character_matched_passes(screenplay: Screenplay, extraction: Extraction) -> None:
    nandi = {"people": [{"person": 0, "character": "NANDI", "support": None}]}
    failed, _ = _run(screenplay, extraction, ("NANDI",), nandi)
    assert Check.NO_CHARACTER not in failed


def test_a_shot_that_drew_no_one_never_fails_it(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    failed, _ = _run(screenplay, extraction, ())
    assert Check.NO_CHARACTER not in failed


def test_no_character_is_hard(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=[]),
        judged(people=[]),
        extraction,
        on_screen=("NANDI",),
    )
    assert next(c for c in checks if c.check is Check.NO_CHARACTER).severity is Severity.HARD


async def test_audit_frame_checks_against_the_people_the_prompt_drew(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    """The kitchen shot's line names NANDI, so the prompt drew her: an empty frame fails."""
    handler = Scripted(described(people=[]).model_dump_json(), judged(people=[]).model_dump_json())
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.FAIL
    assert Check.NO_CHARACTER in [c.check for c in audit.checks if not c.ok]


def test_the_judge_refuses_a_contradicted_sex_or_look() -> None:
    prompt = JUDGE_PROMPT.lower()
    assert "sex" in prompt and "look" in prompt
    assert "she" in prompt and "braids" in prompt


def test_a_matched_character_the_prompt_didn_t_draw_doesn_t_count(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    """T080 review: NANDI drawn, only THABO matched: the frame isn't of the people it asked for."""
    shot = kitchen_shot(characters=("NANDI", "THABO"))
    thabo = [{"person": 0, "character": "THABO", "support": None}]
    checks, verdict, _ = run_checks(
        shot,
        screenplay.scenes[0],
        described(people=[{"position": "left", "appearance": "a man"}]),
        judged(people=thabo),
        extraction,
        on_screen=("NANDI",),
    )
    assert Check.NO_CHARACTER in {c.check for c in checks if not c.ok}
    assert verdict is Verdict.FAIL
