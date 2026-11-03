"""Comic pages as pixels, a PDF and the reader's JSON. docs/design/comic.md §4 steps 6-8, §6.

A withheld frame is never drawn: its panel shows the withheld card, and `PanelFrame.withheld` is
the switch, so a withheld frame's bytes are never even decoded.
"""

import math
from collections.abc import Mapping, Sequence
from io import BytesIO
from itertools import pairwise

from PIL import Image, ImageDraw

from app.comic import layout
from app.comic.bubbles import (
    STROKE,
    connector,
    corner_radius,
    frame_image,
    panel_name,
    radio_zigzag,
    tail_triangle,
    thought_trail,
)
from app.comic.layout import FONT_PX, PADDING, WRAP_SHARE, font_at, wrap
from app.comic.model import (
    Bubble,
    Caption,
    ComicBook,
    ComicError,
    Panel,
    PanelFrame,
    Rect,
    Voice,
    WithheldCard,
)
from app.script import Span
from app.shots import Shot
from app.verify.model import Audit, Check, FrameOutcome, FrameState, Severity, Verdict

DPI = 300
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
CARD_GREY = (128, 128, 128)  # #808080
CAPTION_FILL = (255, 244, 194)  # #FFF4C2
PANEL_BORDER = CARD_BORDER = 4
OUTLINE = 3
DASH, GAP = 12, 8  # px: a whisper's outline (comic.md §4 step 7, T117)
BURST_DEPTH, BURST_STEP = 9, 36  # px: a shout's valleys, and a peak-to-peak spacing
WAVE_DEPTH, WAVE_LENGTH = 5, 24  # px: a distressed outline's wave
CUT = 14  # px: a radio box's cut corners
CLOUD_CORE, CLOUD_R, CLOUD_STEP = 8, 11, 24  # px: a thought cloud's core inset, scallops, spacing

type Key = tuple[int, int]
type RGB = tuple[int, int, int]
type Path = list[tuple[float, float]]


def withheld_checks(audit: Audit) -> str:
    """The card's <checks>: `audit error`, or the failed hard checks in `Check` order."""
    if audit.verdict is Verdict.ERROR:
        return "audit error"
    failed = {r.check for r in audit.checks if r.severity is Severity.HARD and not r.ok}
    return ", ".join(check.value.replace("_", " ") for check in Check if check in failed)


def panel_frame(outcome: FrameOutcome, shot: Shot) -> PanelFrame:
    """verify's outcome as the comic needs it: the accepted frame, or only the card."""
    key = (shot.scene_index, shot.number)
    if outcome.shot != key:
        raise ComicError(
            f"{panel_name(key)} was given the outcome of {panel_name(outcome.shot)}", shot=key
        )
    last = outcome.audits[-1] if outcome.audits else None
    if outcome.state in (FrameState.PASSED, FrameState.WARNED):
        if outcome.frame is None or last is None:
            raise ComicError(
                f"{panel_name(key)} is {outcome.state} without its frame and audit", shot=key
            )
        return PanelFrame(outcome.frame.png, dict(last.positions), False, heads=last.heads)
    if outcome.state is FrameState.WITHHELD:
        checks = "" if last is None else withheld_checks(last)
        if not checks:
            raise ComicError(f"{panel_name(key)} is withheld without a failed hard check", shot=key)
        return PanelFrame(b"", {}, True, WithheldCard(checks, shot.span))
    raise ComicError(
        f"{panel_name(key)}: its frame is {outcome.state}, not accepted or withheld", shot=key
    )


def failed_panel(shot: Shot) -> PanelFrame:
    """A panel whose renderer raised (comic.md §4 step 6, T067): only the failed card."""
    return PanelFrame(b"", {}, True, WithheldCard("", shot.span, failed=True))


def card_lines(card: WithheldCard) -> tuple[str, str]:
    span = card.span
    first = (
        "Frame not drawn: the renderer failed"
        if card.failed
        else f"Frame withheld: failed audit ({card.checks})"
    )
    return first, f"Script p.{span.page} l.{span.line_start}\u2013{span.line_end}"  # an en dash


def render_pages(book: ComicBook, frames: Mapping[Key, PanelFrame]) -> list[bytes]:
    """One PNG per page: each panel's frame (or card) at its rect, then its lettering."""
    out: list[bytes] = []
    for page in book.pages:
        canvas = Image.new("RGB", (page.width, page.height), WHITE)
        for panel in page.panels:
            key = (panel.scene_index, panel.shot_number)
            frame = frames.get(key)
            if frame is None:
                raise ComicError(f"{panel_name(key)} has no frame", shot=key)
            canvas.paste(_tile(panel, frame, key), panel.rect[:2])
            _letter(ImageDraw.Draw(canvas), panel)
        buffer = BytesIO()
        canvas.save(buffer, "PNG")
        out.append(buffer.getvalue())
    return out


