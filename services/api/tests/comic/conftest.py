"""Frames for the comic tests, drawn with Pillow.

Real frames come from the renderer (T026, on the GPU). `place_lettering` and `render_pages` take
a `PanelFrame`'s PNG bytes, so these tests draw frames at that seam: flat regions (no detail) and
busy ones (a fine checkerboard, all edges), to prove where the lettering goes.
"""

from collections.abc import Callable, Mapping
from io import BytesIO

from PIL import Image, ImageDraw

from app.comic import ComicBook, PanelFrame, Rect
from app.verify import Position

type Key = tuple[int, int]
type Draw = Callable[[Rect], bytes]

FLAT = (226, 232, 238)
INK = (20, 20, 20)


def png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def solid(rect: Rect, colour: tuple[int, int, int] = FLAT) -> bytes:
    return png(Image.new("RGB", (rect[2], rect[3]), colour))


def busy(rect: Rect, region: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    """A flat frame with a 6 px checkerboard over `region(w, h)` (x0, y0, x1, y1)."""
    _, _, w, h = rect
    image = Image.new("RGB", (w, h), FLAT)
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = region(w, h)
    for y in range(y0, y1, 6):
        for x in range(x0 + (y // 6 % 2) * 6, x1, 12):
            draw.rectangle((x, y, min(x + 5, x1 - 1), min(y + 5, y1 - 1)), fill=INK)
    return png(image)


def busy_left(rect: Rect) -> bytes:
    return busy(rect, lambda w, h: (0, 0, w // 2, h))


def busy_top(rect: Rect) -> bytes:
    return busy(rect, lambda w, h: (0, 0, w, h // 2))


def frames(
    book: ComicBook,
    draw: Draw = solid,
    positions: Mapping[Key, Mapping[str, Position]] | None = None,
) -> dict[Key, PanelFrame]:
    """An accepted frame for every panel, drawn at exactly its rect's size."""
    out: dict[Key, PanelFrame] = {}
    for page in book.pages:
        for panel in page.panels:
            key = (panel.scene_index, panel.shot_number)
            out[key] = PanelFrame(draw(panel.rect), dict((positions or {}).get(key, {})), False)
    return out
