"""The storyboard PDF (T027): storyboard.md §3.4, §6 `document.py`, §9 Document. Generated PNGs,
an in-memory store; no network, no database."""

import re
import uuid
from dataclasses import replace
from io import BytesIO
from itertools import pairwise
from typing import Any

import pytest
from PIL import Image

from app.frames.model import FrameAuditRow, FrameRow
from app.script import Screenplay, Span, parse_text
from app.shots import Framing, Movement, Shot, ShotPlan
from app.storyboard import document
from app.storyboard.document import (
    CARD_TEXT_W,
    DOCUMENT_VERSION,
    FRAME_W,
    PAGE_H,
    document_key,
    export_pdf,
    frames_from_rows,
    layout_document,
    render_pdf,
    span_text,
)
from app.storyboard.model import Block, StoryboardFrame
from app.verify.model import Check, FrameState, Verdict
from tests.comic.test_layout import plan_of
from tests.fakes import MemoryStore
from tests.script.conftest import two_page_text
from tests.storyboard.conftest import STYLE, shot_of

PID = uuid.UUID("00000000-0000-0000-0000-000000000027")
block_height = document._height  # pyright: ignore[reportPrivateUsage]
content_top = document._content_top  # pyright: ignore[reportPrivateUsage]
content_bottom = document._content_bottom  # pyright: ignore[reportPrivateUsage]
card_lines = document._card_lines  # pyright: ignore[reportPrivateUsage]
content_heading = document._heading_lines  # pyright: ignore[reportPrivateUsage]


def screenplay() -> Screenplay:
    return parse_text(*two_page_text())


def plan(sp: Screenplay) -> ShotPlan:
    return plan_of(
        shot_of(sp, 0, [0, 1], number=1, framing=Framing.WIDE),
        shot_of(sp, 0, [2, 3], number=2, framing=Framing.CLOSE_UP, movement=Movement.PAN),
        shot_of(sp, 1, [0], number=1),
        shot_of(sp, 1, [1, 2, 3], number=2, framing=Framing.OVER_SHOULDER),
        shot_of(sp, 2, [0], number=1, framing=Framing.INSERT),
    )


def frame(shot: Shot, state: FrameState = FrameState.PASSED, **kw: Any) -> StoryboardFrame:
    accepted = state in (FrameState.PASSED, FrameState.WARNED)
    return StoryboardFrame(
        shot=(shot.scene_index, shot.number),
        state=state,
        asset=kw.get("asset", f"frames/{shot.scene_index}-{shot.number}.png" if accepted else None),
        prompt=None,
        seed=kw.get("seed", 7),
        attempts=kw.get("attempts", 1),
        verdict=kw.get("verdict", Verdict.PASS),
        noted_checks=tuple(kw.get("noted", ())),
        failure=kw.get("failure"),
    )


def png(colour: tuple[int, int, int] = (90, 90, 90)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (1280, 720), colour).save(buffer, "PNG")
    return buffer.getvalue()


def mixed(p: ShotPlan) -> list[StoryboardFrame]:
    """A pass, a warn, a withheld, an audit error and a failed render, in plan order."""
    a, b, c, d, e = p.shots
    return [
        frame(a),
        frame(b, FrameState.WARNED, verdict=Verdict.WARN, noted=[Check.LIGHT, Check.FRAMING]),
        frame(c, FrameState.WITHHELD, verdict=Verdict.FAIL, noted=[Check.UNSCRIPTED_PERSON]),
        frame(d, FrameState.WITHHELD, verdict=Verdict.ERROR),
        frame(e, FrameState.FAILED, verdict=Verdict.ERROR, failure="render", seed=None),
    ]


def blocks(pages: Any) -> list[Block]:
    return [b for page in pages for b in page.blocks]


# ------------------------------------------------------------------- from the rows


def row(shot: tuple[int, int], state: str, attempt: int, **kw: Any) -> FrameRow:
    return FrameRow(
        project_id=PID,
        scene_index=shot[0],
        shot_number=shot[1],
        state=state,
        attempt=attempt,
        asset=kw.get("asset"),
        withheld_check=kw.get("withheld_check"),
        failure=kw.get("failure"),
    )


def audit_row(
    shot: tuple[int, int], attempt: int, verdict: str, checks: list[Any]
) -> FrameAuditRow:
    return FrameAuditRow(
        project_id=PID,
        scene_index=shot[0],
        shot_number=shot[1],
        attempt=attempt,
        seed=1000 + attempt,
        frame_asset=f"frames/{shot}-{attempt}.png",
        checks=checks,
        verdict=verdict,
        target="storyboard",
    )


