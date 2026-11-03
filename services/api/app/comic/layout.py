"""Page geometry from the shot list. docs/design/comic.md §4 steps 1-5.

Pure: no frame exists yet. Panels are sized by story beat and by how much they must letter,
so each frame can later be rendered at exactly its panel's size and nothing is cropped. Weights
are exact fractions, so a tier whose weights sum to 2.0 closes on 2.0, not on 1.9999999.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from pathlib import Path

from PIL import ImageFont

from app.comic.model import ComicBook, ComicError, LayoutReport, Page, Panel, Rect
from app.script import Dialogue, Scene, Screenplay, absolute_time
from app.shots import Framing, Shot, ShotPlan

PAGE_W, PAGE_H = 1988, 3075  # US comic trim, 6.625 x 10.25 in at 300 dpi
MARGIN, GUTTER = 120, 36
TIERS_PER_PAGE = 3
PANELS_PER_TIER = 3
FULL_TIER = Fraction(2)  # a shot this heavy is solo; a tier this heavy closes
SOLO_HEIGHT = Fraction(5, 4)  # a solo tier is 1.25 normal tiers tall

BASE_WEIGHT: dict[Framing, Fraction] = {
    Framing.WIDE: Fraction(2),
    Framing.MEDIUM: Fraction(1),
    Framing.OVER_SHOULDER: Fraction(1),
    Framing.POV: Fraction(1),
    Framing.CLOSE_UP: Fraction(4, 5),
    Framing.EXTREME_CLOSE_UP: Fraction(3, 5),
    Framing.INSERT: Fraction(3, 5),
}
ESTABLISHING = Fraction(1, 2)  # a scene's first shot
LETTERING_STEP, LETTERING_CHARS = Fraction(1, 4), 60  # per started 60 lettered characters

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "ComicNeue-Regular.ttf"
FONT_PX = 32  # nominal; the renderer may drop to 28 to fit a box, never lower
PADDING = 16  # around a wrapped block, each side
WRAP_SHARE = Fraction(2, 5)  # text wraps to at most 40% of the panel width
BUDGET_SHARE = Fraction(7, 20)  # boxes may cover at most 35% of the panel's area
RAISE = Fraction(1, 2)
MAX_RELAYOUTS = 3


@dataclass(frozen=True)
class _Beat:
    """A shot before it has a rect: what it will letter, and its step-1 weight."""

    shot: Shot
    first: bool
    texts: tuple[str, ...]
    weight: Fraction


type _Tier = tuple[list[int], bool]  # beat indices, solo


def panel_weight(shot: Shot, scene: Scene, first_in_scene: bool, lettered_chars: int) -> float:
    return float(_weight(shot, scene, first_in_scene, lettered_chars))


def scene_caption(scene: Scene) -> str:
    """The `SCENE` caption: heading words only; a borrowed clock (CONTINUOUS) is never lettered."""
    time = absolute_time(scene.time_of_day)
    return scene.location if time is None else f"{scene.location} — {time}"


def layout_geometry(plan: ShotPlan, screenplay: Screenplay) -> ComicBook:
    """Rects for one panel per shot, in plan order. Bubbles and captions are placed later
    (T023), so every panel's are empty and the report counts none yet."""
    font = font_at(FONT_PATH)
    beats = _beats(plan, screenplay)
    weights = [beat.weight for beat in beats]
    forced: set[int] = set()
    relayouts = 0
    while True:
        tiers = _tiers(beats, weights, forced)
        rects = [r for page in _pages(tiers) for r in _page_rects(page, weights)]
        over = [i for i, rect in enumerate(rects) if not _fits(beats[i].texts, rect, font)]
        if not over:
            break
        if relayouts < MAX_RELAYOUTS:
            for i in over:
                weights[i] += RAISE
        else:
            # Past the passes a panel still over budget gets a solo tier; over even there, fail.
            for i in over:
                if i in forced or weights[i] >= FULL_TIER:
                    raise ComicError(
                        f"{shot_name(beats[i].shot)}: its lettering needs more than 35% of the "
                        "panel even in a solo tier",
                        shot=(beats[i].shot.scene_index, beats[i].shot.number),
                    )
            forced.update(over)
        relayouts += 1

    pages: list[Page] = []
    at = 0
    for number, page in enumerate(_pages(tiers), start=1):
        count = sum(len(indices) for indices, _ in page)
        panels = tuple(
            Panel(beats[i].shot.scene_index, beats[i].shot.number, rects[i], (), ())
            for i in range(at, at + count)
        )
        pages.append(Page(number, PAGE_W, PAGE_H, panels))
        at += count
    return ComicBook(tuple(pages), LayoutReport(len(beats), 0, 0, relayouts))


