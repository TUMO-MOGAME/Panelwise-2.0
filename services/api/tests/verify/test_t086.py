"""T086: a matched person's age in code; inside a vehicle its parts are the place; unheld food
warns (docs/design/verify.md §3, §6, §9)."""

import pytest

from app.grounding import Extraction
from app.script import Action, IntExt, Scene, Screenplay, Span, parse_text
from app.storyboard.prompt import introduced_years
from app.verify import Check, Verdict, run_checks
from app.verify.audit import (
    age_contradicts,
    described_age,
    inside_vehicle,
    part_of_vehicle,
    shot_ages,
)
from app.verify.model import ObjectCategory
from tests.verify.conftest import described, judged, kitchen_shot


def _scene(heading: str, int_ext: IntExt, location: str) -> Scene:
    return Scene(
        index=0,
        number="3",
        heading=heading,
        int_ext=int_ext,
        location=location,
        time_of_day="DAWN",
        elements=(Action("Daniel drives. Theo sits beside him.", Span(3, 1, 1)),),
        span=Span(3, 1, 1),
    )


VAN = _scene("INT. VAN - MOVING - DAWN", IntExt.INT, "VAN - MOVING")
BAKERY = _scene("INT. NOMSA'S BAKERY - DAY", IntExt.INT, "NOMSA'S BAKERY")


@pytest.mark.parametrize(
    ("appearance", "age"),
    [
        ("a child, a boy with short dark hair", "child"),
        ("an old man with white hair, looking toward the girl", "old"),
        ("a 10-year-old girl with braids", "child"),
        ("an older woman in a cardigan", "adult"),  # "older" is no age: DANIEL (40s)
        ("a mother holding a child", "adult"),
        ("a grandmother with a shawl", "old"),
        ("an elderly man with a cane", "old"),
        ("a teenager with dark hair", "teenager"),
        ("an adult seen from behind", "adult"),
        ("an adult woman holding a tray", "adult"),
        ("a figure in a coat", None),
    ],
)
def test_described_age(appearance: str, age: str | None) -> None:
    assert described_age(appearance) == age


@pytest.mark.parametrize(
    ("years", "described", "contradicts"),
    [
        (9, "adult", True),
        (9, "old", True),
        (9, "teenager", False),
        (9, "child", False),
        (17, "old", True),
        (17, "child", False),
        (40, "old", True),
        (40, "child", True),
        (40, "teenager", False),
        (70, "child", True),
        (70, "teenager", True),
        (70, "adult", False),
        (40, None, False),
    ],
)
def test_age_contradicts(years: int, described: str | None, contradicts: bool) -> None:
    assert age_contradicts(years, described) is contradicts


def _match(
    appearance: str, extraction: Extraction, screenplay: Screenplay, ages: dict[str, int] | None
):
    return run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=[{"position": "left", "appearance": appearance}]),
        judged(),
        extraction,
        ages=ages,
    )


def test_a_contradicted_age_fails_and_the_character_is_not_placed(
    extraction: Extraction, screenplay: Screenplay
) -> None:
    checks, verdict, positions = _match(
        "an adult seen from behind", extraction, screenplay, {"NANDI": 9}
    )
    failed = {c.check: c.detail for c in checks if not c.ok}
    assert "described as adult, but NANDI is introduced at 9" in failed[Check.UNSCRIPTED_PERSON]
    assert "NANDI" not in positions
    assert verdict is Verdict.FAIL


def test_a_fitting_age_passes(extraction: Extraction, screenplay: Screenplay) -> None:
    checks, _, positions = _match("a child, a girl", extraction, screenplay, {"NANDI": 9})
    assert Check.UNSCRIPTED_PERSON not in {c.check for c in checks if not c.ok}
    assert positions == {"NANDI": "left"}


def test_without_ages_nothing_changes(extraction: Extraction, screenplay: Screenplay) -> None:
    checks, _, positions = _match("an adult seen from behind", extraction, screenplay, None)
    assert Check.UNSCRIPTED_PERSON not in {c.check for c in checks if not c.ok}
    assert positions == {"NANDI": "left"}


@pytest.mark.parametrize(
    ("location", "int_ext", "words"),
    [
        ("VAN - MOVING", IntExt.INT, {"van"}),
        ("SIPHO'S BAKKIE", IntExt.INT, {"bakkie"}),
        ("VAN", IntExt.EXT, set[str]()),
        ("NOMSA'S BAKERY", IntExt.INT, set[str]()),
        ("BUS STATION", IntExt.INT, set[str]()),  # a place named after a vehicle, not inside one
        ("CAR PARK - LEVEL 2", IntExt.INT, set[str]()),
        ("TAXI RANK", IntExt.INT, set[str]()),
    ],
)
def test_inside_vehicle(location: str, int_ext: IntExt, words: set[str]) -> None:
    assert inside_vehicle(_scene(f"INT. {location}", int_ext, location)) == words


@pytest.mark.parametrize(
    ("name", "scene", "part"),
    [
        ("steering wheel", VAN, True),
        ("rearview mirror", VAN, True),
        ("dashboard", VAN, True),
        ("headrests", VAN, True),
        ("car seats", VAN, True),
        ("sailboat", VAN, False),  # a bare vehicle is judged as before
        ("car", VAN, False),
        ("van", VAN, False),
        ("second van", VAN, False),  # a copy word
        ("steering wheel", BAKERY, False),  # not inside a vehicle
        ("pistol barrel", VAN, False),  # a weapon's part, not the van's
        ("dog collar", VAN, False),
    ],
)
def test_part_of_vehicle(name: str, scene: Scene, part: bool) -> None:
    category = {"pistol barrel": ObjectCategory.WEAPON, "dog collar": ObjectCategory.ANIMAL}.get(
        name, ObjectCategory.VEHICLE
    )
    assert part_of_vehicle(name, category, scene) is part