def check(name: str, severity: str, ok: bool) -> dict[str, Any]:
    return {"check": name, "severity": severity, "ok": ok, "detail": ""}


def test_each_row_reads_its_own_attempts_audit_and_its_checks_in_enum_order() -> None:
    rows = [
        row((0, 1), "passed", 2, asset="frames/a.png"),
        row((0, 2), "warned", 1, asset="frames/b.png"),
        row((1, 1), "withheld", 3, withheld_check="unscripted_person"),
        row((1, 2), "failed", 2, failure="render"),
    ]
    audits = [
        audit_row((0, 1), 1, "fail", [check("text_in_frame", "hard", False)]),
        audit_row((0, 1), 2, "pass", [check("text_in_frame", "hard", True)]),
        audit_row(
            (0, 2), 1, "warn", [check("framing", "soft", False), check("light", "soft", False)]
        ),
        audit_row(
            (1, 1),
            3,
            "fail",
            [
                check("text_in_frame", "hard", False),
                check("unscripted_person", "hard", False),
                check("light", "soft", False),  # soft: never named on a withheld card
            ],
        ),
        audit_row((1, 2), 1, "fail", [check("setting", "hard", False)]),  # not attempt 2's
    ]
    got = {f.shot: f for f in frames_from_rows(rows, list(reversed(audits)))}

    assert (got[(0, 1)].verdict, got[(0, 1)].seed, got[(0, 1)].attempts) == (Verdict.PASS, 1002, 2)
    assert got[(0, 1)].asset == "frames/a.png" and got[(0, 1)].noted_checks == ()
    assert got[(0, 2)].noted_checks == (Check.LIGHT, Check.FRAMING)  # enum order, not the audit's
    assert got[(1, 1)].noted_checks == (Check.UNSCRIPTED_PERSON, Check.TEXT_IN_FRAME)
    assert got[(1, 1)].asset is None
    failed = got[(1, 2)]
    assert (failed.verdict, failed.seed, failed.failure, failed.asset) == (
        Verdict.ERROR,
        None,
        "render",
        None,
    )
    assert all(f.prompt is None for f in got.values())


# ------------------------------------------------------------------- document key


def test_the_key_changes_with_every_input_but_not_with_frame_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = plan(screenplay())
    frames = mixed(p)
    key = document_key(PID, STYLE, frames)
    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert document_key(PID, STYLE, list(reversed(frames))) == key
    changed = [
        document_key(uuid.uuid4(), STYLE, frames),
        document_key(PID, replace(STYLE, key="other"), frames),
        document_key(PID, replace(STYLE, label="Relabelled"), frames),  # the footer prints it
        document_key(PID, STYLE, [replace(frames[0], asset="frames/z.png"), *frames[1:]]),
        document_key(PID, STYLE, [replace(frames[0], state=FrameState.WARNED), *frames[1:]]),
        document_key(PID, STYLE, [replace(frames[0], verdict=Verdict.WARN), *frames[1:]]),
        document_key(
            PID, STYLE, [*frames[:2], replace(frames[2], noted_checks=(Check.LIGHT,)), *frames[3:]]
        ),
        document_key(PID, STYLE, [*frames[:4], replace(frames[4], failure="restart")]),
    ]
    assert key not in changed and len(set(changed)) == len(changed)
    monkeypatch.setattr(document, "DOCUMENT_VERSION", DOCUMENT_VERSION + 1)
    assert document_key(PID, STYLE, frames) != key


# ------------------------------------------------------------------- layout


def test_a_block_per_shot_in_plan_order_with_its_title_span_and_audit_line() -> None:
    sp = screenplay()
    p = plan(sp)
    pages = layout_document(mixed(p), p, sp, STYLE)
    got = blocks(pages)
    assert [b.shot for b in got] == [(s.scene_index, s.number) for s in p.shots]
    assert [b.title for b in got] == [
        "1.1  WIDE / STATIC",
        "1.2  CLOSE UP / PAN",
        "2.1  MEDIUM / STATIC",
        "2.2  OVER SHOULDER / STATIC",
        "3.1  INSERT / STATIC",
    ]
    first = p.shots[0].span
    assert got[0].span_label == f"p.{first.page} l.{first.line_start}\u2013{first.line_end}"
    assert [b.audit_line for b in got] == [
        "Audit: pass",
        "Audit: warn (light, framing)",
        None,
        None,
        None,
    ]
    assert all(b.frame_rect == (180, b.y, 880, 495) for b in got)  # centred, 16:9
    assert not any(b.continued for b in got)


