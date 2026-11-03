"""run_checks / seed_for: verify.md §3 (the checks table, support, positions), §9. Pure."""

import dataclasses
import hashlib

import pytest

from app.grounding import Extraction
from app.script import IntExt, Screenplay
from app.shots import Framing, Shot
from app.verify import Check, CheckResult, Position, Severity, Verdict, run_checks, seed_for
from tests.verify.conftest import described, judged, kitchen_shot


def failing(checks: tuple[CheckResult, ...]) -> set[Check]:
    return {c.check for c in checks if not c.ok}


def test_a_frame_that_matches_its_shot_passes(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, positions = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judged(), extraction
    )
    assert verdict is Verdict.PASS
    assert failing(checks) == set()
    assert {c.check for c in checks} == set(Check)  # every check reports, pass or fail
    assert positions == {"NANDI": Position.LEFT}


def test_severities_follow_the_table(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, _, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judged(), extraction
    )
    hard = {
        Check.UNSCRIPTED_PERSON,
        Check.UNSCRIPTED_OBJECT,  # since T089 only an animal or a weapon
        Check.SETTING,
        Check.NO_CHARACTER,  # T080
        Check.DRAWN_SEX,  # T095
        Check.SPLIT_PANELS,  # T104
        Check.DRAWN_TWICE,  # T104
    }
    for c in checks:
        assert c.severity is (Severity.HARD if c.check in hard else Severity.SOFT), c.check


# --- people -----------------------------------------------------------------------------------


def test_two_people_called_as_one_character_puts_an_unscripted_person_on_screen(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(
        people=[
            {"position": "left", "appearance": "older woman"},
            {"position": "right", "appearance": "older woman"},
        ]
    )
    judgement = judged(
        people=[
            {"person": 0, "character": "NANDI", "support": None},
            {"person": 1, "character": "NANDI", "support": None},
        ]
    )
    checks, verdict, positions = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    assert verdict is Verdict.FAIL
    # The second NANDI is no character, described as the first: drawn twice too (T124).
    assert failing(checks) == {Check.UNSCRIPTED_PERSON, Check.DRAWN_TWICE}
    assert positions == {"NANDI": Position.LEFT}  # the first person called for her


def test_a_name_is_matched_like_a_speaker_cue(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    judgement = judged(people=[{"person": 0, "character": "Nandi", "support": None}])
    _, verdict, positions = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judgement, extraction
    )
    assert verdict is Verdict.PASS
    assert positions == {"NANDI": Position.LEFT}


@pytest.mark.parametrize(
    ("character", "support", "ok"),
    [
        ("MARIA", None, False),  # a name the script never gave
        ("THABO", None, False),  # in the script, not in this shot
        (None, None, False),  # nobody, and nothing puts them there
        (None, "a crowd gathers", False),  # a support the script doesn't say
        (None, "pours tea into two chipped mugs", True),  # verbatim from the shot's source
    ],
)
def test_a_person_who_is_no_shot_character_needs_verified_support(
    screenplay: Screenplay,
    extraction: Extraction,
    character: str | None,
    support: str | None,
    ok: bool,
) -> None:
    description = described(
        people=[
            {"position": "left", "appearance": "older woman"},
            {"position": "centre", "appearance": "a man"},
        ]
    )
    judgement = judged(
        people=[
            {"person": 0, "character": "NANDI", "support": None},
            {"person": 1, "character": character, "support": support},
        ]
    )
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    assert (Check.UNSCRIPTED_PERSON not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.FAIL)


def test_a_missing_character_only_warns(screenplay: Screenplay, extraction: Extraction) -> None:
    description = described(people=[])
    judgement = judged(people=[])
    checks, verdict, positions = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    assert failing(checks) == {Check.MISSING_CHARACTER}
    assert verdict is Verdict.WARN
    assert positions == {}


# --- the judgement's shape --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("people", "objects"),
    [
        ([], [{"object": 0, "kind": "scripted_prop", "support": "oilskin coat"}]),  # skipped
        (
            [
                {"person": 0, "character": "NANDI", "support": None},
                {"person": 0, "character": None, "support": None},
            ],
            [{"object": 0, "kind": "scripted_prop", "support": "oilskin coat"}],
        ),  # repeated
        (
            [{"person": 1, "character": "NANDI", "support": None}],
            [{"object": 0, "kind": "scripted_prop", "support": "oilskin coat"}],
        ),  # out of range
        (
            [{"person": 0, "character": "NANDI", "support": None}],
            [
                {"object": 0, "kind": "scripted_prop", "support": "oilskin coat"},
                {"object": 0, "kind": "unscripted", "support": None},
            ],
        ),  # an object repeated
        ([{"person": 0, "character": "NANDI", "support": None}], []),  # an object skipped
        (
            [{"person": 0, "character": "NANDI", "support": None}],
            [{"object": -1, "kind": "scripted_prop", "support": "oilskin coat"}],
        ),  # negative
    ],
)
def test_a_judgement_that_does_not_call_everything_exactly_once_is_an_error(
    screenplay: Screenplay,
    extraction: Extraction,
    people: list[dict[str, object]],
    objects: list[dict[str, object]],
) -> None:
    judgement = judged(people=people, objects=objects)
    checks, verdict, positions = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judgement, extraction
    )
    assert verdict is Verdict.ERROR
    assert checks == ()
    assert positions == {}