def _weight(shot: Shot, scene: Scene, first_in_scene: bool, lettered_chars: int) -> Fraction:
    if shot.scene_index != scene.index:
        raise ComicError(
            f"{shot_name(shot)} weighed against scene {scene.index}",
            shot=(shot.scene_index, shot.number),
        )
    weight = BASE_WEIGHT[shot.framing] + (ESTABLISHING if first_in_scene else 0)
    return weight + LETTERING_STEP * -(-lettered_chars // LETTERING_CHARS)


def _beats(plan: ShotPlan, screenplay: Screenplay) -> list[_Beat]:
    scenes = {scene.index: scene for scene in screenplay.scenes}
    seen: set[int] = set()
    beats: list[_Beat] = []
    for shot in plan.shots:
        scene = scenes.get(shot.scene_index)
        if scene is None or not all(0 <= i < len(scene.elements) for i in shot.elements):
            raise ComicError(
                f"{shot_name(shot)} cites a scene or element the screenplay lacks",
                shot=(shot.scene_index, shot.number),
            )
        first = shot.scene_index not in seen
        seen.add(shot.scene_index)
        caption = [scene_caption(scene)] if first else []
        spoken = [e.text for i in shot.elements if isinstance(e := scene.elements[i], Dialogue)]
        texts = (*caption, *spoken)
        weight = _weight(shot, scene, first, sum(len(t) for t in texts))
        beats.append(_Beat(shot, first, texts, weight))
    return beats


def _tiers(beats: Sequence[_Beat], weights: Sequence[Fraction], forced: set[int]) -> list[_Tier]:
    tiers: list[_Tier] = []
    open_tier: list[int] | None = None
    for i, beat in enumerate(beats):
        if weights[i] >= FULL_TIER or i in forced:
            tiers.append(([i], True))
            open_tier = None
            continue
        if open_tier is None or beat.first:
            open_tier = []
            tiers.append((open_tier, False))
        open_tier.append(i)
        total = sum((weights[j] for j in open_tier), Fraction(0))
        if len(open_tier) == PANELS_PER_TIER or total >= FULL_TIER:
            open_tier = None
    return tiers


def _pages(tiers: Sequence[_Tier]) -> list[Sequence[_Tier]]:
    return [tiers[k : k + TIERS_PER_PAGE] for k in range(0, len(tiers), TIERS_PER_PAGE)]


def _page_rects(page: Sequence[_Tier], weights: Sequence[Fraction]) -> list[Rect]:
    """Tiers fill the usable height exactly: a normal tier is u tall, a solo one 1.25·u."""
    solo = sum(1 for _, is_solo in page if is_solo)
    usable = PAGE_H - 2 * MARGIN - GUTTER * (len(page) - 1)
    unit = Fraction(usable) / (len(page) - solo + SOLO_HEIGHT * solo)
    heights = [math.floor(unit * SOLO_HEIGHT if is_solo else unit) for _, is_solo in page]
    heights[-1] += usable - sum(heights)
    rects: list[Rect] = []
    y = MARGIN
    for (indices, _), height in zip(page, heights, strict=True):
        rects += _tier_rects(indices, weights, y, height)
        y += height + GUTTER
    return rects


def _tier_rects(indices: Sequence[int], weights: Sequence[Fraction], y: int, h: int) -> list[Rect]:
    """Widths proportional to weights, rounded down, the remainder to the last panel."""
    usable = PAGE_W - 2 * MARGIN - GUTTER * (len(indices) - 1)
    total = sum((weights[i] for i in indices), Fraction(0))
    widths = [math.floor(usable * weights[i] / total) for i in indices]
    widths[-1] += usable - sum(widths)
    rects: list[Rect] = []
    x = MARGIN
    for width in widths:
        rects.append((x, y, width, h))
        x += width + GUTTER
    return rects


def _fits(texts: Sequence[str], rect: Rect, font: ImageFont.FreeTypeFont) -> bool:
    _, _, w, h = rect
    limit = math.floor(w * WRAP_SHARE)
    area = sum(bw * bh for bw, bh in (box_size(text, limit, font) for text in texts))
    return area <= BUDGET_SHARE * w * h


def box_size(text: str, limit: int, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """The wrapped block at the font's size, plus padding: the rect a bubble or caption fills."""
    lines = wrap(text, limit, font)
    ascent, descent = font.getmetrics()
    width = max(math.ceil(font.getlength(line)) for line in lines)
    return width + 2 * PADDING, len(lines) * (ascent + descent) + 2 * PADDING


def wrap(text: str, limit: int, font: ImageFont.FreeTypeFont) -> list[str]:
    """Greedy on whitespace. A word wider than the limit keeps a line to itself: text is
    never split mid-word, cut or reworded, so such a box is simply wider."""
    lines: list[str] = []
    for word in text.split():
        joined = f"{lines[-1]} {word}" if lines else word
        if lines and font.getlength(joined) <= limit:
            lines[-1] = joined
        else:
            lines.append(word)
    return lines or [""]


@cache
def font_at(path: Path, size: int = FONT_PX) -> ImageFont.FreeTypeFont:
    if not path.is_file():
        raise ComicError(f"lettering font missing: {path}; there is no fallback font")
    # Basic, not raqm: Pillow uses raqm only where libfribidi is installed (a CI runner, not the
    # API image or Windows), and its kerning would size every box differently per host.
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def shot_name(shot: Shot) -> str:
    return f"scene {shot.scene_index}, shot {shot.number}"
