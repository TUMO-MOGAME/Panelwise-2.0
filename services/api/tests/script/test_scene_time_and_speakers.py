"""resolve_times and match_speaker -- docs/design/script.md §6."""

import pytest

from app.script import Scene, absolute_time, match_speaker, parse_text, resolve_times

from .conftest import ACTION, Row, heading, layout


def scenes_with_times(*times: str) -> tuple[Scene, ...]:
    rows: list[Row] = []
    for i, time in enumerate(times, 1):
        slug = "INT. ROOM" + (f" - {time}" if time else "")
        rows += [heading(str(i), slug), None, (ACTION, "Something happens."), None]
    return parse_text(layout(rows)).scenes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NIGHT", "NIGHT"),
        ("night", "NIGHT"),
        ("CONTINUOUS", None),
        ("LATER", None),
        ("", None),
        (None, None),
        ("THREE WEEKS AGO", None),
    ],
)
def test_absolute_time(value: str | None, expected: str | None) -> None:
    assert absolute_time(value) == expected


def test_relative_times_borrow_the_nearest_earlier_clock() -> None:
    scenes = scenes_with_times("NIGHT", "CONTINUOUS", "", "DAWN", "LATER")
    assert resolve_times(scenes) == ["NIGHT", "NIGHT", "NIGHT", "DAWN", "DAWN"]


def test_nothing_upstream_means_none_not_a_guess() -> None:
    scenes = scenes_with_times("CONTINUOUS", "", "DAY")
    assert resolve_times(scenes) == [None, None, "DAY"]


CAST = ["THABO MOLEFE", "NANDI", "SIPHOKAZI", "MR ADRIAAN BOTHA"]


@pytest.mark.parametrize(
    ("cue", "expected"),
    [
        ("NANDI", "NANDI"),  # exact
        ("nandi", "NANDI"),  # case
        ("THABO", "THABO MOLEFE"),  # cue words ⊆ name words
        ("BOTHA", "MR ADRIAAN BOTHA"),
        ("MR. BOTHA", "MR ADRIAAN BOTHA"),  # punctuation
        ("SIPHO", None),  # not a substring match
        ("VOICE", None),  # nobody
        ("", None),
    ],
)
def test_match_speaker(cue: str, expected: str | None) -> None:
    assert match_speaker(cue, CAST) == expected


def test_an_ambiguous_cue_matches_nobody() -> None:
    assert match_speaker("THABO", ["THABO MOLEFE", "THABO SENIOR"]) is None
    assert match_speaker("NANDI", ["NANDI", "Nandi"]) is None