# --- objects ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("obj", "call", "ok"),
    [
        (
            {"name": "coat", "category": "clothing", "held": False},
            {"kind": "scripted_prop", "support": "OILSKIN   coat"},
            True,
        ),  # normalised match
        (
            {"name": "mugs", "category": "other", "held": True},
            {"kind": "scripted_prop", "support": "two chipped mugs"},
            True,
        ),  # from the source
        (
            {"name": "coat", "category": "clothing", "held": True},
            {"kind": "scripted_prop", "support": None},
            "warn",
        ),  # held (an unheld one is costume: T071); T089: warns, no animal or weapon
        (
            {"name": "knife", "category": "weapon", "held": True},
            {"kind": "scripted_prop", "support": "a kitchen knife"},
            False,
        ),  # not in the script
        (
            {"name": "map", "category": "other", "held": True},
            {"kind": "scripted_prop", "support": "holding a torn map"},
            "warn",
        ),  # THABO not in shot; T089: warns
        (
            {"name": "gun", "category": "weapon", "held": True},
            {"kind": "unscripted", "support": None},
            False,
        ),
        (
            {"name": "stove", "category": "furniture", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            True,
        ),  # heading words
        (
            {"name": "stove", "category": "furniture", "held": False},
            {"kind": "set_dressing", "support": "pours tea"},
            "warn",
        ),  # source, not the heading: an unheld everyday thing only warns (T083)
        (
            {"name": "stove", "category": "furniture", "held": False},
            {"kind": "set_dressing", "support": None},
            "warn",
        ),
        (
            {"name": "ladle", "category": "other", "held": True},
            {"kind": "set_dressing", "support": "kitchen"},
            "warn",
        ),  # held: a prop, not dressing; T089: warns
        (
            {"name": "cat", "category": "animal", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            False,
        ),
        (
            {"name": "car", "category": "vehicle", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            "warn",  # T089: a vehicle warns; only an animal or a weapon withholds
        ),
        (
            {"name": "rifle", "category": "weapon", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            False,
        ),
        (
            {"name": "poster", "category": "screen_or_sign", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            True,
        ),
        (
            {"name": "bread", "category": "food", "held": False},
            {"kind": "set_dressing", "support": "kitchen"},
            "warn",  # T086: unheld food warns, never passes as dressing
        ),
    ],
)
def test_objects(
    screenplay: Screenplay,
    extraction: Extraction,
    obj: dict[str, object],
    call: dict[str, object],
    ok: bool | str,
) -> None:
    description = described(objects=[obj])
    judgement = judged(objects=[{"object": 0, **call}])
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    if ok == "warn":  # T083: a background object; T089: any object but an animal or weapon
        assert Check.UNSCRIPTED_OBJECT not in failing(checks)
        assert Check.BACKGROUND_OBJECT in failing(checks)
        assert verdict is Verdict.WARN
        return
    assert (Check.UNSCRIPTED_OBJECT not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.FAIL)


def test_an_entity_quote_supports_only_when_its_entity_is_in_the_shot(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(objects=[{"name": "map", "category": "other", "held": True}])
    judgement = judged(
        objects=[{"object": 0, "kind": "scripted_prop", "support": "holding a torn map"}]
    )
    shot = kitchen_shot(characters=("NANDI", "THABO"))
    checks, _, _ = run_checks(shot, screenplay.scenes[0], description, judgement, extraction)
    assert Check.UNSCRIPTED_OBJECT not in failing(checks)


# --- code-decided checks ----------------------------------------------------------------------


def test_text_in_frame_warns(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(has_text=True, text=["SALE"]),
        judged(),
        extraction,
    )
    assert failing(checks) == {Check.TEXT_IN_FRAME}
    assert verdict is Verdict.WARN  # T089: soft


# --- T071: legible text fails only when it isn't the script's words ---------------------------


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (["LIGHTHOUSE KITCHEN"], True),  # the scene's location (INT. LIGHTHOUSE KITCHEN - NIGHT)
        (["Lighthouse"], True),  # part of it, any case
        (["chipped mugs"], True),  # words of the shot's source
        (["LIGHTHOUSE KITCHEN", "chipped mugs"], True),
        (["LIGHTHUOSE KITCHN"], False),  # a garbled sign
        (["J. Smith"], False),  # a readable signature
        (["NIGHT"], False),  # the heading's time of day is not script words for a wall
        (["LIGHTHOUSE KITCHEN", "SALE"], False),  # one stray word is enough
    ],
)
def test_text_passes_only_as_the_script_s_own_words(
    screenplay: Screenplay, extraction: Extraction, text: list[str], ok: bool
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(has_text=True, text=text),
        judged(),
        extraction,
    )
    assert (Check.TEXT_IN_FRAME not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.WARN)  # T089: soft


def test_a_failed_text_check_names_each_stray_text(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(has_text=True, text=["LIGHTHOUSE KITCHEN", "SALE", "J. Smith"]),
        judged(),
        extraction,
    )
    detail = next(c.detail for c in checks if c.check is Check.TEXT_IN_FRAME)
    assert "SALE" in detail and "J. Smith" in detail and "LIGHTHOUSE" not in detail


def test_marks_the_describer_could_not_read_pass(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(has_text=True, text=[]),
        judged(),
        extraction,
    )
    assert Check.TEXT_IN_FRAME not in failing(checks)
    assert verdict is Verdict.PASS


# --- T071: costume and the place's structure ----------------------------------------------------


@pytest.mark.parametrize("category", ["clothing", "architecture"])
@pytest.mark.parametrize(
    "call",
    [
        {"kind": "unscripted", "support": None},
        {"kind": "set_dressing", "support": None},
        {"kind": "scripted_prop", "support": "not in the script at all"},
    ],
)
def test_worn_clothes_and_the_place_s_structure_are_never_unscripted(
    screenplay: Screenplay, extraction: Extraction, category: str, call: dict[str, object]
) -> None:
    objects = [{"name": "coat", "category": "clothing", "held": False}]
    objects.append(
        {
            "name": "jacket" if category == "clothing" else "chimney",
            "category": category,
            "held": False,
        }
    )
    judgement = judged(
        objects=[
            {"object": 0, "kind": "scripted_prop", "support": "oilskin coat"},
            {"object": 1, **call},
        ]
    )
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(objects=objects), judgement, extraction
    )
    assert Check.UNSCRIPTED_OBJECT not in failing(checks)
    assert verdict is Verdict.PASS


@pytest.mark.parametrize("category", ["clothing", "architecture"])
def test_a_held_costume_or_structure_object_is_still_checked(
    screenplay: Screenplay, extraction: Extraction, category: str
) -> None:
    objects = [{"name": "scarf", "category": category, "held": True}]
    judgement = judged(objects=[{"object": 0, "kind": "unscripted", "support": None}])
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(objects=objects), judgement, extraction
    )
    assert Check.BACKGROUND_OBJECT in failing(checks)  # T089: checked, and warns
    assert verdict is Verdict.WARN


@pytest.mark.parametrize(
    ("int_ext", "setting", "ok"),
    [
        (IntExt.INT, "interior", True),
        (IntExt.INT, "exterior", False),
        (IntExt.EXT, "interior", False),
        (IntExt.EXT, "exterior", True),
        (IntExt.INT_EXT, "interior", True),
        (IntExt.INT_EXT, "exterior", True),
        (IntExt.INT, "unclear", True),
        (IntExt.EXT, "unclear", True),
    ],
)
def test_setting(
    screenplay: Screenplay, extraction: Extraction, int_ext: IntExt, setting: str, ok: bool
) -> None:
    scene = dataclasses.replace(screenplay.scenes[0], int_ext=int_ext)
    checks, verdict, _ = run_checks(
        kitchen_shot(), scene, described(setting=setting), judged(), extraction
    )
    assert (Check.SETTING not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.FAIL)


@pytest.mark.parametrize(
    ("time", "light", "ok"),
    [
        *((t, "day", False) for t in ("NIGHT", "MIDNIGHT", "EVENING")),
        *((t, "night", True) for t in ("NIGHT", "MIDNIGHT", "EVENING")),
        *((t, "night", False) for t in ("DAY", "MORNING", "AFTERNOON")),
        *((t, "day", True) for t in ("DAY", "MORNING", "AFTERNOON")),
        *(
            (t, light, True)
            for t in ("DAWN", "DUSK", "SUNRISE", "SUNSET", "MAGIC HOUR", None)
            for light in ("day", "night")
        ),
        *((t, "dawn_or_dusk", True) for t in ("NIGHT", "DAY")),
        *((t, "unclear", True) for t in ("NIGHT", "DAY")),
    ],
)
def test_light_is_soft(
    screenplay: Screenplay, extraction: Extraction, time: str | None, light: str, ok: bool
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(time_of_day=time),
        screenplay.scenes[0],
        described(light=light),
        judged(),
        extraction,
    )
    assert (Check.LIGHT not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.WARN)


@pytest.mark.parametrize(
    ("framing", "size", "ok"),
    [
        (Framing.WIDE, "medium", True),
        (Framing.WIDE, "close", False),
        (Framing.WIDE, "extreme_close", False),
        (Framing.MEDIUM, "extreme_close", False),
        (Framing.MEDIUM, "close", True),
        (Framing.CLOSE_UP, "wide", False),
        (Framing.EXTREME_CLOSE_UP, "medium", False),
        (Framing.EXTREME_CLOSE_UP, "close", True),
        (Framing.OVER_SHOULDER, "extreme_close", False),  # counts as medium
        (Framing.POV, "wide", True),  # counts as medium
        (Framing.INSERT, "wide", False),  # counts as close
        (Framing.INSERT, "extreme_close", True),
        (Framing.WIDE, "unclear", True),
    ],
)
def test_framing_is_soft(
    screenplay: Screenplay, extraction: Extraction, framing: Framing, size: str, ok: bool
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(framing=framing),
        screenplay.scenes[0],
        described(shot_size=size),
        judged(),
        extraction,
    )
    assert (Check.FRAMING not in failing(checks)) is ok
    assert verdict is (Verdict.PASS if ok else Verdict.WARN)


def test_a_hard_failure_outranks_a_soft_one(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(setting="exterior", light="day"),  # T089: text is soft, so a wrong setting
        judged(),
        extraction,
    )
    assert failing(checks) == {Check.SETTING, Check.LIGHT}
    assert verdict is Verdict.FAIL


def test_details_name_the_offender_without_quoting_the_script(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(objects=[{"name": "gun", "category": "weapon", "held": True}])
    judgement = judged(objects=[{"object": 0, "kind": "unscripted", "support": None}])
    checks, _, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    detail = next(c.detail for c in checks if c.check is Check.UNSCRIPTED_OBJECT)
    assert "gun" in detail


# --- seeds ------------------------------------------------------------------------------------


def test_seeds_are_deterministic_per_shot_and_attempt() -> None:
    shot: Shot = kitchen_shot()
    expected = int.from_bytes(hashlib.sha256(b"0:1:2").digest()[:4], "big")
    assert seed_for(shot, 2) == expected
    assert seed_for(shot, 2) == seed_for(kitchen_shot(), 2)
    assert len({seed_for(shot, a) for a in (1, 2, 3)}) == 3
    assert 0 <= seed_for(shot, 1) < 2**32


@pytest.mark.parametrize("text", [[""], ["  "], ["", "LIGHTHOUSE KITCHEN"]])
def test_an_empty_text_entry_is_no_text_read(
    screenplay: Screenplay, extraction: Extraction, text: list[str]
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(text=text), judged(), extraction
    )
    assert Check.TEXT_IN_FRAME not in failing(checks)
    assert verdict is Verdict.PASS


# --- T077: a signature warns (T072 failed it) ----------------------------------------------------


def test_a_signature_alone_warns_and_withholds_nothing(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(signature=True, text=[]),
        judged(),
        extraction,
    )
    assert failing(checks) == {Check.SIGNATURE}
    assert verdict is Verdict.WARN
    result = next(c for c in checks if c.check is Check.SIGNATURE)
    assert result.severity is Severity.SOFT
    assert "a signature" in result.detail


def test_a_signature_with_an_unscripted_word_still_names_the_word(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(signature=True, text=["@hutley"]),
        judged(),
        extraction,
    )
    assert failing(checks) == {Check.SIGNATURE, Check.TEXT_IN_FRAME}
    assert verdict is Verdict.WARN  # T089: both soft


def test_no_signature_and_no_text_passes(screenplay: Screenplay, extraction: Extraction) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(signature=False, text=[]),
        judged(),
        extraction,
    )
    assert Check.TEXT_IN_FRAME not in failing(checks)
    assert verdict is Verdict.PASS


# --- T072 review: a character's quote supports no stranger; a named prop is never dressing ---


def test_a_quote_naming_a_shot_character_supports_no_stranger(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    """A child Lerato drawn as an adult: the judge refuses the match, then can't excuse the stranger
    with Lerato's own quote. Here: NANDI's quote for a person who isn't Nandi."""
    judgement = judged(
        people=[{"person": 0, "character": None, "support": "NANDI (60s, oilskin coat)"}]
    )
    checks, verdict, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judgement, extraction
    )
    assert Check.UNSCRIPTED_PERSON in failing(checks)
    assert verdict is Verdict.FAIL


def test_a_quote_naming_no_character_still_supports_a_stranger(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    judgement = judged(people=[{"person": 0, "character": None, "support": "pours tea"}])
    checks, _, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], described(), judgement, extraction
    )
    assert Check.UNSCRIPTED_PERSON not in failing(checks)


@pytest.mark.parametrize(
    ("name", "ok"),
    [("map", False), ("torn map", False), ("bucket", True), ("cup of tea", True)],
)
def test_a_thing_the_script_names_is_never_set_dressing(
    screenplay: Screenplay, extraction: Extraction, name: str, ok: bool
) -> None:
    """The extraction names the prop "torn map": a map called set dressing is a story choice."""
    description = described(objects=[{"name": name, "category": "other", "held": False}])
    judgement = judged(objects=[{"object": 0, "kind": "set_dressing", "support": "kitchen"}])
    checks, _, _ = run_checks(
        kitchen_shot(), screenplay.scenes[0], description, judgement, extraction
    )
    detail = next(c.detail for c in checks if c.check is Check.BACKGROUND_OBJECT)
    assert Check.UNSCRIPTED_OBJECT not in failing(checks)  # T089: it warns, naming why
    assert detail.endswith("the script names it") is not ok