def to_pdf(pages: Sequence[bytes]) -> bytes:
    """One PDF page per page PNG, at 300 dpi: 1988 x 3075 px is the 6.625 x 10.25 in trim."""
    if not pages:
        raise ComicError("a comic PDF needs at least one page")
    images = [Image.open(BytesIO(page)).convert("RGB") for page in pages]
    buffer = BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=images[1:], resolution=DPI)
    return buffer.getvalue()


def to_json(book: ComicBook, frame_urls: Mapping[Key, str]) -> dict[str, object]:
    """T024's layout JSON (comic.md §6). A shot with no URL is withheld and has no frame_url."""
    return {
        "pages": [
            {
                "number": page.number,
                "width": page.width,
                "height": page.height,
                "panels": [_panel_json(panel, frame_urls) for panel in page.panels],
            }
            for page in book.pages
        ]
    }


def _panel_json(panel: Panel, frame_urls: Mapping[Key, str]) -> dict[str, object]:
    key = (panel.scene_index, panel.shot_number)
    out: dict[str, object] = {"shot": list(key), "rect": list(panel.rect)}
    url = frame_urls.get(key)
    if url is not None:
        out["frame_url"] = url
    out["withheld"] = url is None
    out["bubbles"] = [
        {
            "kind": b.kind.value,
            "speaker": b.speaker,
            "text": b.text,
            "element": b.element,
            "span": _span_json(b.span),
            "rect": list(b.rect),
            "tail": None if b.tail is None else list(b.tail),
            "font_px": b.font_px,
            "voice": b.voice.value,
            "linked": b.linked,
        }
        for b in panel.bubbles
    ]
    out["captions"] = [
        {
            "kind": c.kind.value,
            "text": c.text,
            "element": c.element,
            "span": _span_json(c.span),
            "rect": list(c.rect),
            "font_px": c.font_px,
            "voice": c.voice.value,
        }
        for c in panel.captions
    ]
    return out


def _span_json(span: Span) -> dict[str, int]:
    return {"page": span.page, "line_start": span.line_start, "line_end": span.line_end}


def _tile(panel: Panel, frame: PanelFrame, key: Key) -> Image.Image:
    _, _, w, h = panel.rect
    if frame.withheld:
        assert frame.card is not None  # PanelFrame guarantees it
        return _card(w, h, frame.card)
    tile = frame_image(frame.png, (w, h), key).convert("RGB")
    ImageDraw.Draw(tile).rectangle((0, 0, w - 1, h - 1), outline=BLACK, width=PANEL_BORDER)
    return tile


def _card(w: int, h: int, card: WithheldCard) -> Image.Image:
    """comic.md §4 step 6: white, a grey border, two centred lines; never the frame's pixels."""
    image = Image.new("RGB", (w, h), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w - 1, h - 1), outline=CARD_GREY, width=CARD_BORDER)
    font = font_at(layout.FONT_PATH, FONT_PX)
    ascent, descent = font.getmetrics()
    lines = [line for text in card_lines(card) for line in wrap(text, w - 2 * PADDING, font)]
    top = (h - len(lines) * (ascent + descent)) // 2
    for i, line in enumerate(lines):
        x = (w - font.getlength(line)) / 2
        draw.text((x, top + i * (ascent + descent)), line, font=font, fill=BLACK)
    return image


def _letter(draw: ImageDraw.ImageDraw, panel: Panel) -> None:
    """Every outline, then every fill, then a whisper's dashes, then every word: a tail under a
    bubble never hides text, and a dash never crosses a word (comic.md §4 step 7)."""
    items: list[Bubble | Caption] = [*panel.captions, *panel.bubbles]
    links = [  # T118: a linked bubble's connector to the bubble before it
        connector(before.rect, bubble.rect)
        for before, bubble in pairwise(panel.bubbles)
        if bubble.linked
    ]
    for outline in (True, False):
        for band in links:
            _shape(draw, list(band), BLACK if outline else WHITE, OUTLINE if outline else 0)
        for item in items:
            _balloon(draw, item, outline=outline)
    for item in items:
        if isinstance(item, Bubble) and item.voice is Voice.WHISPER:
            _whisper_dashes(draw, item)
    limit = math.floor(panel.rect[2] * WRAP_SHARE)
    for item in items:
        x, y, w, _ = item.rect
        font = font_at(layout.FONT_PATH, item.font_px)
        ascent, descent = font.getmetrics()
        for i, line in enumerate(wrap(item.text, limit, font)):
            left = x + (w - font.getlength(line)) / 2
            draw.text((left, y + PADDING + i * (ascent + descent)), line, font=font, fill=BLACK)


