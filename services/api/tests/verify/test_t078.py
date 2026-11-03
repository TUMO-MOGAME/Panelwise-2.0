"""T078: a part of a shot's prop is that prop; the describer leaves out the drawing's own marks
(verify.md §3 A part of a prop, §6 `part_of_prop`, §9)."""

from typing import Any

import pytest

from app.grounding import Extraction
from app.script import Screenplay
from app.verify import Check, ObjectCategory, part_of_prop, run_checks
from app.verify.prompts import DESCRIBE_PROMPT
from tests.verify.conftest import described, judged, kitchen_shot

OTHER = ObjectCategory.OTHER


@pytest.mark.parametrize(
    ("name", "category", "props", "part"),
    [
        ("map corner", OTHER, ("torn map",), "torn map"),
        ("torn map edge", OTHER, ("torn map",), "torn map"),
        ("Map Corner", OTHER, ("torn map",), "torn map"),  # compared in lower case
        ("map", OTHER, ("torn map",), None),  # the prop itself, judged as before
        ("old map", OTHER, ("torn map",), None),  # ends in the head noun: the prop or a copy
        ("second map corner", OTHER, ("torn map",), None),  # a copy word
        ("another map edge", OTHER, ("torn map",), None),
        ("map of the town", OTHER, ("torn map",), None),  # head noun not right before the last
        ("map corner flap", OTHER, ("torn map",), None),
        ("oilskin bag", OTHER, ("oilskin coat",), None),  # a shared word that isn't the head
        ("map corner", OTHER, ("oilskin coat",), None),  # the map isn't in this shot
        ("map corner", OTHER, ("lantern",), None),  # a prop the extraction doesn't quote
        ("map knife", ObjectCategory.WEAPON, ("torn map",), None),  # never set dressing
        ("map pie", ObjectCategory.FOOD, ("torn map",), None),
        ("map dog", ObjectCategory.ANIMAL, ("torn map",), None),
        ("map cart", ObjectCategory.VEHICLE, ("torn map",), None),
    ],
)
def test_part_of_prop(
    extraction: Extraction,
    name: str,
    category: ObjectCategory,
    props: tuple[str, ...],
    part: str | None,
) -> None:
    assert part_of_prop(name, category, kitchen_shot(props=props), extraction) == part


def _fails(
    screenplay: Screenplay,
    extraction: Extraction,
    props: tuple[str, ...],
    call: dict[str, Any],
    name: str = "map corner",
    category: str = "other",
) -> bool:
    objects = [{"name": name, "category": category, "held": True}]
    checks, _, _ = run_checks(
        kitchen_shot(props=props),
        screenplay.scenes[0],
        described(objects=objects),
        judged(objects=[{"object": 0} | call]),
        extraction,
    )
    # Flagged either way: hard for an animal or a weapon, else a warning (T089).
    flagged = {Check.UNSCRIPTED_OBJECT, Check.BACKGROUND_OBJECT}
    return bool(flagged & {c.check for c in checks if not c.ok})


@pytest.mark.parametrize(
    "call",
    [
        {"kind": "unscripted", "support": None},
        {"kind": "set_dressing", "support": "KITCHEN"},
        {"kind": "scripted_prop", "support": None},  # the judge's quote doesn't matter
    ],
)
def test_a_held_part_passes_whatever_the_judge_called_it_when_its_prop_is_in_the_shot(
    screenplay: Screenplay, extraction: Extraction, call: dict[str, Any]
) -> None:
    assert not _fails(screenplay, extraction, ("torn map",), call)


def test_the_same_part_fails_when_its_prop_is_not_in_the_shot(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    assert _fails(
        screenplay, extraction, ("oilskin coat",), {"kind": "unscripted", "support": None}
    )


def test_a_held_weapon_named_like_a_part_still_fails(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    call = {"kind": "set_dressing", "support": "KITCHEN"}
    assert _fails(screenplay, extraction, ("torn map",), call, name="map knife", category="weapon")


def test_the_describer_leaves_out_the_drawing_s_own_marks() -> None:
    prompt = DESCRIBE_PROMPT.lower()
    for mark in ("shading", "hatching", "outlines", "border"):
        assert mark in prompt
