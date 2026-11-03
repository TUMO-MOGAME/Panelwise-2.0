"""T098: bubbles placed by the speaker's head (comic.md §4 steps 7 and 8, §6, §9). A head is a
`HeadSeen` box from T097's head agent; a frame with none letters exactly as before."""

import math

import pytest

from app.comic import (
    Bubble,
    BubbleKind,
    ComicBook,
    PanelFrame,
    WithheldCard,
    bubbles,
    place_lettering,
)
from app.comic import job as comic_job
from app.comic.render import panel_frame
from app.frames.model import FrameAuditRow
from app.llm import Usage
from app.shots import Framing
from app.verify import Position
from app.verify.model import (
    Audit,
    Check,
    CheckResult,
    FrameOutcome,
    FrameState,
    HeadSeen,
    RenderedFrame,
    Severity,
    Verdict,
)
from tests.comic.conftest import frames, solid
from tests.comic.test_bubbles import INSET, lettered, one_panel, second
from tests.comic.test_layout import shot
from tests.fakes import MemoryStore

head_rect = bubbles._head_rect  # pyright: ignore[reportPrivateUsage]
cost_of = bubbles._cost  # pyright: ignore[reportPrivateUsage]
to_mouth = bubbles._to_mouth  # pyright: ignore[reportPrivateUsage]
reused = comic_job._reused  # pyright: ignore[reportPrivateUsage]
Prior = comic_job._Prior  # pyright: ignore[reportPrivateUsage]

TOP_LEFT_HEAD = HeadSeen(0, "THABO", (0.0, 0.0, 0.3, 0.3))  # someone else, over the first cell


def with_heads(
    book: ComicBook,
    heads: tuple[HeadSeen, ...],
    positions: dict[str, Position] | None = None,
) -> dict[tuple[int, int], PanelFrame]:
    """`frames` on a flat frame, the lettered panel (0, 2) given `heads` and `positions`."""
    out = frames(book, solid, {(0, 2): positions or {}})
    frame = out[(0, 2)]
    out[(0, 2)] = PanelFrame(frame.png, frame.positions, False, heads=heads)
    return out


# --- the head rect ------------------------------------------------------------------------------


def test_a_head_rect_is_the_box_in_pixels_grown_by_12_and_clipped() -> None:
    # 900 x 700: x0 0.1 -> 90, y0 0.25 -> 175, x1 0.2005 -> ceil(180.45) = 181, y1 0.4 -> 280
    assert head_rect(HeadSeen(0, None, (0.1, 0.25, 0.2005, 0.4)), 900, 700) == (78, 163, 115, 129)
    # at the corner: clipped to the panel
    assert head_rect(HeadSeen(0, None, (0.0, 0.0, 0.05, 0.05)), 900, 700) == (0, 0, 57, 47)
    assert head_rect(HeadSeen(0, None, (0.95, 0.95, 1.0, 1.0)), 900, 700) == (843, 653, 57, 47)


# --- the cost -----------------------------------------------------------------------------------


def test_a_box_over_any_head_costs_2_more() -> None:
    box = (100, 100, 200, 80)
    over = [(150, 150, 40, 40)]
    beside = [(400, 400, 40, 40)]
    assert cost_of(None, box, None, over) - cost_of(None, box, None, beside) == 2.0
    assert cost_of(None, box, None, []) == cost_of(None, box, None, beside) == 0.0
    # two heads under one box still cost 2.0: the box covers a head or it doesn't
    assert cost_of(None, box, None, [*over, (110, 110, 20, 20)]) == 2.0
    # the speaker's third adds on top, as before
    assert cost_of(None, box, (0, 300), over) == 4.0


def test_a_bubble_keeps_off_a_head_when_a_free_spot_exists() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    plain = lettered(second(place_lettering(book, screenplay, plan, frames(book))))
    assert plain.rect[:2] == (x + INSET, y + INSET)  # the first cell, without heads
    placed = place_lettering(book, screenplay, plan, with_heads(book, (TOP_LEFT_HEAD,)))
    bubble = lettered(second(placed))
    hx, hy, hw, hh = head_rect(TOP_LEFT_HEAD, w, h)
    bx, by, bw, bh = bubble.rect
    assert not (bx - x < hx + hw and hx < bx - x + bw and by - y < hy + hh and hy < by - y + bh)


# --- the speaker --------------------------------------------------------------------------------


NANDI_RIGHT = HeadSeen(0, "NANDI", (0.7, 0.5, 0.8, 0.65))


