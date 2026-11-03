"""T083: things the scene names are scripted; everyday background objects warn
(docs/design/verify.md §3, §6, §9)."""

import dataclasses
from typing import Any

import pytest

from app.grounding import Extraction
from app.script import Action, Dialogue, IntExt, Scene, Screenplay, Span
from app.verify import Check, Severity, Verdict, run_checks
from app.verify.audit import named_in_scene
from app.verify.model import ObjectCategory
from tests.verify.conftest import described, judged, kitchen_shot

HARBOUR = Scene(
    index=0,
    number="1",
    heading="EXT. QUAYSIDE -- DAWN",
    int_ext=IntExt.EXT,
    location="QUAYSIDE",
    time_of_day="DAWN",
    elements=(
        Action(
            "A small fishing harbour on a wild coast. Grey water, grey sky, a single row of "
            "forty-year-old wooden fishing-boats knocking against a concrete jetty.",
            Span(2, 75, 77),
        ),
        Action("Gulls wheel. A dog trots past with a fish-head in its mouth.", Span(2, 79, 80)),
        Action("A rusted bakkie waits at the end of the road.", Span(2, 82, 82)),
        Action(
            "Two horses graze by the slipway. Ponies too, and a police officer.", Span(2, 84, 84)
        ),
        Action("Boxes of bait are stacked high.", Span(2, 86, 86)),
        Action(
            "It will be a long night. Nobody cares. A bus passes. A door bangs.", Span(2, 87, 87)
        ),
        Dialogue("SIPHO", None, None, "My yacht is in Durban.", Span(2, 88, 89)),
    ),
    span=Span(2, 74, 82),
)


@pytest.mark.parametrize(
    ("name", "category", "word"),
    [
        ("boat masts", ObjectCategory.VEHICLE, "boats"),
        ("boats", ObjectCategory.VEHICLE, "boats"),
        ("fishing boat", ObjectCategory.VEHICLE, "boats"),
        ("fish", ObjectCategory.FOOD, "fish"),
        ("dogs", ObjectCategory.ANIMAL, "dog"),
        ("off-road vehicle", ObjectCategory.VEHICLE, None),  # a hyphenated word stays whole
        ("second boat", ObjectCategory.VEHICLE, None),  # a copy word
        ("another dog", ObjectCategory.ANIMAL, None),
        ("small boats", ObjectCategory.OTHER, None),  # not one of the four categories
        ("box of fish", ObjectCategory.FOOD, "fish"),  # its own noun, not "of"
        ("cart of", ObjectCategory.VEHICLE, None),  # "of" is never a candidate
        ("pickup truck", ObjectCategory.VEHICLE, None),  # the scene names a bakkie, not a truck
        ("ox", ObjectCategory.ANIMAL, None),  # under 3 letters
        ("horse", ObjectCategory.ANIMAL, "horses"),  # a singular meets its plural
        ("pony", ObjectCategory.ANIMAL, "ponies"),
        ("box", ObjectCategory.FOOD, "boxes"),
        ("police car", ObjectCategory.VEHICLE, None),  # car is no part word
        ("dog collar", ObjectCategory.ANIMAL, "dog"),  # a part of the scene's dog
        ("harbour boat", ObjectCategory.VEHICLE, "boats"),
        ("yacht", ObjectCategory.VEHICLE, None),  # only talked about, in dialogue
        ("quayside", ObjectCategory.VEHICLE, None),  # only in the heading
        ("bees", ObjectCategory.ANIMAL, None),  # never "be" (the code review)
        ("car", ObjectCategory.VEHICLE, None),  # never "cares"
        ("car door", ObjectCategory.VEHICLE, None),  # a part is named by its whole, not the door
        ("buses", ObjectCategory.VEHICLE, "bus"),
        ("horses", ObjectCategory.ANIMAL, "horses"),
        ("boxes", ObjectCategory.FOOD, "boxes"),
        ("wheel", ObjectCategory.VEHICLE, "wheel"),  # residue: the verb in "Gulls wheel"
    ],
)
def test_named_in_scene(name: str, category: ObjectCategory, word: str | None) -> None:
    assert named_in_scene(name, category, HARBOUR) == word


