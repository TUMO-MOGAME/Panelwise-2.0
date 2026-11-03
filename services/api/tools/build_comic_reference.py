"""Render the comic reference pages in docs/design/comic/ (comic.md §2, T023).

    cd services/api && uv run python -m tools.build_comic_reference

The script is the self-written sample `samples/the-red-kite.pdf`, read by the real parser. The
shot list is planned by hand here (every element in exactly one shot), so the reference doesn't
move when a model does. The frames are **test fixtures**, drawn with Pillow and each marked
`TEST FIXTURE - not a render`: real frames come from the renderer (T026, on a GPU). Hatched
shapes stand where the audit placed each speaker, and hatching fills the ground, so the
reference shows lettering keeping to the empty sky and off the speakers. One frame is withheld,
to show the card. Everything else is the real code: `layout_geometry`, `panel_frame` (from
verify's `FrameOutcome`), `place_lettering`, `render_pages`.

The gate's `tests/comic/test_reference.py` re-renders these pages and compares pixels.
"""

import sys
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from app.comic import ComicBook, PanelFrame, layout_geometry, panel_frame, place_lettering
from app.comic.layout import FONT_PATH, font_at
from app.comic.render import render_pages
from app.llm import Usage
from app.script import Dialogue, Screenplay, Span, parse_pdf
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from app.verify import (
    Audit,
    Check,
    CheckResult,
    FrameOutcome,
    FrameState,
    Position,
    RenderedFrame,
    Severity,
    Verdict,
)
from tools.build_samples import SAMPLES

REFERENCE = Path(__file__).resolve().parents[3] / "docs" / "design" / "comic"
SAMPLE = "the-red-kite"
MARK = "TEST FIXTURE - not a render"

L, C, R = Position.LEFT, Position.CENTRE, Position.RIGHT
W, M, CU, OS, INS = (
    Framing.WIDE,
    Framing.MEDIUM,
    Framing.CLOSE_UP,
    Framing.OVER_SHOULDER,
    Framing.INSERT,
)

# (scene, framing, elements, who the fixture frame shows where). Every element of every scene
# is in exactly one shot, in order. MOKGOSI (O.S.) and the RADIO ANNOUNCER (V.O.) are heard, not
# seen, so they have no position.
PLAN: Sequence[tuple[int, Framing, tuple[int, ...], Mapping[str, Position]]] = [
    (0, W, (0, 1), {"LERATO": C}),
    (0, M, (2, 3, 4), {"LERATO": L}),
    (0, CU, (5, 6), {"LERATO": R}),
    (1, W, (0, 1), {"MOKGOSI": R}),
    (1, M, (2, 3, 4), {"LERATO": L, "MOKGOSI": R}),
    (1, INS, (5, 6), {"MOKGOSI": C}),
    (1, OS, (7, 8), {"LERATO": R, "MOKGOSI": L}),
    (1, CU, (9, 10), {}),
    (1, M, (11, 12), {"LERATO": L, "MOKGOSI": R}),
    (2, W, (0, 1), {"LERATO": C}),
    (2, M, (2,), {"LERATO": L}),
    (2, INS, (3, 4), {}),
    (2, W, (5, 6), {"LERATO": R}),
    (3, W, (0, 1), {"LERATO": L}),
    (3, CU, (2, 3, 4), {"LERATO": C}),
    (3, M, (5, 6, 7), {"LERATO": L, "MOKGOSI": R}),
    (3, INS, (8,), {}),
    (4, W, (0, 1), {"LERATO": L, "MOKGOSI": R}),
    (4, M, (2, 3, 4), {"LERATO": R, "MOKGOSI": L}),
    (4, CU, (5, 6), {"MOKGOSI": C}),
]
WITHHELD = (3, 3)  # its fixture audit found an unscripted person; the page shows the card

DAY_SKY, NIGHT_SKY = (214, 226, 236), (58, 66, 96)
HATCH = (40, 40, 48)
BAND = (24, 24, 28)


def plan_for(screenplay: Screenplay) -> ShotPlan:
    scenes = {scene.index: scene for scene in screenplay.scenes}
    numbers: dict[int, int] = {}
    shots: list[Shot] = []
    for scene_index, framing, elements, positions in PLAN:
        scene = scenes[scene_index]
        number = numbers[scene_index] = numbers.get(scene_index, 0) + 1
        cited = [scene.elements[i] for i in elements]
        span = Span(cited[0].span.page, cited[0].span.line_start, cited[-1].span.line_end)
        speakers = {e.cue for e in cited if isinstance(e, Dialogue)}
        characters = tuple(sorted(set(positions) | speakers))
        source = "\n\n".join(e.text for e in cited)
        shots.append(
            Shot(
                scene_index,
                number,
                framing,
                Movement.STATIC,
                elements,
                characters,
                (),
                scene.time_of_day,
                "hand-planned for the comic reference",
                span,
                source,
            )
        )
    report = PlanReport(len(scenes), len(shots), 0, 0, 0)
    return ShotPlan(tuple(shots), report, (), Usage(0, 0, 0))