def test_scenes_start_pages_and_blocks_stay_between_header_and_footer() -> None:
    sp = screenplay()
    p = plan(sp)
    pages = layout_document(mixed(p), p, sp, STYLE)
    assert [pg.number for pg in pages] == list(range(1, len(pages) + 1))
    scenes = [pg.scene_index for pg in pages]
    assert scenes == sorted(scenes) and set(scenes) == {0, 1, 2}
    for pg in pages:
        assert pg.blocks
        top, bottom = content_top(sp, pg.scene_index), content_bottom(STYLE)
        ys = [(b.y, b.y + block_height(b)) for b in pg.blocks]
        assert ys[0][0] == top and all(end <= bottom for _, end in ys)
        assert all(nxt[0] - prev[1] == 40 for prev, nxt in pairwise(ys))
        assert all(b.shot[0] == pg.scene_index for b in pg.blocks)
    assert layout_document(mixed(p), p, sp, STYLE) == pages  # deterministic


def test_two_short_shots_share_a_page() -> None:
    # Scene 1's two shots cite at most three script lines each: one page, not two.
    sp = screenplay()
    p = plan(sp)
    pages = layout_document(mixed(p), p, sp, STYLE)
    assert [[b.shot for b in pg.blocks] for pg in pages][:2] == [[(0, 1), (0, 2)], [(1, 1), (1, 2)]]


def test_a_source_too_long_for_a_page_continues_with_every_line() -> None:
    sp = screenplay()
    p = plan(sp)
    long = "\n".join(f"Line {i}: the lamp turns and the beam sweeps the water." for i in range(60))
    # T103: no elements, so the lines are `source`'s own (the fallback), as before T103.
    shots = (replace(p.shots[0], elements=(), source=long), *p.shots[1:])
    p = replace(p, shots=shots)
    pages = layout_document(mixed(p), p, sp, STYLE)
    parts = [b for b in blocks(pages) if b.shot == (0, 1)]
    assert len(parts) >= 2
    assert parts[0].frame_rect is not None and not parts[0].continued
    assert all(b.continued and b.frame_rect is None and b.audit_line is None for b in parts[1:])
    assert all(b.title == "1.1 (cont.)" for b in parts[1:])
    lines = [line.text for b in parts for line in b.source_lines]
    assert lines == [f"Line {i}: the lamp turns and the beam sweeps the water." for i in range(60)]
    for pg in pages:
        assert all(b.y + block_height(b) <= content_bottom(STYLE) for b in pg.blocks)


def test_source_lines_keep_element_breaks_and_are_never_cut_or_folded() -> None:
    sp = screenplay()
    p = plan(sp)
    text = "\u201cIt\u2019s gone\u201d \u2014 " + " ".join(["lighthouse"] * 40) + "\nAll of it."
    shots = (replace(p.shots[0], elements=(), source=text), *p.shots[1:])  # the fallback (T103)
    p = replace(p, shots=shots)
    (first, *_) = blocks(layout_document(mixed(p), p, sp, STYLE))
    texts = [line.text for line in first.source_lines]
    assert texts[-1] == "All of it."  # its own element, its own line
    assert " ".join(texts[:-1]) == text.split("\n")[0]  # curly quotes, dash kept


def test_the_heading_is_its_span_line_even_after_a_form_feed() -> None:
    # Spans number lines by split("\n"); splitlines() would also break on the form feed and
    # shift every later line (review of T027).
    text, starts = two_page_text()
    sp = parse_text(text.replace("FADE IN:", "FADE IN:\f"), starts)
    assert "\f" in sp.text  # the form feed survives parsing, so the case is real
    p = plan(sp)
    heading = content_heading(sp, 1)
    printed = sp.text.split("\n")[sp.scenes[1].span.line_start - 1]
    assert heading == [" ".join(printed.split())]  # its words, a run of spaces as one
    assert "EXT. LIGHTHOUSE GALLERY" in heading[0]
    assert layout_document(mixed(p), p, sp, STYLE)  # and the document still lays out


def test_a_shot_without_a_frame_is_refused() -> None:
    sp = screenplay()
    p = plan(sp)
    with pytest.raises(ValueError, match=r"1\.2"):
        layout_document([f for f in mixed(p) if f.shot != (0, 2)], p, sp, STYLE)


# ------------------------------------------------------------------- cards