def _objects(
    screenplay: Screenplay,
    extraction: Extraction,
    scene: Scene,
    objects: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> tuple[dict[Check, str], Verdict]:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        scene,
        described(objects=objects),
        judged(objects=calls),
        extraction,
    )
    return {c.check: c.detail for c in checks if not c.ok}, verdict


def _kitchen(screenplay: Screenplay) -> Scene:
    return screenplay.scenes[0]


def test_boats_the_scene_names_pass_whatever_the_judge_called_them(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    failed, _ = _objects(
        screenplay,
        extraction,
        HARBOUR,
        [{"name": "boats", "category": "vehicle", "held": False}],
        [{"object": 0, "kind": "set_dressing", "support": "EXT. HARBOUR"}],
    )
    assert Check.UNSCRIPTED_OBJECT not in failed


def test_a_vehicle_the_scene_never_names_warns(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    failed, verdict = _objects(
        screenplay,
        extraction,
        _kitchen(screenplay),
        [{"name": "boats", "category": "vehicle", "held": False}],
        [{"object": 0, "kind": "set_dressing", "support": "KITCHEN"}],
    )
    assert "never set dressing" in failed[Check.BACKGROUND_OBJECT]  # T089: no animal or weapon
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert verdict is Verdict.WARN


def test_an_unheld_everyday_object_only_warns(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    failed, verdict = _objects(
        screenplay,
        extraction,
        _kitchen(screenplay),
        [
            {"name": "coat", "category": "clothing", "held": False},
            {"name": "pen", "category": "other", "held": False},
            {"name": "moon", "category": "nature", "held": False},
        ],
        [
            {"object": 0, "kind": "scripted_prop", "support": "oilskin coat"},
            {"object": 1, "kind": "unscripted", "support": None},
            {"object": 2, "kind": "set_dressing", "support": "the night sky"},
        ],
    )
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert failed[Check.BACKGROUND_OBJECT] == (
        "object 1 (pen, other): not in the script; object 2 (moon, nature): not in the script"
    )
    assert verdict is Verdict.WARN


@pytest.mark.parametrize(
    ("obj", "call", "reason"),
    [
        (  # held: a story action, not the background
            {"name": "pen", "category": "other", "held": True},
            {"object": 1, "kind": "unscripted", "support": None},
            "unscripted",
        ),
        (  # an animal is never the background
            {"name": "dog", "category": "animal", "held": False},
            {"object": 1, "kind": "unscripted", "support": None},
            "unscripted",
        ),
        (  # a prop the extraction names, called unscripted: a story choice (T072)
            {"name": "map", "category": "other", "held": False},
            {"object": 1, "kind": "unscripted", "support": None},
            "unscripted",
        ),
        (  # the judge claimed a quote it can't show
            {"name": "pen", "category": "other", "held": False},
            {"object": 1, "kind": "scripted_prop", "support": "a pen nobody wrote"},
            "prop without support",
        ),
    ],
)
def test_the_rest_is_still_flagged_and_an_animal_stays_hard(
    screenplay: Screenplay,
    extraction: Extraction,
    obj: dict[str, Any],
    call: dict[str, Any],
    reason: str,
) -> None:
    failed, verdict = _objects(
        screenplay,
        extraction,
        _kitchen(screenplay),
        [{"name": "coat", "category": "clothing", "held": False}, obj],
        [{"object": 0, "kind": "scripted_prop", "support": "oilskin coat"}, call],
    )
    # T089: only an animal or a weapon stays hard; the rest warn with the same reason.
    story = obj["category"] in ("animal", "weapon")
    filed = Check.UNSCRIPTED_OBJECT if story else Check.BACKGROUND_OBJECT
    other = Check.BACKGROUND_OBJECT if story else Check.UNSCRIPTED_OBJECT
    assert failed[filed].endswith(reason)
    assert other not in failed
    assert verdict is (Verdict.FAIL if story else Verdict.WARN)


def test_background_object_is_soft(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(),
        judged(),
        extraction,
    )
    severity = {c.check: c.severity for c in checks}
    assert severity[Check.BACKGROUND_OBJECT] is Severity.SOFT
    assert Check.BACKGROUND_OBJECT.value == "background_object"


def test_a_scene_with_no_action_names_nothing() -> None:
    bare = dataclasses.replace(HARBOUR, elements=())
    assert named_in_scene("boats", ObjectCategory.VEHICLE, bare) is None
