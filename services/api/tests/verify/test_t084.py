"""T084: a person's support is an action line with no he, him or she
(docs/design/verify.md §3, §6, §9)."""

import pytest

from app.grounding import Extraction
from app.script import Action, Dialogue, IntExt, Scene, Screenplay, Span
from app.shots import Framing, Movement, Shot
from app.verify import Check, Verdict, run_checks
from app.verify.audit import shot_action_text
from tests.verify.conftest import described, judged, kitchen_shot

PLATFORM = Scene(
    index=0,
    number="5",
    heading="INT. PLATFORM NINE -- NIGHT",
    int_ext=IntExt.INT,
    location="PLATFORM NINE",
    time_of_day="NIGHT",
    elements=(
        Action(
            "A long covered platform. KOOS (70s) pushes a broom. A SLEEPING COMMUTER lies "
            "across a bench under a newspaper.",
            Span(5, 1, 2),
        ),
        Dialogue("KOOS", None, None, "Somebody might have. Leave him be.", Span(5, 3, 4)),
        Action("A pigeon glares at him. He's already gone. She waves.", Span(5, 5, 5)),
        Action("Passengers hurry past. They ignore him.", Span(5, 6, 6)),
        Action("A WOMAN, 40s, folds her umbrella.", Span(5, 7, 7)),
        Action("Where the shadows gather, a figure waits.", Span(5, 8, 8)),
        Action("A MAN shaves himself and folds his towel. A guard says she left.", Span(5, 9, 9)),
    ),
    span=Span(5, 1, 9),
)


def _shot(elements: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)) -> Shot:
    return Shot(
        scene_index=0,
        number=1,
        framing=Framing.WIDE,
        movement=Movement.STATIC,
        elements=elements,
        characters=("KOOS",),
        props=(),
        time_of_day="NIGHT",
        rationale="Koos on the platform.",
        span=Span(5, 1, 9),
        source=" ".join(PLATFORM.elements[i].text for i in elements),
    )


def _stranger(support: str | None, extraction: Extraction) -> tuple[str | None, Verdict]:
    """Koos matched, and one stranger supported by `support`: the UNSCRIPTED_PERSON detail."""
    checks, verdict, _ = run_checks(
        _shot(),
        PLATFORM,
        described(
            people=[
                {"position": "left", "appearance": "an old man with a broom"},
                {"position": "right", "appearance": "a small distant adult figure"},
            ],
            objects=[],
        ),
        judged(
            people=[
                {"person": 0, "character": "KOOS", "support": None},
                {"person": 1, "character": None, "support": support},
            ],
            objects=[],
        ),
        extraction,
    )
    failed = {c.check: c.detail for c in checks if not c.ok}
    return failed.get(Check.UNSCRIPTED_PERSON), verdict


def test_shot_action_text_joins_only_the_action_elements_in_order() -> None:
    text = shot_action_text(_shot((0, 1, 2)), PLATFORM)
    assert "PUSHES A BROOM" in text
    assert "A PIGEON GLARES AT HIM" in text
    assert text.index("BROOM") < text.index("PIGEON")
    assert "SOMEBODY MIGHT HAVE" not in text  # dialogue


def test_shot_action_text_is_empty_for_a_shot_of_dialogue_alone() -> None:
    assert shot_action_text(_shot((1,)), PLATFORM) == ""


def test_a_stranger_supported_by_a_line_of_dialogue_fails(extraction: Extraction) -> None:
    detail, verdict = _stranger("Somebody might have.", extraction)
    assert detail is not None
    assert "its support is not an action line" in detail
    assert "a small distant adult figure" in detail
    assert verdict is Verdict.FAIL


def test_dialogue_with_him_fails_as_not_an_action_line_first(extraction: Extraction) -> None:
    detail, _ = _stranger("Leave him be.", extraction)
    assert detail is not None
    assert "its support is not an action line" in detail
    assert "points at someone else" not in detail


@pytest.mark.parametrize(
    "support",
    [
        "A pigeon glares at him.",
        "He's already gone.",
        "She waves.",
        "They ignore him.",
        "A guard says she left.",  # mid-sentence
    ],
)
def test_a_support_with_he_him_or_she_points_at_someone_else(
    support: str, extraction: Extraction
) -> None:
    detail, verdict = _stranger(support, extraction)
    assert detail is not None
    assert "its support points at someone else" in detail
    assert verdict is Verdict.FAIL


@pytest.mark.parametrize(
    "support",
    [
        "A SLEEPING COMMUTER lies across a bench under a newspaper.",
        "A WOMAN, 40s, folds her umbrella.",  # her own possessive
        "A MAN shaves himself and folds his towel.",  # his, himself alone
        "Passengers hurry past.",
        "Passengers hurry past. They",  # they alone
        "Where the shadows gather, a figure waits.",  # "he" inside "the", "where"
    ],
)
def test_a_stranger_the_action_introduces_passes(support: str, extraction: Extraction) -> None:
    detail, _ = _stranger(support, extraction)
    assert detail is None


def test_a_support_found_nowhere_still_fails_as_before(extraction: Extraction) -> None:
    detail, _ = _stranger("A soldier stands guard.", extraction)
    assert detail is not None
    assert "no shot character, no support" in detail


def test_a_support_naming_a_character_still_fails_as_about_a_character(
    extraction: Extraction,
) -> None:
    detail, _ = _stranger("KOOS (70s) pushes a broom.", extraction)
    assert detail is not None
    assert "its support is about a character" in detail


def test_an_entity_quote_outside_the_shots_action_text_no_longer_supports(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # "holding a torn map" is THABO's quote, an in-shot entity, but not in this shot's action.
    checks, _, _ = run_checks(
        kitchen_shot(characters=("NANDI", "THABO")),
        screenplay.scenes[0],
        described(
            people=[
                {"position": "left", "appearance": "older woman"},
                {"position": "right", "appearance": "a young man"},
            ]
        ),
        judged(
            people=[
                {"person": 0, "character": "NANDI", "support": None},
                {"person": 1, "character": None, "support": "holding a torn map"},
            ]
        ),
        extraction,
    )
    failed = {c.check: c.detail for c in checks if not c.ok}
    assert "its support is not an action line" in failed[Check.UNSCRIPTED_PERSON]


def test_a_matched_character_is_unaffected(extraction: Extraction) -> None:
    checks, _, positions = run_checks(
        _shot(),
        PLATFORM,
        described(people=[{"position": "left", "appearance": "an old man"}], objects=[]),
        judged(people=[{"person": 0, "character": "KOOS", "support": None}], objects=[]),
        extraction,
    )
    assert Check.UNSCRIPTED_PERSON not in {c.check for c in checks if not c.ok}
    assert positions == {"KOOS": "left"}
