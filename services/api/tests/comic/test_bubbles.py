"""place_lettering: comic.md §3 (extension → kind, SCENE caption), §4 steps 5-8, §9 (Traceability,
Extension mapping, Placement)."""

import math
import random
from io import BytesIO
from itertools import pairwise

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.comic import (
    Bubble,
    BubbleKind,
    Caption,
    CaptionKind,
    ComicBook,
    ComicError,
    LayoutReport,
    Page,
    Panel,
    PanelFrame,
    Rect,
    WithheldCard,
    bubbles,
    layout,
    layout_geometry,
    place_lettering,
    scene_caption,
)
from app.comic.bubbles import frame_image
from app.comic.layout import PADDING, WRAP_SHARE, box_size, font_at
from app.script import Dialogue, Scene, Screenplay, Span, parse_pdf, parse_text
from app.shots import Framing, Shot, ShotPlan
from app.verify import Position
from tests.comic.conftest import FLAT, busy, busy_left, busy_top, frames, png, solid
from tests.comic.test_layout import plan_of, say, scene, shot
from tests.script.conftest import two_page_text
from tools.build_samples import SAMPLES

INSET = 16
# The old rule's oracle (T065) costs boxes exactly as the module does.
detail = bubbles._detail  # pyright: ignore[reportPrivateUsage]
overlaps = bubbles._overlap  # pyright: ignore[reportPrivateUsage]
texts_of = bubbles._texts  # pyright: ignore[reportPrivateUsage]
third_of = bubbles._third  # pyright: ignore[reportPrivateUsage]


def sample() -> tuple[Screenplay, ShotPlan, ComicBook]:
    """T022's sample plan over the two-page test screenplay: every element in one shot."""
    screenplay = parse_text(*two_page_text())
    plan = plan_of(
        shot(0, 1, Framing.WIDE, 0, 1),
        shot(0, 2, Framing.CLOSE_UP, 2, 3),
        shot(1, 1, Framing.WIDE, 0),
        shot(1, 2, Framing.MEDIUM, 1, 2, 3),
        shot(2, 1, Framing.MEDIUM, 0),
    )
    return screenplay, plan, layout_geometry(plan, screenplay)


def panels(book: ComicBook) -> list[Panel]:
    return [p for page in book.pages for p in page.panels]


def boxes(panel: Panel) -> list[Rect]:
    return [c.rect for c in panel.captions] + [b.rect for b in panel.bubbles]


def one_panel(
    text: str, extension: str | None = None, rect: Rect = (120, 120, 900, 700)
) -> tuple[Screenplay, ShotPlan, ComicBook]:
    """One scene whose second shot letters one line: a hand-built book (no scene caption)."""
    s = scene(0, say(text, extension))
    screenplay = Screenplay("", 1, (s,), (1,))
    plan = plan_of(shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, 0))
    wide = Panel(0, 1, (120, 2000, 900, 700), (), ())
    book = ComicBook(
        (Page(1, 1988, 3075, (wide, Panel(0, 2, rect, (), ()))),), LayoutReport(2, 0, 0, 0)
    )
    return screenplay, plan, book


def lettered(panel: Panel) -> Bubble | Caption:
    (only,) = (*panel.bubbles, *panel.captions)
    return only


def second(book: ComicBook) -> Panel:
    return book.pages[0].panels[1]


def overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def cell(panel: Panel, box: Rect) -> tuple[int, int]:
    """The grid cell (row, col) whose corner is the box's top-left (comic.md §4 step 7)."""
    x, y, w, h = panel.rect
    ix, iy, iw, ih = x + INSET, y + INSET, w - 2 * INSET, h - 2 * INSET
    corners = {
        (ix + col * iw // 12, iy + row * ih // 8): (row, col)
        for row in range(8)
        for col in range(12)
    }
    return corners[box[0], box[1]]


# ------------------------------------------------------------------ traceability


def test_every_line_of_dialogue_is_lettered_once_verbatim_with_its_span() -> None:
    screenplay, plan, book = sample()
    placed = place_lettering(book, screenplay, plan, frames(book))

    scenes = {s.index: s for s in screenplay.scenes}
    expected = sorted(
        (sh.scene_index, i, e.text, e.span)
        for sh in plan.shots
        for i in sh.elements
        if isinstance(e := scenes[sh.scene_index].elements[i], Dialogue)
    )
    got = sorted(
        [(p.scene_index, b.element, b.text, b.span) for p in panels(placed) for b in p.bubbles]
        + [
            (p.scene_index, c.element, c.text, c.span)
            for p in panels(placed)
            for c in p.captions
            if c.kind is CaptionKind.VOICE_OVER
        ]
    )
    assert got == expected
    # The speaker is the cue verbatim; parentheticals ("without turning", "beat") are not lettered.
    for p in panels(placed):
        for b in p.bubbles:
            spoken = scenes[p.scene_index].elements[b.element]
            assert isinstance(spoken, Dialogue) and b.speaker == spoken.cue
    words = [t.text for p in panels(placed) for t in (*p.bubbles, *p.captions)]
    assert not any("without turning" in w or "beat" in w or "DOORS SLAM" in w for w in words)


def test_a_scenes_first_panel_carries_its_heading_caption_and_no_other_panel_does() -> None:
    screenplay, plan, book = sample()
    placed = place_lettering(book, screenplay, plan, frames(book))

    scene_captions = [
        (p.scene_index, p.shot_number, c)
        for p in panels(placed)
        for c in p.captions
        if c.kind is CaptionKind.SCENE
    ]
    assert [(s, n) for s, n, _ in scene_captions] == [(0, 1), (1, 1), (2, 1)]
    for (s, _, caption), heading in zip(scene_captions, screenplay.scenes, strict=True):
        assert caption.text == scene_caption(heading)
        assert caption.element is None
        assert caption.span == Span(
            heading.span.page, heading.span.line_start, heading.span.line_start
        )
        assert s == heading.index
    assert scene_captions[0][2].text == "LIGHTHOUSE KITCHEN — NIGHT"


def test_the_drawn_lines_are_the_texts_own_words_in_order() -> None:
    # render.py draws `wrap(text, limit, font)`: its lines, rejoined, are the text's own words.
    screenplay, plan, book = sample()
    h_screenplay, h_plan, h_book = one_panel(
        "In the teeth of a south- westerly, whatever you hear."
    )
    lettered = [
        *panels(place_lettering(book, screenplay, plan, frames(book))),
        second(place_lettering(h_book, h_screenplay, h_plan, frames(h_book))),
    ]
    for panel in lettered:
        for item in (*panel.bubbles, *panel.captions):
            font = layout.font_at(layout.FONT_PATH, item.font_px)
            lines = layout.wrap(item.text, math.floor(panel.rect[2] * 2 / 5), font)
            assert " ".join(lines) == " ".join(item.text.split())


def test_placement_keeps_the_geometry_and_counts_what_it_lettered() -> None:
    screenplay, plan, book = sample()
    placed = place_lettering(book, screenplay, plan, frames(book))

    assert [p.rect for p in panels(placed)] == [p.rect for p in panels(book)]
    bubbles = sum(len(p.bubbles) for p in panels(placed))
    captions = sum(len(p.captions) for p in panels(placed))
    assert (bubbles, captions) == (5, 3)  # six lines, THABO (O.S.) among them; 3 scene captions
    assert placed.report == LayoutReport(5, bubbles, captions, book.report.relayouts)
    assert place_lettering(book, screenplay, plan, frames(book)) == placed  # deterministic


def test_a_line_break_hyphen_is_lettered_as_the_element_has_it() -> None:
    # Lettering never rewrites: whatever the element text says is what is lettered.
    text = "In the teeth of a south- westerly."
    screenplay, plan, book = one_panel(text)
    placed = place_lettering(book, screenplay, plan, frames(book))
    assert lettered(second(placed)).text == text


def test_the_parsed_sample_letters_south_westerly_joined() -> None:
    # T048: the parser joins the line-break hyphen, and the bubble letters the element text.
    pdf = (SAMPLES / "sipho-and-siphokazi.pdf").read_bytes()
    (text,) = [
        e.text
        for s in parse_pdf(pdf).scenes
        for e in s.elements
        if isinstance(e, Dialogue) and "westerly" in e.text
    ]
    screenplay, plan, book = one_panel(text)
    placed = place_lettering(book, screenplay, plan, frames(book))
    assert lettered(second(placed)).text == text
    assert "in the teeth of a south-westerly." in text


# -------------------------------------------------------------- extension → kind


@pytest.mark.parametrize(
    ("extension", "kind"),
    [
        (None, BubbleKind.SPEECH),
        ("CONT'D", BubbleKind.SPEECH),
        ("FILTERED", BubbleKind.SPEECH),
        ("PRE-LAP", BubbleKind.SPEECH),
        ("ON P.A.", BubbleKind.SPEECH),
        ("O.S.", BubbleKind.OFF_PANEL),
        ("O.C.", BubbleKind.OFF_PANEL),
        ("OFF SCREEN", BubbleKind.OFF_PANEL),
        ("o.s.", BubbleKind.OFF_PANEL),
        ("V.O.", CaptionKind.VOICE_OVER),
        ("V.O./CONT'D", CaptionKind.VOICE_OVER),
    ],
)
def test_the_extension_decides_the_kind(
    extension: str | None, kind: BubbleKind | CaptionKind
) -> None:
    screenplay, plan, book = one_panel("Hold the light steady.", extension)
    placed = lettered(second(place_lettering(book, screenplay, plan, frames(book))))
    assert placed.kind is kind
    assert placed.text == "Hold the light steady."
    if isinstance(placed, Caption):
        assert placed.element == 0  # a voice-over caption is still that element, with its span


# --------------------------------------------------------------------- placement


def test_a_bubble_lands_in_the_frames_empty_half() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, _, w, _ = second(book).rect
    left = lettered(second(place_lettering(book, screenplay, plan, frames(book, busy_left))))
    assert left.rect[0] >= x + w // 2  # the left half is all edges; the right is flat

    top = lettered(second(place_lettering(book, screenplay, plan, frames(book, busy_top))))
    _, y, _, h = second(book).rect
    assert top.rect[1] >= y + h // 2


def test_a_flat_frame_takes_the_first_cell_so_detail_is_what_moves_it() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, _, _ = second(book).rect
    flat = lettered(second(place_lettering(book, screenplay, plan, frames(book))))
    assert flat.rect[:2] == (x + INSET, y + INSET)


def test_a_bubble_keeps_off_its_speakers_third_and_points_at_them() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    seen = {(0, 2): {"NANDI": Position.LEFT}}
    bubble = lettered(second(place_lettering(book, screenplay, plan, frames(book, solid, seen))))
    assert isinstance(bubble, Bubble) and bubble.kind is BubbleKind.SPEECH
    assert bubble.rect[0] >= x + w // 3  # off the left third
    assert bubble.tail == (x + w // 6, y + math.floor(h * 0.45))

    right = {(0, 2): {"Nandi": Position.RIGHT}}  # found by match_speaker, not by exact key
    bubble = lettered(second(place_lettering(book, screenplay, plan, frames(book, solid, right))))
    assert isinstance(bubble, Bubble)
    assert bubble.tail == (x + 5 * w // 6, y + math.floor(h * 0.45))
    assert bubble.rect[0] + bubble.rect[2] <= x + 2 * w // 3


def test_an_unknown_speaker_points_at_the_bottom_centre() -> None:
    screenplay, plan, book = one_panel("You came back.")
    x, y, w, h = second(book).rect
    bubble = lettered(second(place_lettering(book, screenplay, plan, frames(book))))
    assert isinstance(bubble, Bubble) and bubble.tail == (x + w // 2, y + h - 1)


@pytest.mark.parametrize(
    ("seen", "edge"),
    [({"NANDI": Position.LEFT}, "left"), ({"NANDI": Position.CENTRE}, "right"), ({}, "right")],
)
def test_an_off_panel_tail_ends_on_the_edge_of_the_speakers_side(
    seen: dict[str, Position], edge: str
) -> None:
    screenplay, plan, book = one_panel("You came back.", "O.S.")
    x, _, w, _ = second(book).rect
    placed = place_lettering(book, screenplay, plan, frames(book, solid, {(0, 2): seen}))
    bubble = lettered(second(placed))
    assert isinstance(bubble, Bubble) and bubble.kind is BubbleKind.OFF_PANEL
    bx, by, _, bh = bubble.rect
    assert bubble.tail == (x if edge == "left" else x + w - 1, by + bh // 2)
    assert bx >= x


def test_boxes_stay_inside_never_overlap_and_keep_reading_order() -> None:
    rng = random.Random(23)
    framings = list(Framing)
    lines = [
        "You came back.",
        "The boat didn't. I walked the last mile along the cliff.",
        "No.",
        "Hold the light steady, and whatever you hear, do not look down at the water.",
    ]
    for _ in range(12):
        scenes: list[Scene] = []
        shots: list[Shot] = []
        for index in range(rng.randint(1, 3)):
            spoken = [say(rng.choice(lines), rng.choice([None, "O.S.", "V.O."])) for _ in range(5)]
            scenes.append(scene(index, *spoken, location=f"DECK {index}"))
            start = 0
            for number in range(1, rng.randint(2, 4)):
                count = rng.randint(0, 2)
                shots.append(
                    shot(index, number, rng.choice(framings), *range(start, start + count))
                )
                start += count
        screenplay = Screenplay("", 1, tuple(scenes), (1,))
        plan = plan_of(*shots)
        book = layout_geometry(plan, screenplay)
        draw = rng.choice([solid, busy_left, busy_top])
        placed = place_lettering(book, screenplay, plan, frames(book, draw))

        for panel in panels(placed):
            x, y, w, h = panel.rect
            order = [c for c in panel.captions if c.kind is CaptionKind.SCENE] + sorted(
                [*panel.bubbles, *(c for c in panel.captions if c.kind is not CaptionKind.SCENE)],
                key=lambda t: t.element if t.element is not None else -1,
            )
            rects = [t.rect for t in order]
            for bx, by, bw, bh in rects:
                assert x + INSET <= bx and bx + bw <= x + w - INSET
                assert y + INSET <= by and by + bh <= y + h - INSET
            for i, a in enumerate(rects):
                assert not any(overlap(a, b) for b in rects[i + 1 :])
            cells = [cell(panel, r) for r in rects]
            assert all(a < b for a, b in pairwise(cells))  # strictly row-major, in element order
            assert all(t.font_px in (28, 32) for t in order)


def test_a_box_with_no_room_at_32_px_is_lettered_at_28() -> None:
    word = "Lighthouse"
    small = layout.font_at(layout.FONT_PATH, 28)
    ascent, descent = small.getmetrics()
    w = math.ceil(small.getlength(word)) + 2 * 16 + 2 * INSET
    h = ascent + descent + 2 * 16 + 2 * INSET
    screenplay, plan, book = one_panel(word, rect=(120, 120, w, h))
    placed = lettered(second(place_lettering(book, screenplay, plan, frames(book))))
    assert placed.font_px == 28
    assert placed.rect == (120 + INSET, 120 + INSET, w - 2 * INSET, h - 2 * INSET)


def test_no_admissible_spot_fails_naming_the_shot_and_never_cuts_the_line() -> None:
    text = "The boat didn't. I walked the last mile along the cliff."
    screenplay, plan, book = one_panel(text, rect=(120, 120, 300, 160))
    with pytest.raises(ComicError, match="scene 0, shot 2"):
        place_lettering(book, screenplay, plan, frames(book))


def test_a_character_the_font_cannot_draw_fails_rather_than_letter_a_box() -> None:
    screenplay, plan, book = one_panel("Ngiyabonga 謝謝")
    with pytest.raises(ComicError, match="scene 0, shot 2"):
        place_lettering(book, screenplay, plan, frames(book))


def test_reading_order_is_hard_even_when_an_earlier_spot_is_cheaper() -> None:
    # A frame busy everywhere but two flat patches: a small one at the top-left that only the
    # short second line fits, and one at row 4 exactly the first line's size. The first line
    # takes row 4; the second may not go before it, so it pays for detail instead.
    s = scene(0, say("You came back to the lighthouse."), say("No."))
    screenplay = Screenplay("", 1, (s,), (1,))
    plan = plan_of(shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, 0, 1))
    rect = (120, 120, 1300, 700)
    wide = Panel(0, 1, (120, 2000, 1300, 700), (), ())
    book = ComicBook(
        (Page(1, 1988, 3075, (wide, Panel(0, 2, rect, (), ()))),), LayoutReport(2, 0, 0, 0)
    )

    font = layout.font_at(layout.FONT_PATH, 32)
    ascent, descent = font.getmetrics()
    long_w = math.ceil(font.getlength("You came back to the lighthouse.")) + 32
    short_w = math.ceil(font.getlength("No.")) + 32
    box_h = ascent + descent + 32
    row4 = INSET + 4 * (700 - 2 * INSET) // 8
    assert long_w <= 520  # one line at the 40% wrap

    def two_patches(r: Rect) -> bytes:
        image = Image.open(BytesIO(busy(r, lambda w, h: (0, 0, w, h)))).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, INSET + short_w + 8, INSET + box_h + 8), fill=FLAT)
        draw.rectangle((INSET, row4, INSET + long_w - 1, row4 + box_h - 1), fill=FLAT)
        return png(image)

    placed = second(place_lettering(book, screenplay, plan, frames(book, two_patches)))
    first, then = placed.bubbles
    assert first.text == "You came back to the lighthouse." and then.text == "No."
    assert cell(placed, first.rect) == (4, 0)
    assert cell(placed, then.rect) > (4, 0)  # not the cheap top-left patch


def quiet_bottom_right(r: Rect) -> bytes:
    """PR #92's frame: vertical lines every 6 px everywhere but the bottom-right ninth."""
    _, _, w, h = r
    image = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, w, 6):
        draw.line([(x, 0), (x, h)], fill="black")
    draw.rectangle((w * 2 // 3, h * 2 // 3, w, h), fill="white")
    return png(image)


def two_lines(rect: Rect = (120, 120, 729, 850)) -> tuple[Screenplay, ShotPlan, ComicBook]:
    s = scene(
        0,
        say("All of it. But listen to me."),
        say("Hold the light steady, and whatever you hear, do not look down."),
    )
    screenplay = Screenplay("", 1, (s,), (1,))
    plan = plan_of(shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, 0, 1))
    wide = Panel(0, 1, (120, 2000, 729, 850), (), ())
    book = ComicBook(
        (Page(1, 1988, 3075, (wide, Panel(0, 2, rect, (), ()))),), LayoutReport(2, 0, 0, 0)
    )
    return screenplay, plan, book


def test_a_panel_quiet_only_low_down_moves_its_first_bubble_so_the_next_fits() -> None:
    # PR #92: the first bubble's cheapest spot is the quiet corner, late in the panel; placed one
    # at a time, the second line then had no cell after it and the comic stopped.
    screenplay, plan, book = two_lines()
    placed = second(place_lettering(book, screenplay, plan, frames(book, quiet_bottom_right)))
    first, then = placed.bubbles
    assert first.text == "All of it. But listen to me."
    assert then.text == "Hold the light steady, and whatever you hear, do not look down."
    assert cell(placed, first.rect) < cell(placed, then.rect)
    assert not overlap(first.rect, then.rect)


def test_the_search_stops_at_its_limit_and_names_the_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    screenplay, plan, book = two_lines()
    monkeypatch.setattr(bubbles, "SEARCH_LIMIT", 1)
    stopped = "scene 0, shot 2: no placement for its lines within 1 tries .*'Hold the light"
    with pytest.raises(ComicError, match=stopped):
        place_lettering(book, screenplay, plan, frames(book, quiet_bottom_right))


def one_at_a_time(
    panel: Panel, screenplay: Screenplay, plan: ShotPlan, frame: PanelFrame, first: bool
) -> list[tuple[Rect, int]] | None:
    """The rule before T065, as an oracle: each box the cheapest admissible cell after the last,
    never revisited; None where it found no room."""
    x, y, w, h = panel.rect
    (shot_,) = [
        s for s in plan.shots if (s.scene_index, s.number) == (panel.scene_index, panel.shot_number)
    ]
    scene_ = screenplay.scenes[panel.scene_index]
    image = frame_image(frame.png, (w, h), (panel.scene_index, panel.shot_number))
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    ix, iy, iw, ih = x + PADDING, y + PADDING, w - 2 * PADDING, h - 2 * PADDING
    corners = [((r, c), ix + c * iw // 12, iy + r * ih // 8) for r in range(8) for c in range(12)]
    placed: list[tuple[Rect, tuple[int, int], int]] = []
    for text in texts_of(shot_, scene_, first):
        after = placed[-1][1] if placed else None
        third = third_of(text.speaker, frame.positions, w)
        choice = None
        for size in (32, 28):
            bw, bh = box_size(
                text.text, math.floor(w * WRAP_SHARE), font_at(layout.FONT_PATH, size)
            )
            best = None
            for at, cx, cy in corners:
                if after is not None and at <= after:
                    continue
                if text.kind is CaptionKind.SCENE and at != (0, 0):
                    continue
                if cx + bw > ix + iw or cy + bh > iy + ih:
                    continue
                if any(overlaps((cx, cy, bw, bh), other) for other, _, _ in placed):
                    continue
                cost = detail(edges, (cx - x, cy - y, bw, bh))
                if third is not None and cx - x < third[1] and cx - x + bw > third[0]:
                    cost += 2.0
                if best is None or cost < best[0]:
                    best = (cost, ((cx, cy, bw, bh), at, size))
            if best is not None:
                choice = best[1]
                break
        if choice is None:
            return None
        placed.append(choice)
    return [(rect, size) for rect, _, size in placed]


def crossed(panel: Panel) -> bool:
    """Whether two of the panel's tails cross, two to one tip exempt (T112)."""
    drawn = [
        (b.tail, triangle)
        for b in panel.bubbles
        if b.tail is not None and (triangle := bubbles.tail_triangle(b.rect, b.tail)) is not None
    ]
    return any(
        tip != other and bubbles.tails_cross(a, b)
        for i, (tip, a) in enumerate(drawn)
        for other, b in drawn[i + 1 :]
    )


def test_every_panel_the_old_rule_letters_is_lettered_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The search without T112's tail rule is the old rule; with it, a panel changes only where
    the old placement's tails crossed, and then none of its tails cross."""
    rng = random.Random(65)
    changed = 0
    lines = [
        "You came back.",
        "The boat didn't. I walked the last mile along the cliff.",
        "No.",
        "Hold the light steady, and whatever you hear, do not look down at the water.",
    ]
    compared = 0
    for _ in range(10):
        scenes = [
            scene(
                i,
                *(say(rng.choice(lines), rng.choice([None, "O.S.", "V.O."])) for _ in range(4)),
                location=f"DECK {i}",
            )
            for i in range(rng.randint(1, 2))
        ]
        shots = [
            shot(
                i,
                n,
                rng.choice(list(Framing)),
                *range(2 * (n - 1), 2 * (n - 1) + rng.randint(0, 2)),
            )
            for i in range(len(scenes))
            for n in (1, 2)
        ]
        screenplay, plan = Screenplay("", 1, tuple(scenes), (1,)), plan_of(*shots)
        book = layout_geometry(plan, screenplay)
        given = frames(book, rng.choice([solid, busy_left, busy_top, quiet_bottom_right]))
        firsts = {s.scene_index: s.number for s in reversed(plan.shots)}
        try:
            kept = {
                (p.scene_index, p.shot_number): p
                for p in panels(place_lettering(book, screenplay, plan, given))
            }
            with monkeypatch.context() as patch:
                patch.setattr(bubbles, "tails_cross", lambda a, b: False)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
                placed = {
                    (p.scene_index, p.shot_number): p
                    for p in panels(place_lettering(book, screenplay, plan, given))
                }
        except ComicError as error:
            placed, kept, failed = {}, {}, error.shot
        else:
            failed = None
        for key, panel in placed.items():
            if crossed(panel):
                changed += 1
                assert kept[key] == panel or not crossed(kept[key])
            else:
                assert kept[key] == panel
        for panel in panels(book):
            key = (panel.scene_index, panel.shot_number)
            old = one_at_a_time(panel, screenplay, plan, given[key], firsts[key[0]] == key[1])
            if key == failed:
                assert old is None  # the search gives up only where the old rule did too
            if old is None or key not in placed:
                continue
            got = placed[key]
            order = [c for c in got.captions if c.kind is CaptionKind.SCENE] + sorted(
                [*got.bubbles, *(c for c in got.captions if c.kind is not CaptionKind.SCENE)],
                key=lambda t: t.element if t.element is not None else -1,
            )
            assert [(t.rect, t.font_px) for t in order] == old
            compared += 1
    assert compared >= 20
    assert changed >= 1  # the sample holds a panel whose old tails crossed


# ------------------------------------------------------------------------ frames


def test_a_withheld_card_letters_in_grid_order_with_the_cards_tails() -> None:
    s = scene(0, say("You came back."), say("Where?", "O.S."))
    screenplay = Screenplay("", 1, (s,), (1,))
    plan = plan_of(shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, 0, 1))
    book = layout_geometry(plan, screenplay)
    given = frames(book, busy_left)
    card = WithheldCard("unscripted person", Span(1, 1, 1))
    # Even if positions and pixels were passed, a card has no detail and no known speaker.
    given[(0, 2)] = PanelFrame(busy_left(second(book).rect), {"NANDI": Position.LEFT}, True, card)
    placed = second(place_lettering(book, screenplay, plan, given))

    x, y, w, _ = placed.rect
    speech, off = placed.bubbles
    assert speech.rect[:2] == (x + INSET, y + INSET)  # the earliest cell: detail is 0
    assert speech.tail is None  # no one to point at; a tail would cross the card's lines
    assert off.tail == (x + w - 1, off.rect[1] + off.rect[3] // 2)
    assert cell(placed, speech.rect) < cell(placed, off.rect)


def test_a_panel_without_a_frame_fails_naming_the_shot() -> None:
    screenplay, plan, book = sample()
    given = frames(book)
    del given[(1, 2)]
    with pytest.raises(ComicError, match="scene 1, shot 2"):
        place_lettering(book, screenplay, plan, given)


def test_a_frame_not_at_its_panels_size_fails_rather_than_being_cropped() -> None:
    screenplay, plan, book = one_panel("You came back.")
    given = frames(book)
    x, y, w, h = second(book).rect
    given[(0, 2)] = PanelFrame(solid((x, y, w, h - 1)), {}, False)
    with pytest.raises(ComicError, match="scene 0, shot 2"):
        place_lettering(book, screenplay, plan, given)


def test_a_panel_the_plan_does_not_have_fails() -> None:
    screenplay, _, book = one_panel("You came back.")
    with pytest.raises(ComicError, match="scene 0, shot 2"):
        place_lettering(book, screenplay, plan_of(shot(0, 1, Framing.WIDE)), frames(book))
