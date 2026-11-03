"""T112: speech tails never cross (comic.md §4 steps 7 and 8, §6, §9). A tail is the triangle
step 8 draws; two tails ending at one tip may meet; a panel no placement can keep apart still
letters, through a second search without the rule, with a warning."""

import logging
import math
from collections.abc import Sequence

import pytest

from app.comic import (
    BubbleKind,
    ComicBook,
    LayoutReport,
    Page,
    Panel,
    PanelFrame,
    Rect,
    bubbles,
    place_lettering,
)
from app.comic import render as render_module
from app.comic.bubbles import tail_triangle, tails_cross
from app.comic.model import Point
from app.script import Action, Dialogue, Screenplay
from app.shots import Framing, ShotPlan
from app.verify.model import HeadSeen
from tests.comic.conftest import frames, solid
from tests.comic.test_bubbles import cell, overlap, second
from tests.comic.test_layout import SPAN, plan_of, scene, shot

type Triangle = Sequence[tuple[float, float]]

LERATO_RIGHT = HeadSeen(0, "LERATO", (0.75, 0.45, 0.88, 0.62))
MOKGOSI_LEFT = HeadSeen(1, "MOKGOSI", (0.12, 0.45, 0.25, 0.62))
WARNING = "tails cross on scene 0, shot 2: no placement keeps them apart"


def line(cue: str, text: str, extension: str | None = None) -> Dialogue:
    return Dialogue(cue, extension, None, text, SPAN)


def panel_of(*lines: Dialogue | Action) -> tuple[Screenplay, ShotPlan, ComicBook]:
    """One scene whose second shot letters `lines`, on a 900 x 700 panel (no scene caption)."""
    s = scene(0, *lines)
    screenplay = Screenplay("", 1, (s,), (1,))
    plan = plan_of(shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, *range(len(lines))))
    wide = Panel(0, 1, (120, 2000, 900, 700), (), ())
    book = ComicBook(
        (Page(1, 1988, 3075, (wide, Panel(0, 2, (120, 120, 900, 700), (), ()))),),
        LayoutReport(2, 0, 0, 0),
    )
    return screenplay, plan, book


def framed(book: ComicBook, heads: tuple[HeadSeen, ...] = ()) -> dict[tuple[int, int], PanelFrame]:
    out = frames(book, solid)
    frame = out[(0, 2)]
    out[(0, 2)] = PanelFrame(frame.png, frame.positions, False, heads=heads)
    return out


def tails(panel: Panel) -> list[tuple[Point, Triangle]]:
    out: list[tuple[Point, Triangle]] = []
    for bubble in panel.bubbles:
        if bubble.tail is not None:
            triangle = tail_triangle(bubble.rect, bubble.tail)
            if triangle is not None:
                out.append((bubble.tail, triangle))
    return out


def crossings(panel: Panel) -> int:
    """Pairs of tails that cross, two tails to one tip exempt (step 7)."""
    drawn = tails(panel)
    return sum(
        1
        for i, (tip, a) in enumerate(drawn)
        for other, b in drawn[i + 1 :]
        if tip != other and tails_cross(a, b)
    )


def without_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(a: Triangle, b: Triangle) -> bool:
        return False

    monkeypatch.setattr(bubbles, "tails_cross", never)