def _objects(
    scene: Scene,
    objects: list[dict[str, object]],
    calls: list[dict[str, object]],
    extraction: Extraction,
):
    checks, verdict, _ = run_checks(
        kitchen_shot(), scene, described(objects=objects), judged(objects=calls), extraction
    )
    return {c.check: c.detail for c in checks if not c.ok}, verdict


def test_inside_the_van_its_wheel_and_dashboard_pass(extraction: Extraction) -> None:
    failed, _ = _objects(
        VAN,
        [
            {"name": "steering wheel", "category": "other", "held": True},
            {"name": "dashboard", "category": "vehicle", "held": False},
        ],
        [
            {"object": 0, "kind": "set_dressing", "support": "VAN"},
            {"object": 1, "kind": "set_dressing", "support": "VAN"},
        ],
        extraction,
    )
    assert Check.UNSCRIPTED_OBJECT not in failed


@pytest.mark.parametrize(
    "call",
    [{"kind": "set_dressing", "support": "BAKERY"}, {"kind": "unscripted", "support": None}],
)
def test_unheld_food_warns_whatever_the_judge_called_it(
    call: dict[str, object], extraction: Extraction
) -> None:
    failed, verdict = _objects(
        BAKERY,
        [{"name": "bread loaves", "category": "food", "held": False}],
        [{"object": 0, **call}],
        extraction,
    )
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert "bread loaves" in failed[Check.BACKGROUND_OBJECT]
    assert verdict is Verdict.WARN


def test_held_food_warns_as_held(extraction: Extraction) -> None:
    failed, _ = _objects(
        BAKERY,
        [{"name": "bun", "category": "food", "held": True}],
        [{"object": 0, "kind": "set_dressing", "support": "BAKERY"}],
        extraction,
    )
    assert "held, so not set dressing" in failed[Check.BACKGROUND_OBJECT]  # T089


def test_food_the_scene_names_still_passes(extraction: Extraction) -> None:
    named = Scene(
        index=0,
        number="1",
        heading="INT. NOMSA'S BAKERY - NIGHT",
        int_ext=IntExt.INT,
        location="NOMSA'S BAKERY",
        time_of_day="NIGHT",
        elements=(Action("Trays of bread rolls cool on a steel rack.", Span(1, 1, 1)),),
        span=Span(1, 1, 1),
    )
    failed, _ = _objects(
        named,
        [{"name": "bread rolls", "category": "food", "held": False}],
        [{"object": 0, "kind": "set_dressing", "support": "BAKERY"}],
        extraction,
    )
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert Check.BACKGROUND_OBJECT not in failed


def test_an_age_refused_match_is_never_excused_as_a_stranger(
    extraction: Extraction, screenplay: Screenplay
) -> None:
    checks, _, positions = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=[{"position": "left", "appearance": "an adult seen from behind"}]),
        judged(people=[{"person": 0, "character": "NANDI", "support": "Rain hammers the window."}]),
        extraction,
        ages={"NANDI": 9},
    )
    failed = {c.check: c.detail for c in checks if not c.ok}
    assert "described as adult, but NANDI is introduced at 9" in failed[Check.UNSCRIPTED_PERSON]
    assert positions == {}


@pytest.mark.parametrize(
    ("line", "years"),
    [
        ("THEO (9), in pyjamas, sleeps.", 9),
        ("THEO (9 years old) sleeps.", 9),
        ("DANIEL (40s), a tall driver, climbs out.", 40),
        ("THEO (5 months) sleeps.", None),
    ],
)
def test_introduced_years(line: str, years: int | None) -> None:
    screenplay = parse_text(f"INT. ROOM - NIGHT\n\n{line}\n", [])
    assert introduced_years(line.split(" (")[0], screenplay) == years


def test_shot_ages_keeps_only_characters_with_an_age(screenplay: Screenplay) -> None:
    years = {"NANDI": 60}
    assert shot_ages(
        kitchen_shot(characters=("NANDI", "THABO")), screenplay, lambda c, _: years.get(c)
    ) == {"NANDI": 60}


@pytest.mark.parametrize(
    ("support", "fails"), [("pours tea into two chipped mugs", False), ("a loaf of rye", True)]
)
def test_a_scripted_food_prop_needs_its_support(
    support: str, fails: bool, extraction: Extraction
) -> None:
    scene = Scene(
        index=0,
        number="1",
        heading="INT. NOMSA'S BAKERY - NIGHT",
        int_ext=IntExt.INT,
        location="NOMSA'S BAKERY",
        time_of_day="NIGHT",
        elements=(Action("Nomsa slices the bread.", Span(1, 1, 1)),),
        span=Span(1, 1, 1),
    )
    checks, _, _ = run_checks(
        kitchen_shot(),
        scene,
        described(objects=[{"name": "loaf", "category": "food", "held": False}]),
        judged(objects=[{"object": 0, "kind": "scripted_prop", "support": support}]),
        extraction,
    )
    failed = {c.check: c.detail for c in checks if not c.ok}
    assert (Check.BACKGROUND_OBJECT in failed) is fails  # T089: food warns, unsupported
    assert Check.UNSCRIPTED_OBJECT not in failed
