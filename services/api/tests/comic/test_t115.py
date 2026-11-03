"""T115: a lone unnamed head is the speaker's (comic.md §4 step 7): one head, no name, one speaker
in the panel, and the positions don't put the speaker elsewhere."""

import math

import pytest

from app.comic import Bubble, bubbles, place_lettering
from app.verify import Position
from app.verify.model import HeadSeen
from tests.comic.test_bubbles import lettered, one_panel
from tests.comic.test_t098 import with_heads
from tests.comic.test_t112 import framed, line, panel_of, second

to_mouth = bubbles._to_mouth  # pyright: ignore[reportPrivateUsage]

UNNAMED_RIGHT = HeadSeen(0, None, (0.7, 0.3, 0.82, 0.5))


def test_one_unnamed_head_and_one_speaker_the_tail_aims_at_that_head() -> None:
    # Tumo's gogos-recipe 3.1: the head agent boxed Mpho, the judge left her unmatched
    screenplay, plan, book = one_panel("Ma. There's writing at the back.")
    placed = second(place_lettering(book, screenplay, plan, with_heads(book, (UNNAMED_RIGHT,))))
    bubble = lettered(placed)
    assert isinstance(bubble, Bubble)
    assert bubble.tail == to_mouth(UNNAMED_RIGHT, placed.rect, bubble.rect)


def test_two_lines_of_the_one_speaker_aim_at_the_head_as_one_linked_balloon() -> None:
    screenplay, plan, book = panel_of(line("NANDI", "You came back."), line("NANDI", "Why?"))
    placed = second(place_lettering(book, screenplay, plan, framed(book, (UNNAMED_RIGHT,))))
    first, then = placed.bubbles
    assert then.linked
    (tailed,) = [b for b in (first, then) if b.tail is not None]  # T119: one tail, either box
    assert tailed.tail == to_mouth(UNNAMED_RIGHT, placed.rect, tailed.rect)


def bottom_centre(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    x, y, w, h = rect
    return x + w // 2, y + h - 1


def test_two_speakers_guess_nothing() -> None:
    screenplay, plan, book = panel_of(line("NANDI", "You came back."), line("THABO", "I did."))
    placed = second(place_lettering(book, screenplay, plan, framed(book, (UNNAMED_RIGHT,))))
    assert [b.tail for b in placed.bubbles] == [bottom_centre(placed.rect)] * 2


def test_an_off_panel_voice_does_not_count_as_a_second_speaker() -> None:
    screenplay, plan, book = panel_of(
        line("NANDI", "You came back."), line("THABO", "Nandi? Is that you?", "O.S.")
    )
    placed = second(place_lettering(book, screenplay, plan, framed(book, (UNNAMED_RIGHT,))))
    nandi = placed.bubbles[0]
    assert nandi.tail == to_mouth(UNNAMED_RIGHT, placed.rect, nandi.rect)


@pytest.mark.parametrize(
    "heads",
    [
        (UNNAMED_RIGHT, HeadSeen(1, None, (0.1, 0.3, 0.22, 0.5))),  # two heads: 5.4's extra person
        (UNNAMED_RIGHT, HeadSeen(1, "THABO", (0.1, 0.3, 0.22, 0.5))),  # one named someone else
        (HeadSeen(0, "THABO", UNNAMED_RIGHT.box),),  # the one head is someone else's
    ],
)
def test_with_any_other_head_nothing_is_guessed(heads: tuple[HeadSeen, ...]) -> None:
    screenplay, plan, book = one_panel("You came back.")
    placed = second(place_lettering(book, screenplay, plan, with_heads(book, heads)))
    bubble = lettered(placed)
    assert isinstance(bubble, Bubble) and bubble.tail == bottom_centre(placed.rect)


def test_positions_placing_the_speaker_in_another_third_win() -> None:
    screenplay, plan, book = one_panel("You came back.")
    given = with_heads(book, (UNNAMED_RIGHT,), {"NANDI": Position.LEFT})
    placed = second(place_lettering(book, screenplay, plan, given))
    bubble = lettered(placed)
    x, y, w, h = placed.rect
    assert isinstance(bubble, Bubble)
    assert bubble.tail == (x + w // 6, y + math.floor(h * 0.45))  # T098's third, as before
    agrees = with_heads(book, (UNNAMED_RIGHT,), {"NANDI": Position.RIGHT})
    bubble = lettered(second(place_lettering(book, screenplay, plan, agrees)))
    assert isinstance(bubble, Bubble)
    assert bubble.tail == to_mouth(UNNAMED_RIGHT, placed.rect, bubble.rect)