def every_tail_crosses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every two drawn tails cross. (A tip inside its own box draws no tail, so the panels using
    this give their tails tips no box can cover: the bottom centre, or the panel's edge.)"""

    def always(a: Triangle, b: Triangle) -> bool:
        return True

    monkeypatch.setattr(bubbles, "tails_cross", always)


# --- tails_cross ----------------------------------------------------------------------------------


def test_triangles_that_cross_cross() -> None:
    a = ((0.0, 0.0), (100.0, 100.0), (0.0, 20.0))
    b = ((100.0, 0.0), (0.0, 100.0), (100.0, 20.0))
    assert tails_cross(a, b) and tails_cross(b, a)


def test_triangles_that_touch_at_a_point_cross() -> None:
    a = ((0.0, 0.0), (50.0, 50.0), (0.0, 20.0))
    b = ((100.0, 0.0), (50.0, 50.0), (100.0, 20.0))  # one shared vertex
    assert tails_cross(a, b)
    c = ((50.0, 0.0), (60.0, 50.0), (70.0, 0.0))
    d = ((60.0, 50.0), (55.0, 90.0), (65.0, 90.0))  # a vertex on the other's vertex, apex to apex
    assert tails_cross(c, d)


def test_triangles_apart_do_not_cross() -> None:
    a = ((0.0, 0.0), (40.0, 40.0), (0.0, 20.0))
    b = ((100.0, 0.0), (60.0, 40.0), (100.0, 20.0))
    assert not tails_cross(a, b) and not tails_cross(b, a)
    # side by side, overlapping in x and in y but split by a slanted line: still apart
    c = ((0.0, 0.0), (100.0, 0.0), (0.0, 100.0))
    d = ((100.0, 10.0), (100.0, 100.0), (10.0, 100.0))
    assert not tails_cross(c, d)


def test_tail_triangle_is_step_8s_triangle_unchanged() -> None:
    box, tip = (100, 100, 200, 80), (400, 300)
    r = min(48, 80 // 2, 200 // 2)  # the corner radius
    base = (min(max(400, 100 + r), 100 + 200 - 1 - r), min(max(300, 100 + r), 100 + 80 - 1 - r))
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    length = math.hypot(dx, dy)
    px, py = -dy / length * 28 / 2, dx / length * 28 / 2
    want = ((base[0] + px, base[1] + py), (400.0, 300.0), (base[0] - px, base[1] - py))
    assert tail_triangle(box, tip) == want
    assert tail_triangle(box, (150, 120)) is None  # a tip inside the box draws no tail


# --- placement ------------------------------------------------------------------------------------


def two_speakers() -> tuple[Screenplay, ShotPlan, ComicBook]:
    """Lerato's line, then Mokgosi's; Lerato stands right, Mokgosi left."""
    return panel_of(
        line("LERATO", "Can I have all of it?"), line("MOKGOSI", "All of it. But listen to me.")
    )


def test_two_speakers_on_the_wrong_sides_are_placed_so_their_tails_do_not_cross(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screenplay, plan, book = two_speakers()
    given = framed(book, (LERATO_RIGHT, MOKGOSI_LEFT))
    placed = second(place_lettering(book, screenplay, plan, given))
    with monkeypatch.context() as patch:
        without_rule(patch)
        cheapest = second(place_lettering(book, screenplay, plan, given))
    assert crossings(cheapest) == 1  # the cheapest placement crosses: the case T112 is for
    assert crossings(placed) == 0
    first, then = placed.bubbles
    assert first.speaker == "LERATO" and then.speaker == "MOKGOSI"
    assert cell(placed, first.rect) < cell(placed, then.rect)  # reading order kept
    assert not overlap(first.rect, then.rect)
    x, y, w, h = placed.rect
    for bubble in placed.bubbles:
        bx, by, bw, bh = bubble.rect
        assert x + 16 <= bx and bx + bw <= x + w - 16 and y + 16 <= by and by + bh <= y + h - 16


def test_two_lines_of_one_speaker_ending_at_one_tip_may_meet(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # no head and no position: both tails go to the bottom centre and meet there. Whispered,
    # so T118 doesn't link them: a whisper's dashes keep their own tails.
    screenplay, plan, book = panel_of(
        Dialogue("NANDI", None, "whispering", "You came back.", SPAN),
        Dialogue("NANDI", None, "whispering", "The boat didn't.", SPAN),
    )
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    (one, a), (other, b) = tails(placed)
    assert one == other and tails_cross(a, b)  # they touch at the tip
    with monkeypatch.context() as patch:
        every_tail_crosses(patch)
        assert second(place_lettering(book, screenplay, plan, framed(book))) == placed
    assert WARNING not in caplog.text


def test_a_panel_every_placement_crosses_still_letters_with_a_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lerato's tail to the bottom centre (no head, no position), Mokgosi's to the right edge
    screenplay, plan, book = panel_of(
        line("LERATO", "Can I have all of it?"),
        line("MOKGOSI", "Lerato! Lerato, come down.", "O.S."),
    )
    given = framed(book)
    with monkeypatch.context() as patch:
        without_rule(patch)
        before = place_lettering(book, screenplay, plan, given)
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    every_tail_crosses(monkeypatch)
    # the second search, without the rule, is the placement from before T112
    assert place_lettering(book, screenplay, plan, given) == before
    assert caplog.text.count(WARNING) == 1


def test_an_off_panel_tail_counts_like_any_other(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # two off-panel lines of two speakers: two tips on the right edge, at each box's middle. The
    # boxes differ in height, so no row puts the two middles (and so the two tips) at one point.
    screenplay, plan, book = panel_of(
        line("LERATO", "Mokgosi? Is that you?", "O.S."),
        line("MOKGOSI", "Lerato! Lerato, come down from there before the wind takes you.", "O.S."),
    )
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    every_tail_crosses(monkeypatch)
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    assert all(bubble.kind is BubbleKind.OFF_PANEL for bubble in placed.bubbles)
    assert caplog.text.count(WARNING) == 1


def test_a_caption_has_no_tail_to_cross(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    screenplay, plan, book = panel_of(
        line("LERATO", "Can I have all of it?"), line("MOKGOSI", "Listen to me.", "V.O.")
    )
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    every_tail_crosses(monkeypatch)
    place_lettering(book, screenplay, plan, framed(book, (LERATO_RIGHT,)))
    assert WARNING not in caplog.text


def test_a_panel_whose_first_placement_does_not_cross_letters_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mokgosi on the right now: the cheapest placement is already apart
    screenplay, plan, book = two_speakers()
    mokgosi_right = HeadSeen(1, "MOKGOSI", (0.75, 0.2, 0.88, 0.35))
    lerato_left = HeadSeen(0, "LERATO", (0.12, 0.45, 0.25, 0.62))
    given = framed(book, (lerato_left, mokgosi_right))
    placed = place_lettering(book, screenplay, plan, given)
    assert crossings(second(placed)) == 0
    without_rule(monkeypatch)
    assert place_lettering(book, screenplay, plan, given) == placed


# --- drawing --------------------------------------------------------------------------------------


def test_render_draws_tail_triangles_points(monkeypatch: pytest.MonkeyPatch) -> None:
    screenplay, plan, book = two_speakers()
    given = framed(book, (LERATO_RIGHT, MOKGOSI_LEFT))
    placed = place_lettering(book, screenplay, plan, given)
    asked: list[tuple[Rect, Point]] = []

    def recording(box: Rect, tip: Point) -> tuple[tuple[float, float], ...] | None:
        asked.append((box, tip))
        return tail_triangle(box, tip)

    monkeypatch.setattr(render_module, "tail_triangle", recording)
    render_module.render_pages(placed, given)
    want = [(b.rect, b.tail) for b in second(placed).bubbles]
    # each pass (outlines, then fills) draws the same triangle
    assert set(asked) == {(rect, tip) for rect, tip in want if tip is not None}
