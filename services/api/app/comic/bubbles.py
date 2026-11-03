"""Lettering: which words go on a panel, and where. docs/design/comic.md §3, §4 steps 5-8.

Every bubble and caption letters a `Dialogue` element's text byte for byte, with that element's
span; the only other words are a scene's heading caption. Nothing is shortened: a box that finds
no room even at 28 px fails the comic, naming the shot, rather than lose a word.
"""

import logging
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageStat

from app.comic import layout
from app.comic.layout import PADDING, WRAP_SHARE, box_size, font_at, scene_caption
from app.comic.model import (
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
    Point,
    Rect,
    Voice,
)
from app.script import Dialogue, Scene, Screenplay, Span, match_speaker
from app.shots import Shot, ShotPlan
from app.verify.model import HeadSeen, Position

GRID_COLS, GRID_ROWS = 12, 8
FONT_SIZES = (32, 28)  # nominal, then the one smaller size; never lower
SPEAKER_COST = 2.0
HEAD_COST = 2.0  # T098: a box over anyone's head
HEAD_MARGIN = 12  # T098: px a head rect grows by, so a tail's tip stops short of the face
SPEAKER_HEIGHT = Fraction(9, 20)  # a speaker's point is at 45% of the panel height
SEARCH_LIMIT = 10_000  # candidate placements tried per panel before it fails (comic.md §4 step 7)
LINK_GAP = 120  # px: the most a connector may span between two linked boxes (T118)
LINK_WIDTH = 22  # px: a connector's width, inside its outline (T118)
MERGE_GAP = 16  # px: linked boxes closer than this merge at a seam (T120)
SEAM_DEPTH = 8  # px: how far a seam reaches into each box (T120)
LINKABLE = frozenset({Voice.PLAIN, Voice.SHOUT, Voice.DISTRESS})
TAIL_RULES = 2  # the first search's tail rules: 2 T112's and T116's, 1 T112's, 0 none
MAX_RADIUS = 48
TAIL_BASE = 28  # px: a tail's width at its base (comic.md §4 step 8)

type Kind = BubbleKind | CaptionKind
type Cell = tuple[int, int]  # (row, col)
type Triangle = tuple[tuple[float, float], ...]
type Shape = tuple[tuple[float, float], ...]  # a convex polygon, page px
type Circle = tuple[float, float, float]  # x, y, r (page px)

STROKE = 6  # px: the radio zigzag's white stroke, inside its black edge (comic.md §4 step 8)
EDGE = 3  # px: the black outline every balloon and tail is drawn with

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Text:
    """One thing to letter, before it has a box."""

    kind: Kind
    speaker: str | None
    text: str
    element: int | None
    span: Span
    voice: Voice = Voice.PLAIN
    linked: bool = False  # T118: joined to the text before it by a connector, no tail


@dataclass(frozen=True)
class _Placed:
    text: _Text
    rect: Rect
    cell: Cell
    font_px: int


def place_lettering(
    book: ComicBook,
    screenplay: Screenplay,
    plan: ShotPlan,
    frames: Mapping[tuple[int, int], PanelFrame],
) -> ComicBook:
    """Bubbles and captions for every panel, placed on its frame; the geometry is unchanged."""
    scenes = {scene.index: scene for scene in screenplay.scenes}
    shots = {(shot.scene_index, shot.number): shot for shot in plan.shots}
    firsts: dict[int, tuple[int, int]] = {}
    for shot in plan.shots:
        firsts.setdefault(shot.scene_index, (shot.scene_index, shot.number))

    pages: list[Page] = []
    bubbles = captions = 0
    for page in book.pages:
        panels: list[Panel] = []
        for panel in page.panels:
            key = (panel.scene_index, panel.shot_number)
            shot, scene = shots.get(key), scenes.get(panel.scene_index)
            if shot is None or scene is None:
                raise ComicError(
                    f"{panel_name(key)} is not in the shot plan or the screenplay", shot=key
                )
            frame = frames.get(key)
            if frame is None:
                raise ComicError(f"{panel_name(key)} has no frame", shot=key)
            texts = _texts(shot, scene, firsts[panel.scene_index] == key)
            placed, links = _place(panel, texts, frame)
            lettered = _lettered(panel, placed, frame, links)
            bubbles += len(lettered.bubbles)
            captions += len(lettered.captions)
            panels.append(lettered)
        pages.append(Page(page.number, page.width, page.height, tuple(panels)))
    report = LayoutReport(book.report.panels, bubbles, captions, book.report.relayouts)
    return ComicBook(tuple(pages), report)