def fixture_frame(
    shot: Shot, width: int, height: int, positions: Mapping[str, Position], night: bool
) -> bytes:
    """A flat sky, hatched ground and hatched figures where `positions` puts them, and the mark."""
    image = Image.new("RGB", (width, height), NIGHT_SKY if night else DAY_SKY)
    draw = ImageDraw.Draw(image)
    ground = height * 3 // 4
    _hatch(image, (0, ground, width, height))
    label = font_at(FONT_PATH, 28)
    for name, position in sorted(positions.items()):
        third = {Position.LEFT: 0, Position.CENTRE: 1, Position.RIGHT: 2}[position]
        cx = width * (2 * third + 1) // 6
        fw = max(width // 8, 60)
        top = height * 2 // 5
        _hatch(image, (cx - fw // 2, top, cx + fw // 2, ground))
        draw.ellipse((cx - fw // 3, top - fw * 2 // 3, cx + fw // 3, top), fill=HATCH)
        draw.text((cx, ground - 8), name, font=label, fill=(255, 255, 255), anchor="md")
    band = 44
    draw.rectangle((0, height - band, width, height), fill=BAND)
    text = f"{MARK} · scene {shot.scene_index} shot {shot.number} · {shot.framing.value}"
    draw.text((12, height - band // 2), text, font=label, fill=(255, 255, 255), anchor="lm")
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _hatch(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Diagonal hatching clipped to the box: all edges, so lettering keeps off it."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    tile = Image.new("RGB", (w, h), (236, 236, 240))
    lines = ImageDraw.Draw(tile)
    for x in range(-h, w, 9):
        lines.line((x, h, x + h, 0), fill=HATCH, width=3)
    lines.rectangle((0, 0, w - 1, h - 1), outline=HATCH, width=3)
    image.paste(tile, (x0, y0))


def _outcome(
    shot: Shot, png: bytes, width: int, height: int, positions: Mapping[str, Position]
) -> FrameOutcome:
    key = (shot.scene_index, shot.number)
    frame = RenderedFrame(key, 1, 0, png, width, height, "")
    if key == WITHHELD:
        failed = (CheckResult(Check.UNSCRIPTED_PERSON, Severity.HARD, False, "fixture"),)
        audits = tuple(
            Audit(key, n, 0, None, None, failed, Verdict.FAIL, dict(positions), (), Usage(0, 0, 0))
            for n in (1, 2, 3)
        )
        return FrameOutcome(key, FrameState.WITHHELD, frame, audits)
    audit = Audit(key, 1, 0, None, None, (), Verdict.PASS, dict(positions), (), Usage(0, 0, 0))
    return FrameOutcome(key, FrameState.PASSED, frame, (audit,))


def build() -> tuple[ComicBook, list[bytes]]:
    screenplay = parse_pdf((SAMPLES / f"{SAMPLE}.pdf").read_bytes())
    plan = plan_for(screenplay)
    book = layout_geometry(plan, screenplay)
    scenes = {scene.index: scene for scene in screenplay.scenes}
    placed_positions = {
        (shot.scene_index, shot.number): positions
        for shot, (_, _, _, positions) in zip(plan.shots, PLAN, strict=True)
    }
    shots = {(shot.scene_index, shot.number): shot for shot in plan.shots}
    frames: dict[tuple[int, int], PanelFrame] = {}
    for page in book.pages:
        for panel in page.panels:
            key = (panel.scene_index, panel.shot_number)
            shot, positions = shots[key], placed_positions[key]
            _, _, w, h = panel.rect
            night = scenes[shot.scene_index].time_of_day == "NIGHT"
            png = fixture_frame(shot, w, h, positions, night)
            frames[key] = panel_frame(_outcome(shot, png, w, h, positions), shot)
    lettered = place_lettering(book, screenplay, plan, frames)
    return lettered, render_pages(lettered, frames)


def page_path(number: int) -> Path:
    return REFERENCE / f"{SAMPLE}-page-{number}.png"


def main() -> int:
    book, pages = build()
    REFERENCE.mkdir(parents=True, exist_ok=True)
    for stale in REFERENCE.glob(f"{SAMPLE}-page-*.png"):
        stale.unlink()
    for number, data in enumerate(pages, start=1):
        page_path(number).write_bytes(data)
    report = book.report
    print(
        f"{len(pages)} pages, {report.panels} panels, {report.bubbles} bubbles, "
        f"{report.captions} captions, {report.relayouts} relayouts -> {REFERENCE}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
