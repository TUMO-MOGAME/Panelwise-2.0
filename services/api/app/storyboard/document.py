"""The storyboard PDF (storyboard.md §3.4, §6 `document.py`; T027). Built after the job, from the
project's `frames` rows: a block per shot in plan order, each the audited frame (or the withheld or
failed card) above the shot's verbatim source and its page/line span. Courier Prime, A4 at
150 dpi, one Pillow image per page, one PDF.

Nothing here invents text: titles, spans and sources are the plan's and the script's own, and a
frame that wasn't accepted is never drawn from its pixels (its bytes are not even read).
"""

import asyncio
import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.comic.layout import wrap
from app.frames.model import FrameAuditRow, FrameRow
from app.script import Dialogue, Scene, Screenplay, Span
from app.shots import Shot, ShotPlan
from app.storage import AssetStore
from app.storyboard.model import Block, Rect, SourceLine, StoryboardFrame, StoryboardPage
from app.storyboard.prompt import heading_span
from app.storyboard.styles import Style
from app.verify.model import Check, FrameState, Severity, Verdict

DOCUMENT_VERSION = 3  # bump whenever the layout or the drawing changes (§3.4 Document key); 3: T103

PAGE_W, PAGE_H = 1240, 1754  # A4 portrait at 150 dpi
DPI = 150
MARGIN = 90
CONTENT_W = PAGE_W - 2 * MARGIN  # 1060
FRAME_W, FRAME_H = 880, 495  # 16:9, 1280 x 720 scaled: two short blocks share a page
FRAME_X = MARGIN + (CONTENT_W - FRAME_W) // 2  # centred
GAP = 40  # between blocks
CARD_TEXT_W = FRAME_W - 80  # 40 px clear inside the 880 px box on each side
CARD_PITCH = 34
FOOTER_NOTE = "A vision model describes each frame; Nemotron audits it against the script."
FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"

ACCEPTED = (FrameState.PASSED, FrameState.WARNED)
_CHECK_ORDER = {check: i for i, check in enumerate(Check)}
_FAILURES = {"render": "the renderer failed", "restart": "the job was interrupted"}


@cache
def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS / ("CourierPrime-Bold.ttf" if bold else "CourierPrime-Regular.ttf")
    if not path.is_file():
        raise FileNotFoundError(f"the document font is missing: {path}; there is no fallback font")
    # Basic, not raqm, as the comic's lettering: the same measurements on every host.
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


# --- from the rows ---------------------------------------------------------------------------


def frames_from_rows(
    rows: Sequence[FrameRow], audits: Sequence[FrameAuditRow]
) -> tuple[StoryboardFrame, ...]:
    """§3.4 From the rows: each row with its own attempt's audit (the project's storyboard-target
    audits, any order). Pure."""
    at = {(a.scene_index, a.shot_number, a.attempt): a for a in audits}
    out: list[StoryboardFrame] = []
    for row in rows:
        shot = (row.scene_index, row.shot_number)
        state = FrameState(row.state)
        audit = at.get((*shot, row.attempt))
        out.append(
            StoryboardFrame(
                shot=shot,
                state=state,
                asset=row.asset if state in ACCEPTED else None,
                prompt=None,  # rows don't keep the text sent
                seed=None if audit is None else audit.seed,
                attempts=row.attempt,
                verdict=Verdict.ERROR if audit is None else Verdict(audit.verdict),
                noted_checks=_noted(state, audit),
                failure=row.failure,
            )
        )
    return tuple(out)


def _noted(state: FrameState, audit: FrameAuditRow | None) -> tuple[Check, ...]:
    """As `frame_of` picks them: hard failures for WITHHELD, soft for WARNED, in enum order."""
    if audit is None or state not in (FrameState.WITHHELD, FrameState.WARNED):
        return ()
    # A warned frame names every check it failed: with AUDIT_WITHHOLDS off, hard ones too.
    wanted = {Severity.HARD.value} if state is FrameState.WITHHELD else {s.value for s in Severity}
    failed = {
        Check(c["check"])
        for c in audit.checks
        if c.get("severity") in wanted and c.get("ok") is False
    }
    return tuple(sorted(failed, key=_CHECK_ORDER.__getitem__))


# --- the key ---------------------------------------------------------------------------------


