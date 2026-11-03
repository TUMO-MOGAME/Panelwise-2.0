"""T116: tails stay clear of other bubbles and other faces (comic.md §4 step 7), with T112's
crossing rule and the searches in order when nothing keeps them clear."""

import logging

import pytest

from app.comic import Panel, PanelFrame, bubbles, place_lettering
from app.comic.bubbles import tail_hull, tails_cross
from app.verify.model import HeadSeen
from tests.comic.test_bubbles import cell, overlap
from tests.comic.test_t112 import framed, line, panel_of, second

corners = bubbles._corners  # pyright: ignore[reportPrivateUsage]
head_rect = bubbles._head_rect  # pyright: ignore[reportPrivateUsage]
page_rect = bubbles._page_rect  # pyright: ignore[reportPrivateUsage]
inside = bubbles._inside  # pyright: ignore[reportPrivateUsage]

LERATO_RIGHT = HeadSeen(0, "LERATO", (0.75, 0.3, 0.88, 0.5))
MOKGOSI_LEFT = HeadSeen(1, "MOKGOSI", (0.05, 0.4, 0.17, 0.58))
CLEAR = "a tail runs under a bubble or across a face on scene 0, shot 2"
APART = "tails cross on scene 0, shot 2"


def under(panel: Panel) -> int:
    """Tails that share a point with another box of the panel."""
    boxes = [*panel.bubbles, *panel.captions]
    count = 0
    for bubble in panel.bubbles:
        hull = None if bubble.tail is None else tail_hull(bubble.voice, bubble.rect, bubble.tail)
        if hull is not None:
            count += sum(tails_cross(hull, corners(o.rect)) for o in boxes if o is not bubble)
    return count


def across(panel: Panel, frame: PanelFrame) -> int:
    """Tails that share a point with a face other than the one their tip ends in."""
    faces = [page_rect(panel.rect, head_rect(h, panel.rect[2], panel.rect[3])) for h in frame.heads]
    count = 0
    for bubble in panel.bubbles:
        hull = None if bubble.tail is None else tail_hull(bubble.voice, bubble.rect, bubble.tail)
        if hull is not None and bubble.tail is not None:
            count += sum(
                tails_cross(hull, corners(face)) for face in faces if not inside(bubble.tail, face)
            )
    return count


def test_a_tail_that_would_run_under_the_bubble_above_is_placed_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the 17 Oct live comic's p2: Mokgosi's line below Lerato's, its tail up under hers
    screenplay, plan, book = panel_of(
        line("LERATO", "Can I have all of it?"), line("MOKGOSI", "All of it. But listen to me.")
    )
    given = framed(book, (LERATO_RIGHT, MOKGOSI_LEFT))
    placed = second(place_lettering(book, screenplay, plan, given))
    with monkeypatch.context() as patch:
        patch.setattr(bubbles, "TAIL_RULES", 1)  # T112's rule only: before T116
        before = second(place_lettering(book, screenplay, plan, given))
    assert under(before) == 1  # the case T116 is for
    assert under(placed) == 0 and across(placed, given[(0, 2)]) == 0
    first, then = placed.bubbles
    assert cell(placed, first.rect) < cell(placed, then.rect) and not overlap(first.rect, then.rect)


def test_a_tail_is_not_drawn_across_another_face(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lerato speaks; Mokgosi's head is between her bubble's first spot and her mouth
    screenplay, plan, book = panel_of(line("LERATO", "Can I have all of it?"))
    heads = (
        HeadSeen(0, "LERATO", (0.8, 0.05, 0.92, 0.25)),
        HeadSeen(1, "MOKGOSI", (0.45, 0.02, 0.58, 0.22)),
    )
    given = framed(book, heads)
    placed = second(place_lettering(book, screenplay, plan, given))
    with monkeypatch.context() as patch:
        patch.setattr(bubbles, "TAIL_RULES", 1)
        before = second(place_lettering(book, screenplay, plan, given))
    assert across(before, given[(0, 2)]) == 1
    assert across(placed, given[(0, 2)]) == 0


def test_the_speakers_own_face_is_where_the_tail_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    screenplay, plan, book = panel_of(line("LERATO", "Can I have all of it?"))
    given = framed(book, (LERATO_RIGHT,))
    placed = second(place_lettering(book, screenplay, plan, given))
    with monkeypatch.context() as patch:
        patch.setattr(bubbles, "TAIL_RULES", 1)
        assert second(place_lettering(book, screenplay, plan, given)) == placed  # nothing moves


def test_when_nothing_keeps_tails_clear_the_second_search_keeps_them_apart(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    screenplay, plan, book = panel_of(
        line("LERATO", "Can I have all of it?"), line("MOKGOSI", "All of it. But listen to me.")
    )
    given = framed(book, (LERATO_RIGHT, MOKGOSI_LEFT))
    with monkeypatch.context() as patch:
        patch.setattr(bubbles, "TAIL_RULES", 1)
        apart = place_lettering(book, screenplay, plan, given)
    real = bubbles.tails_cross

    def boxes_always_hit(
        a: tuple[tuple[float, float], ...], b: tuple[tuple[float, float], ...]
    ) -> bool:
        return len(b) == 4 or real(a, b)  # every box and face (4 corners) is hit; tails as real

    monkeypatch.setattr(bubbles, "tails_cross", boxes_always_hit)
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    assert place_lettering(book, screenplay, plan, given) == apart
    assert caplog.text.count(CLEAR) == 1 and APART not in caplog.text


def test_when_nothing_keeps_tails_apart_the_last_search_has_no_tail_rule(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    screenplay, plan, book = panel_of(
        line("LERATO", "Can I have all of it?"),
        line("MOKGOSI", "Lerato! Lerato, come down.", "O.S."),
    )
    given = framed(book)
    with monkeypatch.context() as patch:
        patch.setattr(bubbles, "TAIL_RULES", 0)
        free = place_lettering(book, screenplay, plan, given)

    def always(a: tuple[tuple[float, float], ...], b: tuple[tuple[float, float], ...]) -> bool:
        return True

    monkeypatch.setattr(bubbles, "tails_cross", always)
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    assert place_lettering(book, screenplay, plan, given) == free
    assert CLEAR not in caplog.text and caplog.text.count(APART) == 1  # one warning: the last
