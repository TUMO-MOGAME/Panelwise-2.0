"""T119-T121: a linked chain's one tail leaves the box nearest the speaker; two linked boxes that
nearly touch merge at a seam; a pause the script states keeps one speaker's lines apart
(comic.md §3, §4 steps 7-8)."""

import math

import pytest

from app.comic import bubbles, place_lettering
from app.comic.bubbles import LINK_WIDTH, connector
from app.comic.model import Rect
from app.script import Action, Dialogue, Span, parse_pdf
from app.verify.model import HeadSeen
from tests.comic.test_t112 import framed, panel_of, second
from tools.build_comic_reference import build
from tools.build_samples import SAMPLES

SPAN = Span(1, 1, 1)
seam = bubbles._seam  # pyright: ignore[reportPrivateUsage]
band = bubbles._band  # pyright: ignore[reportPrivateUsage]
to_mouth = bubbles._to_mouth  # pyright: ignore[reportPrivateUsage]
HEAD_LOW_RIGHT = HeadSeen(0, "LERATO", (0.72, 0.5, 0.86, 0.75))


def say(cue: str, text: str, extension: str | None = None, note: str | None = None) -> Dialogue:
    return Dialogue(cue, extension, note, text, SPAN)


# --- T119: the tail on the box nearest the speaker ------------------------------------------------


def test_the_chains_one_tail_leaves_the_box_nearest_the_speaker() -> None:
    screenplay, plan, book = panel_of(
        say("LERATO", "And we watch the sky."), say("LERATO", "Every minute.", "CONT'D")
    )
    placed = second(place_lettering(book, screenplay, plan, framed(book, (HEAD_LOW_RIGHT,))))
    first, then = placed.bubbles
    assert then.linked and first.tail is None and then.tail is not None

    # it is the nearer: the first box's own tip would be further from its centre
    def reach(rect: Rect) -> float:
        tip = to_mouth(HEAD_LOW_RIGHT, placed.rect, rect)
        return math.hypot(rect[0] + rect[2] / 2 - tip[0], rect[1] + rect[3] / 2 - tip[1])

    assert reach(then.rect) < reach(first.rect)
    assert then.tail == to_mouth(HEAD_LOW_RIGHT, placed.rect, then.rect)


def test_with_no_head_the_tail_goes_where_the_nearer_box_points() -> None:
    screenplay, plan, book = panel_of(
        say("NANDI", "You came back."), say("NANDI", "The boat didn't.")
    )
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    assert sum(b.tail is not None for b in placed.bubbles) == 1


# --- T120: merged at a seam -----------------------------------------------------------------------


def test_two_pills_side_by_side_and_close_merge_at_a_seam() -> None:
    a, b = (100, 100, 300, 69), (412, 100, 200, 69)  # 12 px apart, both 69 high
    joined = connector(a, b)
    assert joined == seam(a, b, 0) and joined != band(a, b, LINK_WIDTH)
    xs, ys = [p[0] for p in joined], [p[1] for p in joined]
    assert min(xs) == 100 + 300 - 8 and max(xs) == 412 + 8  # 8 px into each box
    assert max(ys) - min(ys) >= LINK_WIDTH  # wider than a bridge: one outline, pinched


def test_stacked_boxes_merge_across_their_shared_width() -> None:
    a, b = (100, 100, 400, 106), (150, 220, 300, 106)  # 14 px apart
    joined = connector(a, b)
    xs, ys = [p[0] for p in joined], [p[1] for p in joined]
    r = 48 // 2  # half the larger corner radius
    assert (min(xs), max(xs)) == (150 + r, 450 - r)
    assert (min(ys), max(ys)) == (206 - 8, 220 + 8)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ((100, 100, 300, 69), (430, 100, 200, 69)),  # 30 px apart: a bridge
        ((100, 100, 300, 69), (412, 160, 200, 106)),  # diagonal, no shared edge: a bridge
        ((100, 100, 300, 69), (412, 100, 200, 106)),  # too little shared edge once inset
    ],
)
def test_otherwise_a_bridge(a: Rect, b: Rect) -> None:
    assert connector(a, b) == band(a, b, LINK_WIDTH)


# --- T121: a stated pause unlinks -----------------------------------------------------------------


@pytest.mark.parametrize(
    "lines",
    [
        (say("LERATO", "And we watch the sky."), say("LERATO", "Every minute.", None, "beat")),
        (
            say("LERATO", "And we watch the sky."),
            say("LERATO", "Every minute.", None, "after a moment"),
        ),
        (
            say("LERATO", "And we watch the sky."),
            say("LERATO", "Every minute.", None, "a long pause"),
        ),
    ],
)
def test_a_pause_the_script_states_keeps_the_lines_apart(
    lines: tuple[Dialogue | Action, ...],
) -> None:
    screenplay, plan, book = panel_of(*lines)
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    assert not any(b.linked for b in placed.bubbles)
    assert all(b.tail is not None for b in placed.bubbles)  # a tail each


def test_an_action_line_between_does_not_unlink() -> None:
    # Katlego, 2026-10-18: a screenplay puts action between nearly every two blocks of one speaker
    screenplay, plan, book = panel_of(
        say("LERATO", "Come on, wind."),
        Action("A gust tears the kite away.", SPAN),
        say("LERATO", "No, no, no!"),
    )
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    assert [b.linked for b in placed.bubbles] == [False, True]


def test_a_speech_split_by_a_page_break_stays_linked() -> None:
    screenplay, plan, book = panel_of(
        say("LERATO", "And we watch the sky."), say("LERATO", "Every minute.", "CONT'D")
    )
    placed = second(place_lettering(book, screenplay, plan, framed(book)))
    assert placed.bubbles[1].linked


def test_the_samples_two_pairs() -> None:
    # the-red-kite: "Come on, wind." and "No, no, no!" have the gust between them, and stay linked;
    # "And we watch the sky, Grandpa." runs on over a page break as LERATO (CONT'D)
    screenplay = parse_pdf((SAMPLES / "the-red-kite.pdf").read_bytes())
    gust = screenplay.scenes[0].elements[3]
    assert isinstance(gust, Action) and gust.text.startswith("A gust")
    book, _ = build()
    panels = {(p.scene_index, p.shot_number): p for page in book.pages for p in page.panels}
    assert [b.linked for b in panels[(0, 2)].bubbles] == [False, True]
    assert [b.linked for b in panels[(4, 2)].bubbles if b.speaker == "LERATO"] == [False, True]