def kind_of(extension: str | None) -> Kind:
    """comic.md §3: exhaustive over any extension, which is free text in the script."""
    upper = (extension or "").upper()
    if "V.O." in upper:
        return CaptionKind.VOICE_OVER
    if any(mark in upper for mark in ("O.S.", "O.C.", "OFF")):
        return BubbleKind.OFF_PANEL
    return BubbleKind.SPEECH


def _words(*options: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(options) + r")\b", re.IGNORECASE)


_PRONOUN = "(?:his|her|their|my)"
_DEVICE = _words(
    "radio", "phone", "telephone", "cellphone", "intercom", "speakerphone", "tv", "television",
    "loudspeaker", "announcer", "presenter", "newsreader", "voicemail", "walkie-talkie",
    "broadcast",
)  # fmt: skip
_DEVICE_EXTENSIONS = (
    "FILTERED",
    "ON PHONE",
    "ON THE PHONE",
    "ON RADIO",
    "ON TV",
    "ON P.A.",
    "ON SPEAKER",
)
_THOUGHT = _words("think", "thinks", "thinking", "thought", "thoughts", rf"in {_PRONOUN} head")
_SHOUT = _words(
    "shout(?:s|ing|ed)?", "yell(?:s|ing|ed)?", "scream(?:s|ing|ed)?", "bellow(?:s|ing|ed)?",
    "roar(?:s|ing|ed)?", rf"at the top of {_PRONOUN} lungs",
)  # fmt: skip
_WHISPER = _words(
    "whisper(?:s|ing|ed)?", "quietly", "softly", "murmur(?:s|ing|ed)?", "mutter(?:s|ing|ed)?",
    rf"under {_PRONOUN} breath", "barely audible", "hushed", "sotto voce",
)  # fmt: skip
_DISTRESS = _words(
    "crying", "sobbing", "sobs", "weakly", "trembling", "shaking", "shivering", "gasping",
    "wheezing", "slurring", "slurred", "drunk", "drunkenly", "through tears", "hoarse", "hoarsely",
    "choking",
)  # fmt: skip


_PAUSE = _words("beat", "pause", "pauses", "pausing", "a moment", "silence")


def voice_of(dialogue: Dialogue) -> Voice:
    """comic.md §3 (T117): the balloon's shape from the element's own words, first that applies.
    Never from the drawing or the line's punctuation: a shout is drawn where the script says so."""
    note = dialogue.parenthetical or ""
    extension = (dialogue.extension or "").upper()
    away = kind_of(dialogue.extension) is not BubbleKind.SPEECH  # V.O. or off-panel
    if any(phrase in extension for phrase in _DEVICE_EXTENSIONS) or (
        away and (_DEVICE.search(dialogue.cue) or _DEVICE.search(note))
    ):
        return Voice.RADIO
    for pattern, voice in (
        (_THOUGHT, Voice.THOUGHT),
        (_SHOUT, Voice.SHOUT),
        (_WHISPER, Voice.WHISPER),
        (_DISTRESS, Voice.DISTRESS),
    ):
        if pattern.search(note) or (pattern is _THOUGHT and pattern.search(extension)):
            return voice
    return Voice.PLAIN


def _lettering(dialogue: Dialogue) -> tuple[Kind, Voice]:
    """The kind (§3, with T117's two exceptions) and the voice a dialogue element is lettered in."""
    voice = voice_of(dialogue)
    kind = kind_of(dialogue.extension)
    if dialogue.cue.strip().upper() == "NARRATOR":
        kind = CaptionKind.VOICE_OVER  # a narration box: no one in the panel says it
    elif kind is CaptionKind.VOICE_OVER and voice is Voice.THOUGHT:
        kind = BubbleKind.SPEECH  # a thought is someone's in the panel; its trail points at them
    if isinstance(kind, CaptionKind) and voice is not Voice.RADIO:
        voice = Voice.PLAIN  # a caption carries no delivery
    return kind, voice


def _texts(shot: Shot, scene: Scene, first: bool) -> list[_Text]:
    texts: list[_Text] = []
    if first:
        heading = Span(scene.span.page, scene.span.line_start, scene.span.line_start)
        texts.append(_Text(CaptionKind.SCENE, None, scene_caption(scene), None, heading))
    for index in shot.elements:
        if not 0 <= index < len(scene.elements):
            raise ComicError(
                f"{panel_name((shot.scene_index, shot.number))} cites a missing element",
                shot=(shot.scene_index, shot.number),
            )
        element = scene.elements[index]
        if isinstance(element, Dialogue):  # action is never lettered; the art shows it
            kind, voice = _lettering(element)
            before = texts[-1] if texts else None
            linked = (
                before is not None
                and before.element is not None
                and isinstance(kind, BubbleKind)
                and (before.kind, before.speaker, before.voice) == (kind, element.cue, voice)
                and voice in LINKABLE
                and not _paused(element)
            )  # T118: one speaker's consecutive lines read as one balloon split in two
            texts.append(_Text(kind, element.cue, element.text, index, element.span, voice, linked))
    return texts