def _balloon(draw: ImageDraw.ImageDraw, item: Bubble | Caption, *, outline: bool) -> None:
    """One box and its tail, by voice (T117): in black grown by the outline, or in its fill."""
    x, y, w, h = item.rect
    colour = BLACK if outline else WHITE
    grow = OUTLINE if outline else 0
    if isinstance(item, Caption):
        if item.voice is Voice.RADIO:
            _shape(draw, _angular(item.rect), colour, grow)
        else:
            fill = BLACK if outline else CAPTION_FILL
            draw.rectangle((x - grow, y - grow, x + w - 1 + grow, y + h - 1 + grow), fill=fill)
        return
    voice = item.voice
    if voice is Voice.THOUGHT:
        circles, (core, radius) = _cloud(item.rect)
        for cx, cy, r in circles:
            draw.ellipse((cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow), fill=colour)
        cx0, cy0, cx1, cy1 = core
        draw.rounded_rectangle(
            (cx0 - grow, cy0 - grow, cx1 + grow, cy1 + grow), radius=radius + grow, fill=colour
        )
    elif voice is Voice.SHOUT:
        _shape(draw, _burst(item.rect), colour, grow)
    elif voice is Voice.DISTRESS:
        _shape(draw, _wavy(item.rect), colour, grow)
    elif voice is Voice.RADIO:
        _shape(draw, _angular(item.rect), colour, grow)
    elif not (outline and voice is Voice.WHISPER):  # a whisper's outline is its dashes
        box = (x - grow, y - grow, x + w - 1 + grow, y + h - 1 + grow)
        draw.rounded_rectangle(box, radius=corner_radius(item.rect) + grow, fill=colour)
    if item.tail is None:
        return
    if voice is Voice.THOUGHT:
        for cx, cy, r in thought_trail(item.rect, item.tail):
            draw.ellipse((cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow), fill=colour)
    elif voice is Voice.RADIO:
        zigzag = radio_zigzag(item.rect, item.tail)
        if zigzag:
            draw.line(list(zigzag), fill=colour, width=STROKE + 2 * grow, joint="curve")
    elif not (outline and voice is Voice.WHISPER):
        triangle = tail_triangle(item.rect, item.tail)
        if triangle is not None:
            _shape(draw, list(triangle), colour, grow)


def _shape(draw: ImageDraw.ImageDraw, points: Path, colour: RGB, grow: int) -> None:
    """A filled polygon, grown by `grow` px all round when it is an outline."""
    draw.polygon(points, fill=colour)
    if grow:
        draw.line([*points, points[0]], fill=colour, width=2 * grow, joint="curve")


def _whisper_dashes(draw: ImageDraw.ImageDraw, bubble: Bubble) -> None:
    """A whisper's dashed outline: the box's edge, the tail's opening cleared, the tail's sides
    outside the box (comic.md §4 steps 7-8)."""
    _dashed(draw, _rounded(bubble.rect), closed=True)
    triangle = None if bubble.tail is None else tail_triangle(bubble.rect, bubble.tail)
    if triangle is None:
        return
    draw.polygon(list(triangle), fill=WHITE)  # the opening: no dash across the tail's mouth
    tip = triangle[1]
    x, y, w, h = bubble.rect
    for corner in (triangle[0], triangle[2]):
        side = [
            point
            for point in _dense([corner, tip])
            if not (x <= point[0] < x + w and y <= point[1] < y + h)
        ]
        _dashed(draw, side, closed=False)


def _dashed(draw: ImageDraw.ImageDraw, path: Path, *, closed: bool) -> None:
    """Dashes of DASH px with GAP px between, along a dense path."""
    if len(path) < 2:
        return
    walked = 0.0
    for a, b in pairwise(_dense([*path, path[0]] if closed else path)):
        if walked % (DASH + GAP) < DASH:
            draw.line([a, b], fill=BLACK, width=OUTLINE)
        walked += math.hypot(b[0] - a[0], b[1] - a[1])