def document_key(project_id: uuid.UUID, style: Style, frames: Sequence[StoryboardFrame]) -> str:
    """§3.4 Document key: every input that changes the pages, so a second Export is a store hit."""
    listed = sorted(
        (
            [
                f.shot[0],
                f.shot[1],
                f.state.value,
                f.asset,
                f.verdict.value,
                [c.value for c in f.noted_checks],
                f.failure,
            ]
            for f in frames
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    body: dict[str, Any] = {
        "version": DOCUMENT_VERSION,
        "project": str(project_id),
        "style": [style.key, style.label],  # the footer prints the label
        "frames": listed,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- layout ----------------------------------------------------------------------------------


def layout_document(
    frames: Sequence[StoryboardFrame], plan: ShotPlan, screenplay: Screenplay, style: Style
) -> tuple[StoryboardPage, ...]:
    """§3.4: scenes start pages; a block goes on the current page if it fits between the header
    and the footer, else on a new one; a block taller than an empty page continues. Pure."""
    by_shot = {f.shot: f for f in frames}
    bottom = _content_bottom(style)
    pages: list[tuple[int, list[Block]]] = []
    cursor = 0

    def open_page(scene_index: int) -> None:
        nonlocal cursor
        pages.append((scene_index, []))
        cursor = _content_top(screenplay, scene_index)

    for shot in plan.shots:
        key = (shot.scene_index, shot.number)
        number = screenplay.scenes[shot.scene_index].number
        found = by_shot.get(key)
        if found is None:
            raise ValueError(f"shot {number}.{shot.number} has no frame to lay out")
        span = shot.span
        block = Block(
            shot=key,
            y=0,
            frame_rect=(FRAME_X, 0, FRAME_W, FRAME_H),
            title=f"{number}.{shot.number}  {_camera(shot)}",
            span_label=span_text(span),
            audit_line=_audit_line(found),
            source_lines=_source_lines(shot, screenplay.scenes[shot.scene_index]),
            continued=False,
        )
        if not pages or pages[-1][0] != shot.scene_index:
            open_page(shot.scene_index)
        while True:
            fixed = _height(replace(block, source_lines=()))
            room = max(0, (bottom - cursor - fixed) // 30)
            if room >= len(block.source_lines):
                pages[-1][1].append(_at(block, cursor))
                cursor += _height(block) + GAP
                break
            if pages[-1][1]:  # it doesn't fit here: an empty page first
                open_page(shot.scene_index)
                continue
            # Taller than an empty page: as many lines as fit, the rest continued on the next.
            # T103: never ending on a speaker run unless that is all that fits; a speech continued
            # on the next page gets its speaker again, unless this page held speaker lines alone
            # (repeating them then could lay out the same page forever).
            cut = _cut(block.source_lines, max(1, room))
            placed, rest = block.source_lines[:cut], block.source_lines[cut:]
            if not rest:  # every line fits at the cut (room 0 under a page-tall heading): done
                pages[-1][1].append(_at(block, cursor))
                cursor += _height(block) + GAP
                break
            spoken = any(not line.speaker for line in placed)
            if spoken and not rest[0].speaker and rest[0].of is not None:
                rest = (*_speaker_run(rest[0].of), *rest)
            pages[-1][1].append(_at(replace(block, source_lines=placed), cursor))
            block = replace(
                block,
                frame_rect=None,
                title=f"{number}.{shot.number} (cont.)",
                audit_line=None,
                source_lines=rest,
                continued=True,
            )
            open_page(shot.scene_index)
    return tuple(
        StoryboardPage(number=i + 1, scene_index=scene, blocks=tuple(placed))
        for i, (scene, placed) in enumerate(pages)
    )


def _at(block: Block, y: int) -> Block:
    rect: Rect | None = None if block.frame_rect is None else (FRAME_X, y, FRAME_W, FRAME_H)
    return replace(block, y=y, frame_rect=rect)


def _camera(shot: Shot) -> str:
    """`CLOSE UP / STATIC`: the enum values upper-cased, `_` as a space."""
    return f"{shot.framing.value} / {shot.movement.value}".upper().replace("_", " ")


def _audit_line(frame: StoryboardFrame) -> str | None:
    if frame.state is FrameState.PASSED:
        return "Audit: pass"
    if frame.state is FrameState.WARNED:
        noted = _names(frame.noted_checks)
        return f"Audit: warn ({noted})" if noted else "Audit: warn"
    return None  # a withheld or failed frame's card says it


def _names(checks: Sequence[Check]) -> str:
    return ", ".join(c.value.replace("_", " ") for c in checks)


def _source_lines(shot: Shot, scene: Scene) -> tuple[SourceLine, ...]:
    """The shot's source, each element's lines wrapped on their own, so element breaks are kept;
    never cut or folded. T103: from the covered elements, a speech under its speaker's label when
    the label differs from the previous element's (the web's rule); `source`'s own lines, with no
    speaker, for a heading-only shot or elements that no longer join to `source`."""
    covered = [scene.elements[i] for i in shot.elements if 0 <= i < len(scene.elements)]
    if (
        len(covered) != len(shot.elements)
        or not covered
        or ("\n".join(e.text for e in covered) != shot.source)
    ):
        return tuple(SourceLine(line) for line in _wrapped(shot.source))
    lines: list[SourceLine] = []
    last: str | None = None
    for element in covered:
        label = _label(element) if isinstance(element, Dialogue) and element.cue else None
        if label is not None and label != last:
            lines += _speaker_run(label)
        last = label
        lines += [SourceLine(line, of=label) for line in _wrapped(element.text)]
    return tuple(lines)


def _wrapped(text: str) -> list[str]:
    """Each of the text's lines wrapped to the content width on its own (Regular 22 px)."""
    font = _font(False, 22)
    return [line for part in text.split("\n") for line in wrap(part, CONTENT_W, font)]


def _label(dialogue: Dialogue) -> str:
    """`CUE`, or `CUE (EXT)`: exactly the web's speaker label (sheet.ts `sourceBlocks`)."""
    return f"{dialogue.cue} ({dialogue.extension})" if dialogue.extension else dialogue.cue


def _speaker_run(label: str) -> tuple[SourceLine, ...]:
    """The label wrapped in the Bold font it is drawn in: one speaker line, or a run of them."""
    return tuple(SourceLine(line, speaker=True) for line in wrap(label, CONTENT_W, _font(True, 22)))


def _cut(lines: Sequence[SourceLine], room: int) -> int:
    """How many lines go on this page (T103): `room`, less a speaker run they would end on, unless
    that run is all that fits."""
    cut = room
    while cut > 0 and lines[cut - 1].speaker:
        cut -= 1
    return cut or room


def _heading_lines(screenplay: Screenplay, scene_index: int) -> list[str]:
    """The scene's heading as printed in the script: its line of `Screenplay.text`, numbered as
    every span is, by `split("\n")` (`splitlines` also breaks on a form feed or U+2028)."""
    line = heading_span(screenplay.scenes[scene_index]).line_start
    printed = screenplay.text.split("\n")[line - 1].strip()
    return wrap(printed, CONTENT_W, _font(True, 26))


def _content_top(screenplay: Screenplay, scene_index: int) -> int:
    """Below the header: STORYBOARD 22, 8, the heading at 34 a line, 12, a 2 px rule, 24."""
    return MARGIN + 22 + 8 + 34 * len(_heading_lines(screenplay, scene_index)) + 38


def _footer_lines(style: Style, page: int) -> list[str]:
    text = f"Panelwise · {style.label} · page {page} · {FOOTER_NOTE}"
    return wrap(text, CONTENT_W, _font(False, 18))


def _content_bottom(style: Style) -> int:
    """Above the footer, reserved for a page number of up to three digits: a 1 px rule, 8, then
    24 a line."""
    return PAGE_H - MARGIN - (1 + 8 + 24 * len(_footer_lines(style, 999)))


def _height(block: Block) -> int:
    """Frame 495 and 12, title 34, audit 30 when present, 8, then 30 a source line."""
    height = 0 if block.frame_rect is None else FRAME_H + 12
    height += 34 + (30 if block.audit_line is not None else 0) + 8
    return height + 30 * len(block.source_lines)


def span_text(span: Span) -> str:
    """`p.2 l.97` for one line, `p.2 l.97\u201399` (an en dash) for more: as the web's SpanRef."""
    if span.line_end > span.line_start:
        return f"p.{span.page} l.{span.line_start}\u2013{span.line_end}"
    return f"p.{span.page} l.{span.line_start}"


def _card_lines(frame: StoryboardFrame, shot: Shot) -> tuple[str, str]:
    """The withheld card (verify.md §4) or the failed card (§3.4), and where the shot is."""
    span = shot.span
    where = f"Script {span_text(span)}"
    if frame.state is FrameState.FAILED:
        reason = _FAILURES.get(frame.failure or "")
        return (f"Frame not drawn: {reason}" if reason else "Frame not drawn"), where
    if frame.verdict is Verdict.ERROR:
        return "Frame withheld: failed audit (audit error)", where
    if frame.noted_checks:
        return f"Frame withheld: failed audit ({_names(frame.noted_checks)})", where
    # Never an empty "()", and never a failed export over a card's wording.
    return "Frame withheld: failed audit", where


# --- the PDF ---------------------------------------------------------------------------------


def render_pdf(
    pages: Sequence[StoryboardPage],
    frames: Sequence[StoryboardFrame],
    plan: ShotPlan,
    screenplay: Screenplay,
    style: Style,
    images: Mapping[tuple[int, int], bytes],
) -> bytes:
    """One page image per `StoryboardPage`, one PDF. `images` are the accepted frames' PNGs; no
    other frame's bytes are read."""
    if not pages:
        raise ValueError("a storyboard PDF needs at least one page")
    by_shot = {f.shot: f for f in frames}
    shots = {(s.scene_index, s.number): s for s in plan.shots}
    drawn = [_page(page, by_shot, shots, screenplay, style, images) for page in pages]
    buffer = BytesIO()
    drawn[0].save(buffer, "PDF", save_all=True, append_images=drawn[1:], resolution=DPI)
    return buffer.getvalue()


def _page(
    page: StoryboardPage,
    frames: Mapping[tuple[int, int], StoryboardFrame],
    shots: Mapping[tuple[int, int], Shot],
    screenplay: Screenplay,
    style: Style,
    images: Mapping[tuple[int, int], bytes],
) -> Image.Image:
    canvas = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(canvas)
    y = MARGIN
    draw.text((MARGIN, y), "STORYBOARD", font=_font(True, 22), fill="black")
    y += 22 + 8
    for line in _heading_lines(screenplay, page.scene_index):
        draw.text((MARGIN, y), line, font=_font(True, 26), fill="black")
        y += 34
    y += 12
    draw.rectangle((MARGIN, y, MARGIN + CONTENT_W - 1, y + 1), fill="black")

    footer = _footer_lines(style, page.number)
    top = PAGE_H - MARGIN - 24 * len(footer)
    draw.rectangle((MARGIN, top - 9, MARGIN + CONTENT_W - 1, top - 9), fill="black")
    for i, line in enumerate(footer):
        draw.text((MARGIN, top + 24 * i), line, font=_font(False, 18), fill="black")

    for block in page.blocks:
        _block(canvas, draw, block, frames[block.shot], shots[block.shot], images)
    return canvas


def _block(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    block: Block,
    frame: StoryboardFrame,
    shot: Shot,
    images: Mapping[tuple[int, int], bytes],
) -> None:
    y = block.y
    if block.frame_rect is not None:
        x, top, w, h = block.frame_rect
        if frame.state in ACCEPTED:
            with Image.open(BytesIO(images[block.shot])) as picture:
                rgb: Image.Image = picture.convert("RGB")
            # Pillow's stubs leave resize's size type partly unknown (as workflow.py's fit).
            fitted: Image.Image = rgb.resize((w, h), resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
            canvas.paste(fitted, (x, top))
        else:
            _card(draw, block.frame_rect, _card_lines(frame, shot))
        y += FRAME_H + 12
    draw.text((MARGIN, y), block.title, font=_font(True, 24), fill="black")
    label = _font(False, 20)
    width = label.getlength(block.span_label)
    draw.text((MARGIN + CONTENT_W - width, y + 3), block.span_label, font=label, fill="black")
    y += 34
    if block.audit_line is not None:
        draw.text((MARGIN, y), block.audit_line, font=label, fill="black")
        y += 30
    y += 8
    for line in block.source_lines:
        draw.text((MARGIN, y), line.text, font=_font(line.speaker, 22), fill="black")
        y += 30


def _card(draw: ImageDraw.ImageDraw, rect: Rect, lines: tuple[str, str]) -> None:
    """White, a 4 px grey border, the lines centred in Regular 26 px wrapped to 800 px."""
    x, y, w, h = rect
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill="white", outline="#808080", width=4)
    font = _font(False, 26)
    wrapped = [part for line in lines for part in wrap(line, CARD_TEXT_W, font)]
    top = y + (h - CARD_PITCH * len(wrapped)) // 2
    for i, line in enumerate(wrapped):
        left = x + (w - round(font.getlength(line))) // 2
        draw.text((left, top + CARD_PITCH * i), line, font=font, fill="black")


# --- export ----------------------------------------------------------------------------------


async def export_pdf(
    store: AssetStore,
    project_id: uuid.UUID,
    style: Style,
    plan: ShotPlan,
    screenplay: Screenplay,
    frames: Sequence[StoryboardFrame],
) -> str:
    """The store path of the project's PDF (§3.4 Delivery): a hit on its document key, else the
    accepted frames read from the store, drawn in a thread and stored. StorageError propagates."""
    path = f"storyboards/{document_key(project_id, style, frames)}.pdf"
    if await store.exists(path):
        return path
    images = {
        f.shot: await store.get(f.asset)
        for f in frames
        if f.state in ACCEPTED and f.asset is not None
    }
    pages = layout_document(frames, plan, screenplay, style)
    data = await asyncio.to_thread(render_pdf, pages, frames, plan, screenplay, style, images)
    await store.put(path, data, "application/pdf")
    return path
