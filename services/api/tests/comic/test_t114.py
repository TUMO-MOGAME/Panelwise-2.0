"""T114: a speech tail aims at the speaker's mouth, the centre of the head box's lower third, and
stops where the line to it enters the grown head rect (comic.md §4 step 8, §9)."""

import math

from app.comic import Bubble, BubbleKind, bubbles, place_lettering
from app.comic.model import Point, Rect
from app.verify import Position
from app.verify.model import HeadSeen
from tests.comic.conftest import frames, solid
from tests.comic.test_bubbles import lettered, one_panel, second
from tests.comic.test_t098 import with_heads

head_rect = bubbles._head_rect  # pyright: ignore[reportPrivateUsage]
to_mouth = bubbles._to_mouth  # pyright: ignore[reportPrivateUsage]

PANEL: Rect = (120, 120, 900, 700)
# 900 x 700: L 450, T 350, R 540, B 490; the mouth (495, 350 + 5 * 140 / 6) = (495, 466.67);
# grown by 12: x 438-551, y 338-501 (inclusive)
HEAD = HeadSeen(0, "NANDI", (0.5, 0.5, 0.6, 0.7))


def centred(cx: int, cy: int) -> Rect:
    """A 200 x 70 bubble whose centre is (cx, cy) in panel pixels, as a page-pixel box."""
    return PANEL[0] + cx - 100, PANEL[1] + cy - 35, 200, 70


def page(px: int, py: int) -> Point:
    return PANEL[0] + px, PANEL[1] + py


def test_from_beside_the_head_the_tip_is_on_its_side_level_with_the_line_to_the_mouth() -> None:
    # centre (200, 466): t = (438 - 200) / (495 - 200); y = 466 + t * 0.67 = 466.54 -> 467
    assert to_mouth(HEAD, PANEL, centred(200, 466)) == page(438, 467)


def test_from_above_and_left_the_tip_is_where_the_line_enters_not_the_corner() -> None:
    # centre (300, 100): x enters at t = 138 / 195 = 0.7077, y at t = 238 / 366.67 = 0.6491; the
    # later one: x = 438, y = 100 + 0.7077 * 366.67 = 359.49 -> 359. T098 had the corner (438, 338).
    assert to_mouth(HEAD, PANEL, centred(300, 100)) == page(438, 359)


def test_from_straight_above_the_tip_is_on_the_top_edge_over_the_mouth() -> None:
    assert to_mouth(HEAD, PANEL, centred(495, 100)) == page(495, 338)


def test_from_below_the_tip_is_on_the_bottom_edge() -> None:
    # centre (495, 650): only y matters; the line meets y = 501 at x = 495
    assert to_mouth(HEAD, PANEL, centred(495, 650)) == page(495, 501)


def test_a_bubble_centred_inside_the_head_rect_has_its_tip_at_its_centre() -> None:
    assert to_mouth(HEAD, PANEL, centred(480, 400)) == page(480, 400)


def test_the_tip_stays_in_a_head_rect_clipped_by_the_panel() -> None:
    edge = HeadSeen(0, "NANDI", (0.9, 0.0, 1.0, 0.2))  # top-right corner: clipped on two sides
    hx, hy, hw, hh = head_rect(edge, 900, 700)
    for cx, cy in [(100, 600), (450, 350), (850, 650)]:
        tx, ty = to_mouth(edge, PANEL, centred(cx, cy))
        assert PANEL[0] + hx <= tx < PANEL[0] + hx + hw and PANEL[1] + hy <= ty < PANEL[1] + hy + hh


def off_line(tip: Point, start: tuple[float, float], end: tuple[float, float]) -> float:
    """The tip's distance from the line through start and end."""
    (x0, y0), (x1, y1) = start, end
    return abs((x1 - x0) * (y0 - tip[1]) - (x0 - tip[0]) * (y1 - y0)) / math.hypot(x1 - x0, y1 - y0)


def test_a_placed_bubbles_tail_ends_on_the_head_rect_on_the_line_to_the_mouth() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    bubble = lettered(second(place_lettering(book, screenplay, plan, with_heads(book, (HEAD,)))))
    assert isinstance(bubble, Bubble) and bubble.kind is BubbleKind.SPEECH and bubble.tail
    bx, by, bw, bh = bubble.rect
    centre = (bx + bw // 2, by + bh // 2)
    mouth = (x + (450 + 540) / 2, y + 350 + 5 * (490 - 350) / 6)
    hx, hy, hw, hh = head_rect(HEAD, w, h)
    tx, ty = bubble.tail
    assert x + hx <= tx < x + hx + hw and y + hy <= ty < y + hy + hh
    assert tx in (x + hx, x + hx + hw - 1) or ty in (y + hy, y + hy + hh - 1)  # on its edge
    assert off_line(bubble.tail, centre, mouth) <= 1.0


def test_a_frame_without_heads_and_an_off_panel_line_are_unchanged() -> None:
    screenplay, plan, book = one_panel("You came back.")
    seen = {(0, 2): {"NANDI": Position.LEFT}}
    plain = place_lettering(book, screenplay, plan, frames(book, solid, seen))
    assert place_lettering(book, screenplay, plan, with_heads(book, (), seen[(0, 2)])) == plain
    screenplay, plan, book = one_panel("You came back.", "O.S.")
    off = lettered(second(place_lettering(book, screenplay, plan, with_heads(book, (HEAD,)))))
    assert isinstance(off, Bubble) and off.kind is BubbleKind.OFF_PANEL
    assert off.tail == (second(book).rect[0] + 900 - 1, off.rect[1] + off.rect[3] // 2)