def _dense(path: Path, step: float = 2.0) -> Path:
    """The path with a point at least every `step` px."""
    out: Path = path[:1]
    for (x0, y0), (x1, y1) in pairwise(path):
        n = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        out.extend((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(1, n + 1))
    return out


def _rounded(rect: Rect, inset: float = 0) -> Path:
    """The edge of the box's rounded rectangle (inset by `inset` px), clockwise from top-left."""
    x, y, w, h = rect
    left, top, right, bottom = x + inset, y + inset, x + w - 1 - inset, y + h - 1 - inset
    r = max(0.0, corner_radius(rect) - inset)
    centres = ((left + r, top + r, 180), (right - r, top + r, 270), (right - r, bottom - r, 0))
    centres += ((left + r, bottom - r, 90),)
    return [
        (cx + r * math.cos(math.radians(a + d)), cy + r * math.sin(math.radians(a + d)))
        for cx, cy, a in centres
        for d in range(0, 91, 10)
    ]


def _inward(path: Path, depth: Sequence[float]) -> Path:
    """Each point of a clockwise closed path pushed `depth[i]` px toward the inside."""
    out: Path = []
    for i, (px, py) in enumerate(path):
        (ax, ay), (bx, by) = path[i - 1], path[(i + 1) % len(path)]
        tx, ty = bx - ax, by - ay
        length = math.hypot(tx, ty) or 1.0
        out.append((px - ty / length * depth[i], py + tx / length * depth[i]))
    return out


def _burst(rect: Rect) -> Path:
    """A shout (T117): the box's edge, points alternating on it and BURST_DEPTH px inside."""
    x, y, w, h = rect
    corners = [(x, y), (x + w - 1, y), (x + w - 1, y + h - 1), (x, y + h - 1)]
    points: Path = []
    depths: list[float] = []
    for (x0, y0), (x1, y1) in zip(corners, [*corners[1:], corners[0]], strict=True):
        n = 2 * max(1, round(math.hypot(x1 - x0, y1 - y0) / BURST_STEP))
        for k in range(n):
            points.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
            depths.append(0.0 if k % 2 == 0 else BURST_DEPTH)
    return _inward_straight(points, depths, rect)


def _inward_straight(points: Path, depths: Sequence[float], rect: Rect) -> Path:
    """Points on the box's straight edges pushed inward (a corner is never pushed)."""
    x, y, w, h = rect
    out: Path = []
    for (px, py), d in zip(points, depths, strict=True):
        if py == y:
            out.append((px, py + d))
        elif px == x + w - 1:
            out.append((px - d, py))
        elif py == y + h - 1:
            out.append((px, py - d))
        else:
            out.append((px + d, py))
    return out


def _wavy(rect: Rect) -> Path:
    """Distress (T117): the rounded edge pushed in by up to WAVE_DEPTH px along a wave."""
    path = _dense(_rounded(rect) + _rounded(rect)[:1], step=3.0)[:-1]
    walked = [0.0]
    for a, b in pairwise(path):
        walked.append(walked[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    depth = [WAVE_DEPTH * (1 - math.cos(2 * math.pi * s / WAVE_LENGTH)) / 2 for s in walked]
    return _inward(path, depth)


def _angular(rect: Rect) -> Path:
    """Radio (T117): the box with each corner cut CUT px."""
    x, y, w, h = rect
    right, bottom = x + w - 1, y + h - 1
    return [
        (x + CUT, y), (right - CUT, y), (right, y + CUT), (right, bottom - CUT),
        (right - CUT, bottom), (x + CUT, bottom), (x, bottom - CUT), (x, y + CUT),
    ]  # fmt: skip


def _cloud(rect: Rect) -> tuple[list[tuple[float, float, float]], tuple[tuple[int, ...], int]]:
    """A thought (T117): scallops of CLOUD_R px every CLOUD_STEP px along the line CLOUD_R px
    inside the edge, round a core CLOUD_CORE px inside the box."""
    x, y, w, h = rect
    path = _dense(_rounded(rect, CLOUD_R) + _rounded(rect, CLOUD_R)[:1], step=1.0)
    circles: list[tuple[float, float, float]] = []
    walked, last = 0.0, path[0]
    for point in path:
        walked += math.hypot(point[0] - last[0], point[1] - last[1])
        last = point
        if not circles or walked >= CLOUD_STEP:
            circles.append((point[0], point[1], float(CLOUD_R)))
            walked = 0.0
    core = (x + CLOUD_CORE, y + CLOUD_CORE, x + w - 1 - CLOUD_CORE, y + h - 1 - CLOUD_CORE)
    return circles, (core, max(0, corner_radius(rect) - CLOUD_CORE))