def test_a_speaker_with_a_head_pays_no_third_and_the_tail_ends_at_the_head() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    # positions says left; the head is on the right. A known head replaces the third.
    placed = place_lettering(
        book, screenplay, plan, with_heads(book, (NANDI_RIGHT,), {"NANDI": Position.LEFT})
    )
    bubble = lettered(second(placed))
    assert isinstance(bubble, Bubble) and bubble.kind is BubbleKind.SPEECH
    assert bubble.rect[:2] == (x + INSET, y + INSET)  # the left third is free to use
    hx, hy, hw, hh = head_rect(NANDI_RIGHT, w, h)
    # T114 replaced T098's nearest point: the tail aims at the mouth (tests/comic/test_t114.py)
    want = to_mouth(NANDI_RIGHT, (x, y, w, h), bubble.rect)
    assert bubble.tail == want
    assert x + hx <= want[0] < x + hx + hw and y + hy <= want[1] < y + hy + hh


def test_the_speaker_is_found_by_match_speaker() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    head = HeadSeen(1, "Nandi", NANDI_RIGHT.box)
    bubble = lettered(second(place_lettering(book, screenplay, plan, with_heads(book, (head,)))))
    assert isinstance(bubble, Bubble) and bubble.tail == to_mouth(head, (x, y, w, h), bubble.rect)


@pytest.mark.parametrize(
    "head",
    [HeadSeen(0, None, (0.7, 0.5, 0.8, 0.65)), HeadSeen(0, "THABO", (0.7, 0.5, 0.8, 0.65))],
)
def test_a_speaker_with_no_head_keeps_the_third_and_the_45_percent_tip(head: HeadSeen) -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    placed = place_lettering(
        book, screenplay, plan, with_heads(book, (head,), {"NANDI": Position.LEFT})
    )
    bubble = lettered(second(placed))
    assert isinstance(bubble, Bubble)
    assert bubble.tail == (x + w // 6, y + math.floor(h * 0.45))
    assert bubble.rect[0] >= x + w // 3  # still off the left third


def test_an_off_panel_tail_is_unchanged_by_heads() -> None:
    screenplay, plan, book = one_panel("You came back.", "O.S.")
    x = second(book).rect[0]
    placed = place_lettering(
        book, screenplay, plan, with_heads(book, (NANDI_RIGHT,), {"NANDI": Position.LEFT})
    )
    bubble = lettered(second(placed))
    assert isinstance(bubble, Bubble) and bubble.kind is BubbleKind.OFF_PANEL
    assert bubble.tail == (x, bubble.rect[1] + bubble.rect[3] // 2)


def test_a_frame_with_no_heads_letters_exactly_as_before() -> None:
    screenplay, plan, book = one_panel("You came back.")
    seen = {(0, 2): {"NANDI": Position.LEFT}}
    before = place_lettering(book, screenplay, plan, frames(book, solid, seen))
    after = place_lettering(book, screenplay, plan, with_heads(book, (), {"NANDI": Position.LEFT}))
    assert before == after


# --- where the heads come from ------------------------------------------------------------------


def test_panel_frame_carries_the_accepted_audits_heads_and_a_card_none() -> None:
    s = shot(0, 1, Framing.WIDE)
    heads = (HeadSeen(0, "NANDI", (0.1, 0.1, 0.2, 0.3)),)
    frame = RenderedFrame((0, 1), 2, 7, b"png", 10, 10, "")
    accepted = Audit(
        (0, 1), 2, 7, None, None, (), Verdict.PASS, {}, (), Usage(0, 0, 0), heads=heads
    )
    got = panel_frame(FrameOutcome((0, 1), FrameState.PASSED, frame, (accepted,)), s)
    assert got.heads == heads
    failed = CheckResult(Check.UNSCRIPTED_PERSON, Severity.HARD, False, "x")
    withheld = Audit(
        (0, 1), 3, 7, None, None, (failed,), Verdict.FAIL, {}, (), Usage(0, 0, 0), heads=heads
    )
    card = panel_frame(FrameOutcome((0, 1), FrameState.WITHHELD, None, (withheld,)), s)
    assert card.withheld and card.heads == ()
    assert isinstance(card.card, WithheldCard)


@pytest.mark.parametrize(
    ("stored", "want"),
    [
        (
            [{"person": 1, "character": "NANDI", "box": [0.1, 0.2, 0.3, 0.4]}],
            (HeadSeen(1, "NANDI", (0.1, 0.2, 0.3, 0.4)),),
        ),
        (
            [{"person": 0, "character": None, "box": [0, 0, 1, 1]}],
            (HeadSeen(0, None, (0, 0, 1, 1)),),
        ),
        (None, ()),  # a row before 0010, or one the agent didn't answer
    ],
)
async def test_a_reused_panel_carries_its_rows_heads(
    stored: list[dict[str, object]] | None, want: tuple[HeadSeen, ...]
) -> None:
    store = MemoryStore()
    await store.put("frames/a.png", solid((0, 0, 90, 70)), "image/png")
    row = FrameAuditRow(frame_asset="frames/a.png", positions={"NANDI": "left"}, heads=stored)
    got = await reused(store, Prior(1, row), (90, 70))
    assert got is not None
    frame, asset = got
    assert asset == "frames/a.png" and frame.heads == want
    assert frame.positions == {"NANDI": Position.LEFT}