def _paused(second: Dialogue) -> bool:
    """T121: the script states a pause before one speaker's next line: a pause word in its
    parenthetical. An action line between doesn't count (Katlego, 2026-10-18): a screenplay puts
    action between nearly every two blocks of one speaker."""
    return bool(_PAUSE.search(second.parenthetical or ""))


def _place(panel: Panel, texts: Sequence[_Text], frame: PanelFrame) -> tuple[list[_Placed], bool]:
    """comic.md §4 step 7: the panel's boxes as a set. Depth-first in reading order, each box
    trying its candidates in preference order (32 px by cost, then 28 px); the first complete
    placement wins, so a panel one box at a time could letter is lettered exactly as before.
    Also whether its links (T118) held: the last-resort search drops them."""
    x, y, w, h = panel.rect
    key = (panel.scene_index, panel.shot_number)
    edges = None
    if not frame.withheld:
        edges = frame_image(frame.png, (w, h), key).convert("L").filter(ImageFilter.FIND_EDGES)
    positions: Mapping[str, Position] = {} if frame.withheld else frame.positions
    heads = [] if frame.withheld else [_head_rect(head, w, h) for head in frame.heads]
    lone = _lone_head(texts, frame)
    faces = [_page_rect(panel.rect, head) for head in heads]  # T116, in page px
    ix, iy, iw, ih = x + PADDING, y + PADDING, w - 2 * PADDING, h - 2 * PADDING
    corners = [
        ((row, col), ix + col * iw // GRID_COLS, iy + row * ih // GRID_ROWS)
        for row in range(GRID_ROWS)
        for col in range(GRID_COLS)
    ]
    limit = math.floor(w * WRAP_SHARE)
    for text in texts:
        missing = _missing_glyphs(text.text)
        if missing:
            raise ComicError(
                f"{panel_name(key)}: the lettering font has no glyph for {missing!r}, so "
                f"{text.text!r} can't be lettered as written",
                shot=key,
            )

    @cache
    def candidates(index: int, size: int) -> list[_Placed]:
        """Every in-panel spot for a box at a size, cheapest first (ties to the earlier cell);
        order and overlap depend on the boxes before it, so the search checks those."""
        text = texts[index]
        # T098: a known head replaces the third
        known = _head_for(text.speaker, frame, lone) is not None
        third = None if known else _third(text.speaker, positions, w)
        bw, bh = box_size(text.text, limit, font_at(layout.FONT_PATH, size))
        costed: list[tuple[float, _Placed]] = []
        for cell, cx, cy in corners:
            if text.kind is CaptionKind.SCENE and cell != (0, 0):
                continue  # the heading caption sits at the top-left
            if cx + bw > ix + iw or cy + bh > iy + ih:
                continue
            cost = _cost(edges, (cx - x, cy - y, bw, bh), third, heads)
            costed.append((cost, _Placed(text, (cx, cy, bw, bh), cell, size)))
        costed.sort(key=lambda pair: pair[0])  # stable: row-major among equal costs
        return [placed for _, placed in costed]

    @cache
    def tail_of(index: int, box: Rect) -> _Tail | None:
        """The tail step 8 draws for this box: its tip, its hull (T112, T116) and the face its
        tip ends in, the one face it may cross."""
        text = texts[index]
        tip = _tip(text, frame, panel.rect, box, lone)
        if tip is None:
            return None
        own = next((face for face in faces if _inside(tip, face)), None)
        return _Tail(tip, tail_hull(text.voice, box, tip), own, frozenset({index}))

    placed: list[_Placed] = []  # placed[i] letters texts[i]
    drawn: list[list[_Tail]] = []  # each placed box's tails and connectors, while a rule holds
    tries = 0
    stuck = 0  # the furthest box the search reached: the one that found no room
    refused = False  # a candidate was refused for a tail (T112, T116, T118)

    def judged(index: int, option: _Placed, rules: int) -> tuple[bool, list[_Tail]]:
        """Whether a candidate keeps the tail rules (2 all, 1 T112's and the link gap, 0 none),
        and the tails and connectors it brings: its connector to the box before it (T118), and,
        when it closes a chain, the chain's one tail from the box nearest the speaker (T119). A
        tail or connector of a box it joins is never "another"."""
        nonlocal refused
        if rules == 0:
            return True, []
        shapes: list[_Tail] = []
        broken = False
        if texts[index].linked:
            before = placed[-1].rect
            band = _connector(before, option.rect, EDGE)
            shapes.append(_Tail(None, band, None, frozenset({index - 1, index})))
            broken = _gap(before, option.rect) > LINK_GAP
        if not broken and (index + 1 == len(texts) or not texts[index + 1].linked):
            start = index
            while texts[start].linked:
                start -= 1
            rects = [p.rect for p in placed[start:index]] + [option.rect]
            k = start + _nearest(texts[start : index + 1], rects, frame, panel.rect, lone)
            tail = tail_of(k, rects[k - start])
            if tail is not None:
                # a box over its own tip draws no tail, so no rule could see it: it would trade
                # a tail under a bubble for a bubble over the speaker's mouth
                broken = tail.hull is None
                shapes.append(tail)
        others = [o for group in drawn for o in group if o.hull is not None]
        boxes = [*((j, p.rect) for j, p in enumerate(placed)), (index, option.rect)]
        for n, shape in enumerate(shapes):
            hull = shape.hull
            if broken or hull is None:
                continue
            broken = any(
                not (other.owners & shape.owners)
                and not (other.tip is not None and other.tip == shape.tip)
                and other.hull is not None
                and tails_cross(hull, other.hull)
                for other in [*others, *shapes[:n]]
            )  # T112: tails never cross, but two to one tip may meet
            if not broken and rules == 2:  # T116: clear of boxes and faces
                broken = any(
                    j not in shape.owners and tails_cross(hull, _corners(rect)) for j, rect in boxes
                ) or any(face != shape.face and tails_cross(hull, _corners(face)) for face in faces)
        if not broken and rules == 2:
            box = _corners(option.rect)
            broken = any(
                index not in other.owners
                and other.hull is not None
                and tails_cross(other.hull, box)
                for other in others
            )
        refused = refused or broken
        return not broken, shapes

    def search(index: int, rules: int) -> bool:
        nonlocal tries, stuck
        if index == len(texts):
            return True
        stuck = max(stuck, index)
        after = placed[-1].cell if placed else None
        for size in FONT_SIZES:
            for option in candidates(index, size):
                if after is not None and option.cell <= after:
                    continue  # reading order is hard
                if any(_overlap(option.rect, other.rect) for other in placed):
                    continue
                ok, shapes = judged(index, option, rules)
                if not ok:
                    continue
                tries += 1
                if tries > SEARCH_LIMIT:
                    return False
                placed.append(option)
                drawn.append(shapes)
                if search(index + 1, rules):
                    return True
                placed.pop()
                drawn.pop()
        return False

    found = search(0, TAIL_RULES)
    used = TAIL_RULES
    for rules, warning in (
        (1, "a tail runs under a bubble or across a face on %s: no placement keeps it clear"),
        (0, "tails cross on %s: no placement keeps them apart"),
    ):
        if found or not refused:
            break
        if rules >= TAIL_RULES:
            continue
        # the last resorts (T116, then T112): fewer tail rules, each with its own tries
        placed.clear()
        drawn.clear()
        tries = stuck = 0
        refused = False
        found = search(0, rules)
        used = rules
        if found:
            log.warning(warning, panel_name(key))
    if not found:
        if tries > SEARCH_LIMIT:
            raise ComicError(
                f"{panel_name(key)}: no placement for its lines within {SEARCH_LIMIT:,} tries "
                f"(stopped at {texts[stuck].text!r}), and no line is ever cut",
                shot=key,
            )
        raise ComicError(
            f"{panel_name(key)}: no room to letter {texts[stuck].text!r} even at "
            f"{FONT_SIZES[-1]} px; the panel is too small for its lines, and no line is ever cut",
            shot=key,
        )
    return placed, used > 0


def _lettered(panel: Panel, placed: Sequence[_Placed], frame: PanelFrame, links: bool) -> Panel:
    lone = _lone_head([item.text for item in placed], frame)
    tailed: set[int] = set()  # T119: each chain's one tail, on its box nearest the speaker
    start = 0
    for index, item in enumerate(placed):
        if not (links and item.text.linked):
            start = index
        if index + 1 == len(placed) or not (links and placed[index + 1].text.linked):
            chain = placed[start : index + 1]
            texts_ = [p.text for p in chain]
            tailed.add(start + _nearest(texts_, [p.rect for p in chain], frame, panel.rect, lone))
    bubbles: list[Bubble] = []
    captions: list[Caption] = []
    for index, item in enumerate(placed):
        text = item.text
        if isinstance(text.kind, CaptionKind):
            captions.append(
                Caption(
                    text.kind,
                    text.text,
                    text.element,
                    text.span,
                    item.rect,
                    item.font_px,
                    text.voice,
                )
            )
            continue
        assert text.speaker is not None and text.element is not None
        linked = links and text.linked  # T118: joined to the bubble before it
        tail = _tip(text, frame, panel.rect, item.rect, lone) if index in tailed else None
        bubbles.append(
            Bubble(
                text.kind,
                text.speaker,
                text.text,
                text.element,
                text.span,
                item.rect,
                tail,
                item.font_px,
                text.voice,
                linked,
            )
        )
    return Panel(panel.scene_index, panel.shot_number, panel.rect, tuple(bubbles), tuple(captions))


@dataclass(frozen=True)
class _Tail:
    """A tail or a connector (T118), as the tail rules see it."""

    tip: Point | None  # None for a connector
    hull: Shape | None  # None: the tip is inside the box, so no tail is drawn
    face: Rect | None  # the head rect (page px) its tip ends in: the one face it may cross
    owners: frozenset[int]  # the texts whose boxes it joins: their boxes and tails aren't "other"


def _tip(
    text: _Text,
    frame: PanelFrame,
    panel: Rect,
    box: Rect,
    lone: tuple[str, HeadSeen] | None = None,
) -> Point | None:
    """comic.md §4 step 8: where a box's tail ends, in page pixels. None for a caption, and for a
    speech bubble on a card: no one is in the panel, and a tail would cross its lines."""
    if isinstance(text.kind, CaptionKind) or (frame.withheld and text.kind is BubbleKind.SPEECH):
        return None
    head = _head_for(text.speaker, frame, lone)
    if head is not None and text.kind is BubbleKind.SPEECH:
        # T117: a thought comes from the head's centre; speech from the mouth (T114)
        down = Fraction(1, 2) if text.voice is Voice.THOUGHT else Fraction(5, 6)
        return _to_mouth(head, panel, box, down)
    positions: Mapping[str, Position] = {} if frame.withheld else frame.positions
    return _tail(text.kind, _position(text.speaker, positions), panel, box)


def _tail(kind: BubbleKind, position: Position | None, panel: Rect, box: Rect) -> Point:
    """comic.md §4 step 8: the tip, in page pixels, always inside the panel."""
    x, y, w, h = panel
    if kind is BubbleKind.OFF_PANEL:
        middle = box[1] + box[3] // 2
        return (x, middle) if position is Position.LEFT else (x + w - 1, middle)
    if position is None:
        return x + w // 2, y + h - 1
    centre = {Position.LEFT: w // 6, Position.CENTRE: w // 2, Position.RIGHT: 5 * w // 6}
    return x + centre[position], y + math.floor(h * SPEAKER_HEIGHT)


def corner_radius(rect: Rect) -> int:
    """A bubble's corner radius (comic.md §4 step 7): min(48, h/2, w/2)."""
    return min(MAX_RADIUS, rect[3] // 2, rect[2] // 2)


def tail_triangle(box: Rect, tip: Point) -> Triangle | None:
    """comic.md §4 step 8: the tail, 28 px wide at its base, from the point of the box shrunk by
    its corner radius nearest the tip, to the tip; None when the tip is inside the box. Placement
    tests crossings with it and render.py draws it, so the two never disagree (T112)."""
    x, y, w, h = box
    tx, ty = tip
    if x <= tx < x + w and y <= ty < y + h:
        return None
    base = _tail_base(box, tip)
    dx, dy = tx - base[0], ty - base[1]
    length = math.hypot(dx, dy)
    px, py = -dy / length * TAIL_BASE / 2, dx / length * TAIL_BASE / 2
    return (base[0] + px, base[1] + py), (float(tx), float(ty)), (base[0] - px, base[1] - py)


def _tail_base(box: Rect, tip: Point) -> Point:
    """The point of the box shrunk by its corner radius nearest the tip: where a tail starts."""
    x, y, w, h = box
    r = corner_radius(box)
    return min(max(tip[0], x + r), x + w - 1 - r), min(max(tip[1], y + r), y + h - 1 - r)


def _outside(box: Rect, tip: Point) -> bool:
    x, y, w, h = box
    return not (x <= tip[0] < x + w and y <= tip[1] < y + h)


def _leaves(box: Rect, start: Point, tip: Point) -> tuple[float, float]:
    """Where the line from `start` (inside the box) to `tip` (outside) leaves the box."""
    x, y, w, h = box
    leave = 1.0
    for s, t, low, high in ((start[0], tip[0], x, x + w - 1), (start[1], tip[1], y, y + h - 1)):
        if t > high:
            leave = min(leave, (high - s) / (t - s))
        elif t < low:
            leave = min(leave, (s - low) / (s - t))
    return start[0] + leave * (tip[0] - start[0]), start[1] + leave * (tip[1] - start[1])


def thought_trail(box: Rect, tip: Point) -> tuple[Circle, ...]:
    """comic.md §4 step 8 (T117): three circles, radii 12, 8 and 5, at 25%, 55% and 85% of the
    way from where the line from the tail's base leaves the box to the tip; () when the tip is
    inside the box."""
    if not _outside(box, tip):
        return ()
    ex, ey = _leaves(box, _tail_base(box, tip), tip)
    return tuple(
        (ex + f * (tip[0] - ex), ey + f * (tip[1] - ey), r)
        for f, r in ((0.25, 12.0), (0.55, 8.0), (0.85, 5.0))
    )


def radio_zigzag(box: Rect, tip: Point) -> tuple[tuple[float, float], ...]:
    """comic.md §4 step 8 (T117): the lightning stroke's points, from the tail's base through
    35%, 55% and 75% of the way to the tip, pushed sideways +16, -16 and +10 px, to the tip."""
    if not _outside(box, tip):
        return ()
    bx, by = _tail_base(box, tip)
    dx, dy = tip[0] - bx, tip[1] - by
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    middle = tuple(
        (bx + f * dx + push * nx, by + f * dy + push * ny)
        for f, push in ((0.35, 16.0), (0.55, -16.0), (0.75, 10.0))
    )
    return ((float(bx), float(by)), *middle, (float(tip[0]), float(tip[1])))


def tail_hull(voice: Voice, box: Rect, tip: Point) -> Shape | None:
    """comic.md §4 steps 7-8 (T116, T117): the convex hull of the tail drawn for this voice, which
    the tail rules judge; None when no tail is drawn (the tip is inside the box)."""
    if voice is Voice.THOUGHT:
        out = 1 / math.cos(math.pi / 8)  # an octagon this much wider holds its circle
        points = [
            (cx + r * out * math.cos(k * math.pi / 4), cy + r * out * math.sin(k * math.pi / 4))
            for cx, cy, r in thought_trail(box, tip)
            for k in range(8)
        ]
        return _hull(points) if points else None
    if voice is Voice.RADIO:
        half = STROKE / 2 + EDGE
        zigzag = radio_zigzag(box, tip)
        points = [
            (px + sx * half, py + sy * half)
            for px, py in zigzag
            for sx in (-1, 1)
            for sy in (-1, 1)
        ]
        return _hull(points) if points else None
    return tail_triangle(box, tip)


def _hull(points: Sequence[tuple[float, float]]) -> Shape:
    """The convex hull, counter-clockwise (Andrew's monotone chain)."""
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return tuple(ordered)

    def turn(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    upper: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def connector(a: Rect, b: Rect) -> Shape:
    """comic.md §4 step 8: what joins two linked boxes, as render.py draws it: the seam when they
    nearly touch (T120), else the band centre to centre, LINK_WIDTH wide (T118). Its ends are
    hidden under the two boxes' fills."""
    return _connector(a, b, 0)


def _connector(a: Rect, b: Rect, grow: float) -> Shape:
    """The connector grown by `grow` px all round: the tail rules judge it grown by the outline."""
    seam = _seam(a, b, grow) if _gap(a, b) < MERGE_GAP else None
    return seam if seam is not None else _band(a, b, LINK_WIDTH + 2 * grow)


def _seam(a: Rect, b: Rect, grow: float) -> Shape | None:
    """T120: a rectangle across the two boxes' overlap, inset by half the larger corner radius, from
    SEAM_DEPTH px inside one to SEAM_DEPTH px inside the other; None when the overlap, inset, is
    narrower than LINK_WIDTH, or the boxes aren't one above or beside the other."""
    r = max(corner_radius(a), corner_radius(b)) // 2  # half: two pills side by side still merge
    if a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]:  # one above the other
        top, bottom = (a, b) if a[1] < b[1] else (b, a)
        low = max(top[0], bottom[0]) + r
        high = min(top[0] + top[2], bottom[0] + bottom[2]) - r
        start, end = top[1] + top[3] - SEAM_DEPTH, bottom[1] + SEAM_DEPTH
        if high - low < LINK_WIDTH:
            return None
        return (
            (low - grow, start - grow), (high + grow, start - grow),
            (high + grow, end + grow), (low - grow, end + grow),
        )  # fmt: skip
    if a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]:  # side by side
        left, right = (a, b) if a[0] < b[0] else (b, a)
        low = max(left[1], right[1]) + r
        high = min(left[1] + left[3], right[1] + right[3]) - r
        start, end = left[0] + left[2] - SEAM_DEPTH, right[0] + SEAM_DEPTH
        if high - low < LINK_WIDTH:
            return None
        return (
            (start - grow, low - grow), (end + grow, low - grow),
            (end + grow, high + grow), (start - grow, high + grow),
        )  # fmt: skip
    return None


def _nearest(
    texts: Sequence[_Text],
    rects: Sequence[Rect],
    frame: PanelFrame,
    panel: Rect,
    lone: tuple[str, HeadSeen] | None,
) -> int:
    """T119: which box of a linked chain has its tail: the one whose centre is nearest the tip it
    would have (ties to the earlier); the first when none has a tip."""
    best, best_distance = 0, math.inf
    for n, (text, rect) in enumerate(zip(texts, rects, strict=True)):
        tip = _tip(text, frame, panel, rect, lone)
        if tip is None:
            continue
        distance = math.hypot(rect[0] + rect[2] / 2 - tip[0], rect[1] + rect[3] / 2 - tip[1])
        if distance < best_distance:
            best, best_distance = n, distance
    return best


def _band(a: Rect, b: Rect, width: float) -> Shape:
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    length = math.hypot(bx - ax, by - ay)
    nx, ny = -(by - ay) / length * width / 2, (bx - ax) / length * width / 2
    return (ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)


def _gap(a: Rect, b: Rect) -> float:
    """The shortest distance between two boxes (T118's LINK_GAP)."""
    dx = max(0, b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
    dy = max(0, b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
    return math.hypot(dx, dy)


def _corners(rect: Rect) -> Shape:
    """A rect's pixels as a closed shape: (x, y) to (x + w - 1, y + h - 1)."""
    x, y, w, h = rect
    right, bottom = float(x + w - 1), float(y + h - 1)
    return (float(x), float(y)), (right, float(y)), (right, bottom), (float(x), bottom)


def _page_rect(panel: Rect, rect: Rect) -> Rect:
    return panel[0] + rect[0], panel[1] + rect[1], rect[2], rect[3]


def _inside(point: Point, rect: Rect) -> bool:
    return rect[0] <= point[0] < rect[0] + rect[2] and rect[1] <= point[1] < rect[1] + rect[3]


def tails_cross(a: Sequence[tuple[float, float]], b: Sequence[tuple[float, float]]) -> bool:
    """Whether two tails share a point, touching included (T112). Two convex shapes are apart
    exactly when some edge's normal strictly separates their projections."""
    for shape in (a, b):
        for (x0, y0), (x1, y1) in zip(shape, (*shape[1:], shape[0]), strict=True):
            nx, ny = y0 - y1, x1 - x0
            on_a = [nx * px + ny * py for px, py in a]
            on_b = [nx * px + ny * py for px, py in b]
            if max(on_a) < min(on_b) or max(on_b) < min(on_a):
                return False
    return True


def _cost(
    edges: Image.Image | None, box: Rect, third: tuple[int, int] | None, heads: Sequence[Rect]
) -> float:
    """comic.md §4 step 7: a panel-relative box's cost: its detail, plus HEAD_COST when it covers
    any head rect (T098), plus SPEAKER_COST when it overlaps the speaker's third (None: no cost)."""
    cost = _detail(edges, box)
    if any(_overlap(box, head) for head in heads):
        cost += HEAD_COST
    if third is not None and box[0] < third[1] and box[0] + box[2] > third[0]:
        cost += SPEAKER_COST
    return cost


def _head_rect(head: HeadSeen, w: int, h: int) -> Rect:
    """A head's box in panel pixels (T098), grown by HEAD_MARGIN and clipped to the panel."""
    x0, y0, x1, y1 = head.box
    left = max(0, math.floor(x0 * w) - HEAD_MARGIN)
    top = max(0, math.floor(y0 * h) - HEAD_MARGIN)
    right = min(w, math.ceil(x1 * w) + HEAD_MARGIN)
    bottom = min(h, math.ceil(y1 * h) + HEAD_MARGIN)
    return left, top, right - left, bottom - top


def _lone_head(texts: Sequence[_Text], frame: PanelFrame) -> tuple[str, HeadSeen] | None:
    """comic.md §4 step 7 (T115): the frame's one head, unnamed, is the speaker's when the panel's
    in-panel lines have one speaker, unless the positions put that speaker in another third."""
    if frame.withheld or len(frame.heads) != 1 or frame.heads[0].character is not None:
        return None
    speakers = {t.speaker for t in texts if t.kind is BubbleKind.SPEECH and t.speaker is not None}
    if len(speakers) != 1:
        return None
    (speaker,) = speakers
    head = frame.heads[0]
    position = _position(speaker, frame.positions)
    if position is not None:
        centre = (head.box[0] + head.box[2]) / 2
        third = (
            Position.LEFT
            if centre < 1 / 3
            else Position.CENTRE
            if centre < 2 / 3
            else Position.RIGHT
        )
        if third is not position:
            return None
    return speaker, head


def _head_for(
    speaker: str | None, frame: PanelFrame, lone: tuple[str, HeadSeen] | None
) -> HeadSeen | None:
    """The speaker's head: named by the head agent (T098), else the lone unnamed head (T115)."""
    if frame.withheld:
        return None
    named = _speaker_head(speaker, frame.heads)
    if named is None and lone is not None and speaker == lone[0]:
        return lone[1]
    return named


def _speaker_head(speaker: str | None, heads: Sequence[HeadSeen]) -> HeadSeen | None:
    """The speaker's head (T098): the head whose character `match_speaker` finds for them."""
    named = [head for head in heads if head.character is not None]
    if speaker is None or not named:
        return None
    name = match_speaker(speaker, [head.character for head in named if head.character])
    return next((head for head in named if head.character == name), None)


def _to_mouth(head: HeadSeen, panel: Rect, box: Rect, down: Fraction = Fraction(5, 6)) -> Point:
    """comic.md §4 step 8 (T114): the tail aims at the mouth, the centre of the head box's lower
    third, and ends where the line from the bubble's centre to it enters the grown head rect, so
    the tip stops short of the face. In page pixels, inside the rect and so inside the panel."""
    x, y, w, h = panel
    x0, y0, x1, y1 = head.box
    left, top = math.floor(x0 * w), math.floor(y0 * h)
    right, bottom = math.ceil(x1 * w), math.ceil(y1 * h)
    mouth = ((left + right) / 2, top + float(down) * (bottom - top))
    hx, hy, hw, hh = _head_rect(head, w, h)
    centre = (box[0] + box[2] // 2 - x, box[1] + box[3] // 2 - y)
    enter = 0.0  # how far along the line, centre to mouth, it enters the rect
    for c, m, low, high in (
        (centre[0], mouth[0], hx, hx + hw - 1),
        (centre[1], mouth[1], hy, hy + hh - 1),
    ):
        if c < low:
            enter = max(enter, (low - c) / (m - c))
        elif c > high:
            enter = max(enter, (c - high) / (c - m))
    tx = math.floor(centre[0] + enter * (mouth[0] - centre[0]) + 0.5)
    ty = math.floor(centre[1] + enter * (mouth[1] - centre[1]) + 0.5)
    return x + min(max(tx, hx), hx + hw - 1), y + min(max(ty, hy), hy + hh - 1)


def _position(speaker: str | None, positions: Mapping[str, Position]) -> Position | None:
    if speaker is None:
        return None
    name = match_speaker(speaker, list(positions))
    return None if name is None else positions[name]


def _third(
    speaker: str | None, positions: Mapping[str, Position], w: int
) -> tuple[int, int] | None:
    """The speaker's third of the panel as panel-relative [start, end), or None when unknown."""
    position = _position(speaker, positions)
    if position is None:
        return None
    bounds = {
        Position.LEFT: (0, w // 3),
        Position.CENTRE: (w // 3, 2 * w // 3),
        Position.RIGHT: (2 * w // 3, w),
    }
    return bounds[position]


def frame_image(png: bytes, size: tuple[int, int], key: tuple[int, int]) -> Image.Image:
    """An accepted frame, decoded; it must be exactly its panel's size (comic.md §4 step 6)."""
    try:
        image = Image.open(BytesIO(png))
        image.load()
    except (OSError, ValueError) as error:
        raise ComicError(
            f"{panel_name(key)}: its frame is not a readable image", shot=key
        ) from error
    if image.size != size:
        raise ComicError(
            f"{panel_name(key)}: its frame is {image.size[0]} x {image.size[1]}, not its panel's "
            f"{size[0]} x {size[1]}; frames are rendered at the panel's size, never cropped",
            shot=key,
        )
    return image


def _detail(edges: Image.Image | None, box: Rect) -> float:
    """Mean edge strength over the box, 0-1; a withheld card has none."""
    if edges is None:
        return 0.0
    bx, by, bw, bh = box
    return ImageStat.Stat(edges.crop((bx, by, bx + bw, by + bh))).mean[0] / 255


def _missing_glyphs(text: str) -> str:
    """Characters the font would draw as its empty box: a word lettered as boxes is a word lost."""
    notdef = _glyph(layout.FONT_PATH, "\uffff")
    return "".join(
        sorted({ch for ch in text if not ch.isspace() and _glyph(layout.FONT_PATH, ch) == notdef})
    )


@cache
def _glyph(path: Path, ch: str) -> bytes:
    """A character as the font draws it, alone on a small canvas."""
    image = Image.new("L", (96, 96))
    ImageDraw.Draw(image).text((16, 16), ch, font=font_at(path, FONT_SIZES[0]), fill=255)
    return image.tobytes()


def _overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def panel_name(key: tuple[int, int]) -> str:
    return f"scene {key[0]}, shot {key[1]}"
