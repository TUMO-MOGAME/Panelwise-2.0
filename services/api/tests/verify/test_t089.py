"""T089: an object, but an animal or a weapon, and painted lettering warn instead of withholding
the frame; people stay hard (docs/design/verify.md §3 Objects and lettering warn, §6, §9)."""

from typing import Any

import pytest

from app.grounding import Extraction
from app.script import Screenplay
from app.verify import Check, Verdict, audit, run_checks
from app.verify.model import CheckResult, ObjectCategory, Severity
from tests.verify.conftest import described, judged, kitchen_shot

SEVERITY = audit._SEVERITY  # pyright: ignore[reportPrivateUsage]
filed_as = audit._filed  # pyright: ignore[reportPrivateUsage]
Seen = dict[str, Any]


def _audit(
    screenplay: Screenplay,
    extraction: Extraction,
    *,
    calls: list[Seen] | None = None,
    matches: list[Seen] | None = None,
    **seen: Any,
) -> tuple[dict[Check, CheckResult], Verdict]:
    calls_kw: dict[str, Any] = {} if calls is None else {"objects": calls}
    matches_kw: dict[str, Any] = {} if matches is None else {"people": matches}
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(**seen),
        judged(**calls_kw, **matches_kw),
        extraction,
    )
    failed = {c.check: c for c in checks if not c.ok}
    return failed, verdict


def _one(
    screenplay: Screenplay, extraction: Extraction, obj: Seen, call: Seen
) -> tuple[dict[Check, CheckResult], Verdict]:
    return _audit(screenplay, extraction, objects=[obj], calls=[{"object": 0, **call}])


@pytest.mark.parametrize(
    ("category", "check"),
    [
        (ObjectCategory.ANIMAL, Check.UNSCRIPTED_OBJECT),
        (ObjectCategory.WEAPON, Check.UNSCRIPTED_OBJECT),
        *(
            (c, Check.BACKGROUND_OBJECT)
            for c in ObjectCategory
            if c not in (ObjectCategory.ANIMAL, ObjectCategory.WEAPON)
        ),
    ],
)
def test_filed(category: ObjectCategory, check: Check) -> None:
    assert filed_as(category) is check


def test_severities() -> None:
    assert SEVERITY[Check.TEXT_IN_FRAME] is Severity.SOFT
    assert SEVERITY[Check.UNSCRIPTED_OBJECT] is Severity.HARD
    assert SEVERITY[Check.BACKGROUND_OBJECT] is Severity.SOFT
    assert SEVERITY[Check.UNSCRIPTED_PERSON] is Severity.HARD


def test_an_unheld_pen_warns(screenplay: Screenplay, extraction: Extraction) -> None:
    failed, verdict = _one(
        screenplay,
        extraction,
        {"name": "pen", "category": "other", "held": False},
        {"kind": "unscripted", "support": None},
    )
    assert failed[Check.BACKGROUND_OBJECT].detail == "object 0 (pen, other): not in the script"
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert verdict is Verdict.WARN


@pytest.mark.parametrize(
    ("obj", "call", "detail"),
    [
        (
            {"name": "pen", "category": "other", "held": True},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (pen, other): held, so not set dressing",
        ),
        (
            {"name": "bun", "category": "food", "held": True},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (bun, food): held, so not set dressing",
        ),
        (
            {"name": "car", "category": "vehicle", "held": False},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (car, vehicle): never set dressing",
        ),
        (
            {"name": "mug", "category": "other", "held": True},
            {"kind": "scripted_prop", "support": "a mug of tea nobody wrote"},
            "object 0 (mug, other): prop without support",
        ),
        (
            {"name": "scarf", "category": "clothing", "held": True},
            {"kind": "unscripted", "support": None},
            "object 0 (scarf, clothing): unscripted",
        ),
        (
            {"name": "torn map", "category": "other", "held": False},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (torn map, other): the script names it",
        ),
    ],
)
def test_other_object_failures_warn_with_their_own_detail(
    screenplay: Screenplay, extraction: Extraction, obj: Seen, call: Seen, detail: str
) -> None:
    failed, verdict = _one(screenplay, extraction, obj, call)
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert failed[Check.BACKGROUND_OBJECT].detail == detail
    assert failed[Check.BACKGROUND_OBJECT].severity is Severity.SOFT
    assert verdict is Verdict.WARN


@pytest.mark.parametrize(
    ("obj", "call", "detail"),
    [
        (
            {"name": "knife", "category": "weapon", "held": False},
            {"kind": "unscripted", "support": None},
            "object 0 (knife, weapon): unscripted",
        ),
        (
            {"name": "knife", "category": "weapon", "held": True},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (knife, weapon): held, so not set dressing",
        ),
        (
            {"name": "dog", "category": "animal", "held": False},
            {"kind": "set_dressing", "support": "KITCHEN"},
            "object 0 (dog, animal): never set dressing",
        ),
        (
            {"name": "dog", "category": "animal", "held": False},
            {"kind": "scripted_prop", "support": "a dog nobody wrote"},
            "object 0 (dog, animal): prop without support",
        ),
    ],
)
def test_animals_and_weapons_stay_hard(
    screenplay: Screenplay, extraction: Extraction, obj: Seen, call: Seen, detail: str
) -> None:
    failed, verdict = _one(screenplay, extraction, obj, call)
    assert failed[Check.UNSCRIPTED_OBJECT].detail == detail
    assert failed[Check.UNSCRIPTED_OBJECT].severity is Severity.HARD
    assert verdict is Verdict.FAIL


def test_painted_text_alone_warns(screenplay: Screenplay, extraction: Extraction) -> None:
    failed, verdict = _audit(screenplay, extraction, text=["LOST POVERTY"])
    assert failed[Check.TEXT_IN_FRAME].detail == "text 'LOST POVERTY' isn't the script's"
    assert failed[Check.TEXT_IN_FRAME].severity is Severity.SOFT
    assert verdict is Verdict.WARN


def test_painted_text_with_a_stranger_fails(screenplay: Screenplay, extraction: Extraction) -> None:
    failed, verdict = _audit(
        screenplay,
        extraction,
        text=["LOST POVERTY"],
        people=[
            {"position": "left", "appearance": "older woman"},
            {"position": "right", "appearance": "an adult man"},
        ],
        matches=[
            {"person": 0, "character": "NANDI", "support": None},
            {"person": 1, "character": None, "support": None},
        ],
    )
    assert failed[Check.UNSCRIPTED_PERSON].severity is Severity.HARD
    assert Check.TEXT_IN_FRAME in failed
    assert verdict is Verdict.FAIL