def test_the_withheld_and_failed_cards_say_why_and_where() -> None:
    sp = screenplay()
    p = plan(sp)
    _, _, withheld, error, failed = mixed(p)
    span = p.shots[2].span
    assert span.line_start == span.line_end  # a one-line shot: "l.24", never "l.24\u201324"
    where = f"Script p.{span.page} l.{span.line_start}"
    withheld_card = ("Frame withheld: failed audit (unscripted person)", where)
    assert card_lines(withheld, p.shots[2]) == withheld_card
    assert card_lines(error, p.shots[3])[0] == "Frame withheld: failed audit (audit error)"
    assert card_lines(failed, p.shots[4])[0] == "Frame not drawn: the renderer failed"
    unnamed = replace(withheld, noted_checks=())  # a row whose audit names no check
    assert card_lines(unnamed, p.shots[2])[0] == "Frame withheld: failed audit"
    restarted = replace(failed, failure="restart")
    assert card_lines(restarted, p.shots[4])[0] == "Frame not drawn: the job was interrupted"


def test_a_span_reads_as_the_web_s_span_ref_prints_it() -> None:
    assert span_text(Span(2, 97, 97)) == "p.2 l.97"  # one line: never "l.97\u201397"
    assert span_text(Span(3, 140, 147)) == "p.3 l.140\u2013147"


def test_a_one_line_shot_s_label_and_card_say_one_line() -> None:
    sp = screenplay()
    p = plan(sp)
    one = replace(p.shots[2], span=Span(2, 97, 97))
    frames = [replace(f, shot=f.shot) for f in mixed(p)]
    assert card_lines(frames[2], one)[1] == "Script p.2 l.97"


def test_every_card_line_fits_inside_its_box_with_room_to_spare() -> None:
    """The live run of 2026-10-10: wrapped to 1000 px, a three-check reason crossed the 880 px
    box's border. Each line now keeps 40 px clear on both sides."""
    assert CARD_TEXT_W == FRAME_W - 80
    font = document._font(False, 26)  # pyright: ignore[reportPrivateUsage]
    longest = "Frame withheld: failed audit (unscripted person, unscripted object, text in frame)"
    lines = document.wrap(longest, CARD_TEXT_W, font)
    assert len(lines) > 1 and all(font.getlength(line) <= CARD_TEXT_W for line in lines)


# ------------------------------------------------------------------- the PDF


def test_one_a4_page_per_layout_page_and_no_withheld_or_failed_pixels_read() -> None:
    sp = screenplay()
    p = plan(sp)
    frames = mixed(p)
    pages = layout_document(frames, p, sp, STYLE)
    images = {f.shot: png() for f in frames if f.state in (FrameState.PASSED, FrameState.WARNED)}
    # Bytes for the withheld and failed shots that aren't an image: reading them would raise.
    images |= {f.shot: b"not a png" for f in frames if f.shot not in images}
    pdf = render_pdf(pages, frames, p, sp, STYLE, images)
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf)) == len(pages)
    # 1240 x 1754 px at 150 dpi is A4: 595.2 x 841.92 pt.
    assert re.search(rb"/MediaBox\s*\[\s*0\s+0\s+595\.2\d*\s+841\.92\d*\s*\]", pdf)
    assert PAGE_H == 1754


def test_an_accepted_frame_without_its_image_is_an_error_not_a_blank() -> None:
    sp = screenplay()
    p = plan(sp)
    frames = mixed(p)
    with pytest.raises(KeyError):
        render_pdf(layout_document(frames, p, sp, STYLE), frames, p, sp, STYLE, {})


# ------------------------------------------------------------------- export


class CountingStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.gets: list[str] = []

    async def get(self, path: str) -> bytes:
        self.gets.append(path)
        return await super().get(path)


async def test_export_builds_and_stores_once_then_reads_no_frame() -> None:
    sp = screenplay()
    p = plan(sp)
    frames = mixed(p)
    store = CountingStore()
    for f in frames:
        if f.asset is not None:
            await store.put(f.asset, png(), "image/png")
    path = await export_pdf(store, PID, STYLE, p, sp, frames)
    assert path == f"storyboards/{document_key(PID, STYLE, frames)}.pdf"
    data, content_type = store.objects[path]
    assert data.startswith(b"%PDF") and content_type == "application/pdf"
    assert sorted(store.gets) == sorted(f.asset for f in frames if f.asset is not None)

    store.gets.clear()
    assert await export_pdf(store, PID, STYLE, p, sp, frames) == path
    assert store.gets == []  # a store hit: no frame read, nothing rebuilt
