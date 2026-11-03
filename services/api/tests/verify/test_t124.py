"""T124: a pair the describer described alike, not both known as characters, is one person drawn
twice (verify.md §3 *Described alike*, § T124 contracts, §9 T124). Pure, no network."""

from typing import Any

import pytest

from app.grounding import Extraction
from app.script import Screenplay
from app.verify import Check
from app.verify.audit import ALIKE_OVERLAP, described_alike
from app.verify.model import FrameLayout, PersonFound
from tests.verify.conftest import described
from tests.verify.test_t104 import MATCHED, ONE_MATCHED, checks_for


def people(*appearances: str) -> list[dict[str, Any]]:
    return [{"position": "left", "appearance": a} for a in appearances]


def alike(*appearances: str, known: set[int] | None = None) -> tuple[tuple[int, int], ...]:
    return described_alike(described(people=people(*appearances)), known or set())


CHILD = "a child in a short-sleeved shirt and shorts"  # gogos-recipe 2.1's two children, verbatim
ADULT = "an adult in a button-up shirt and trousers"


def test_the_threshold_is_the_measured_one() -> None:
    assert ALIKE_OVERLAP == 0.5


def test_the_same_words_are_alike() -> None:
    assert alike(CHILD, CHILD) == ((0, 1),)


def test_different_people_are_not() -> None:
    assert alike(CHILD, ADULT) == ()


def test_half_the_words_shared_is_alike_and_just_under_is_not() -> None:
    assert alike("tall red coat", "tall red hat") == ((0, 1),)  # 2 of 4 words: 0.5 exactly
    assert alike("tall red coat", "tall blue hat") == ()  # 1 of 5: 0.2
    assert alike("tall red coat scarf", "tall red hat boots") == ()  # 2 of 6: 0.33


def test_case_punctuation_and_stop_words_are_ignored() -> None:
    assert alike("A Boy, in the Blazer.", "boy blazer") == ((0, 1),)
    assert alike("a the with", "an and of") == ()  # nothing left: 0.0, never alike


def test_a_pair_both_known_is_two_characters() -> None:
    assert alike(CHILD, CHILD, known={0, 1}) == ()


def test_one_known_or_neither_is_still_a_copy() -> None:
    assert alike(CHILD, CHILD, known={0}) == ((0, 1),)
    assert alike(CHILD, CHILD, known={1}) == ((0, 1),)


def test_three_alike_people_are_three_sorted_pairs() -> None:
    assert alike(CHILD, ADULT, CHILD, CHILD) == ((0, 2), (0, 3), (2, 3))


# --- run_checks ---------------------------------------------------------------------------------

TWINS = [
    {"position": "left", "appearance": CHILD},
    {"position": "centre", "appearance": CHILD},
]
DETAIL = (
    f"person 0 (left, {CHILD}) and person 1 (centre, {CHILD}): "
    "described alike, one of them no character"
)


@pytest.mark.parametrize(
    "layout", [None, FrameLayout(1, (), "different faces, hair, and clothing details")]
)
def test_alike_fails_drawn_twice_with_or_without_a_layout_answer(
    screenplay: Screenplay, extraction: Extraction, layout: FrameLayout | None
) -> None:
    checks, _ = checks_for(screenplay, extraction, layout, people=TWINS, calls_=ONE_MATCHED)
    assert not checks[Check.DRAWN_TWICE].ok
    assert checks[Check.DRAWN_TWICE].detail == DETAIL


def test_a_pair_in_both_fails_once_with_the_layout_s_detail(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    layout = FrameLayout(1, ((0, 1),), "the same child")
    checks, _ = checks_for(screenplay, extraction, layout, people=TWINS, calls_=ONE_MATCHED)
    assert checks[Check.DRAWN_TWICE].detail == (
        f"person 0 (left, {CHILD}) and person 1 (centre, {CHILD}): the same person drawn twice"
    )


def test_a_split_frame_is_split_panels_alone(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, _ = checks_for(screenplay, extraction, FrameLayout(2, (), "r"), people=TWINS)
    assert not checks[Check.SPLIT_PANELS].ok
    assert checks[Check.DRAWN_TWICE].ok


@pytest.mark.parametrize(
    ("calls_", "found"),
    [
        (MATCHED, []),  # both accepted: two characters who look alike
        (None, [PersonFound("NANDI", 0, "r"), PersonFound("THABO", 1, "r")]),  # both found
    ],
)
def test_alike_characters_pass(
    screenplay: Screenplay,
    extraction: Extraction,
    calls_: list[dict[str, Any]] | None,
    found: list[PersonFound],
) -> None:
    checks, _ = checks_for(screenplay, extraction, None, people=TWINS, calls_=calls_, found=found)
    assert checks[Check.DRAWN_TWICE].ok


def test_unlike_people_pass_without_a_layout_answer(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    unlike = [{"position": "left", "appearance": CHILD}, {"position": "right", "appearance": ADULT}]
    checks, _ = checks_for(screenplay, extraction, None, people=unlike)
    assert checks[Check.DRAWN_TWICE].ok


# --- a scripted crowd (review of #222) -----------------------------------------------------------

EXTRA = "Rain hammers the window."  # an action line of the kitchen shot, naming no character


def extra(person: int, support: str | None = EXTRA) -> dict[str, Any]:
    return {"person": person, "character": None, "support": support}


def test_two_alike_scripted_extras_are_a_crowd(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, _ = checks_for(screenplay, extraction, None, people=TWINS, calls_=[extra(0), extra(1)])
    assert checks[Check.UNSCRIPTED_PERSON].ok  # both scripted
    assert checks[Check.DRAWN_TWICE].ok


def test_a_character_and_an_alike_extra_is_still_a_copy(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    calls_ = [{"person": 0, "character": "NANDI", "support": None}, extra(1)]
    checks, _ = checks_for(screenplay, extraction, None, people=TWINS, calls_=calls_)
    assert not checks[Check.DRAWN_TWICE].ok


def test_alike_people_whose_support_fails_are_a_copy(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, _ = checks_for(
        screenplay, extraction, None, people=TWINS, calls_=[extra(0), extra(1, "not in the script")]
    )
    assert not checks[Check.UNSCRIPTED_PERSON].ok
    assert not checks[Check.DRAWN_TWICE].ok


def test_a_layout_pair_of_two_extras_keeps_t104_s_veto(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    # T104 vetoes characters only: the layout agent's own pair of two extras still fails.
    layout = FrameLayout(1, ((0, 1),), "the same child")
    checks, _ = checks_for(
        screenplay, extraction, layout, people=TWINS, calls_=[extra(0), extra(1)]
    )
    assert not checks[Check.DRAWN_TWICE].ok
    assert checks[Check.DRAWN_TWICE].detail.endswith("the same person drawn twice")
