"""The prompt's per-screenplay caches (#165): one scan per screenplay or extraction object, and
an equal but different object is scanned again, never served another's entry."""

from app.characters import labels
from app.characters.labels import animals
from app.storyboard import prompt
from app.storyboard.prompt import introduced_age
from tests.script.conftest import ACTION, heading
from tests.storyboard.conftest import extraction_of, screenplay_of

ROWS = [heading("1", "INT. ROOM - DAY"), None, (ACTION, "NANDI (60s), oilskin coat, pours tea.")]


def test_introductions_are_scanned_once_per_screenplay() -> None:
    sp = screenplay_of(ROWS)
    first = introduced_age("NANDI", sp)
    entry = prompt._intro_cache[0]  # pyright: ignore[reportPrivateUsage]
    assert entry[0] is sp and "NANDI" in entry[1]
    assert introduced_age("NANDI", sp) == first
    assert prompt._intro_cache[0] is entry  # pyright: ignore[reportPrivateUsage]
    other = screenplay_of(ROWS)  # equal text, a different object: scanned again
    assert introduced_age("NANDI", other) == first
    assert prompt._intro_cache[0][0] is other  # pyright: ignore[reportPrivateUsage]


def test_name_words_are_scanned_once_per_screenplay() -> None:
    sp = screenplay_of(ROWS)
    words = prompt._name_words(sp)  # pyright: ignore[reportPrivateUsage]
    assert "nandi" in words
    assert prompt._name_words(sp) is words  # pyright: ignore[reportPrivateUsage]
    assert prompt._name_words(screenplay_of(ROWS)) is not words  # pyright: ignore[reportPrivateUsage]


def test_animals_are_found_once_per_extraction_and_returned_as_a_copy() -> None:
    sp = screenplay_of(ROWS)
    ex = extraction_of(sp, [("NANDI", "NANDI (60s)")])
    found = animals(ex)
    found["NANDI"] = "a cat"  # a caller's change never reaches the cache
    assert animals(ex) == {}
    assert labels._animals_cache[0][0] is ex  # pyright: ignore[reportPrivateUsage]
