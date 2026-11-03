"""render_pages, the withheld card, to_pdf, to_json: comic.md §4 step 6, §6, §9 (Frames, Export)."""

import io
import json

import pdfplumber
import pytest
from PIL import Image

from app.comic import (
    CaptionKind,
    ComicBook,
    ComicError,
    PanelFrame,
    WithheldCard,
    panel_frame,
    place_lettering,
    render_pages,
    to_json,
    to_pdf,
    withheld_checks,
)
from app.comic.render import card_lines, failed_panel
from app.llm import Usage
from app.script import Span
from app.shots import Framing
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
from tests.comic.conftest import Key, frames, solid
from tests.comic.test_bubbles import sample
from tests.comic.test_layout import shot

RED = (255, 0, 0)
BLUE = (30, 90, 160)
SHOT = shot(1, 2, Framing.MEDIUM, 1, 2, 3)


def image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def pixel(page: Image.Image, x: int, y: int) -> tuple[int, ...]:
    value = page.getpixel((x, y))
    assert isinstance(value, tuple)
    return value


def lettered_sample() -> tuple[ComicBook, dict[Key, PanelFrame]]:
    screenplay, plan, book = sample()
    given = frames(book, lambda r: solid(r, BLUE))
    return place_lettering(book, screenplay, plan, given), given


def result(check: Check, ok: bool, severity: Severity = Severity.HARD) -> CheckResult:
    return CheckResult(check, severity, ok, "")


def audit(
    verdict: Verdict, *checks: CheckResult, positions: dict[str, Position] | None = None
) -> Audit:
    return Audit((1, 2), 1, 7, None, None, checks, verdict, positions or {}, (), Usage(0, 0, 0))


def outcome(state: FrameState, *audits: Audit, png: bytes = b"frame") -> FrameOutcome:
    frame = RenderedFrame((1, 2), len(audits), 7, png, 10, 10, "")
    return FrameOutcome((1, 2), state, frame, audits)


# ---------------------------------------------------------------- withheld card


def test_the_card_names_the_failed_hard_checks_in_check_order() -> None:
    last = audit(
        Verdict.FAIL,
        result(Check.TEXT_IN_FRAME, False),
        result(Check.LIGHT, False, Severity.SOFT),  # soft: not on the card
        result(Check.SETTING, True),
        result(Check.UNSCRIPTED_PERSON, False),
    )
    assert withheld_checks(last) == "unscripted person, text in frame"
    assert withheld_checks(audit(Verdict.ERROR)) == "audit error"


def test_panel_frame_takes_an_accepted_frame_and_its_positions() -> None:
    seen = {"THABO": Position.RIGHT}
    for state in (FrameState.PASSED, FrameState.WARNED):
        failed = audit(Verdict.FAIL, result(Check.UNSCRIPTED_OBJECT, False))
        got = panel_frame(outcome(state, failed, audit(Verdict.PASS, positions=seen)), SHOT)
        assert got == PanelFrame(b"frame", seen, False)


def test_panel_frame_gives_a_withheld_frame_its_card_and_none_of_its_pixels() -> None:
    first = audit(Verdict.FAIL, result(Check.SETTING, False))
    last = audit(
        Verdict.FAIL, result(Check.UNSCRIPTED_PERSON, False), positions={"THABO": Position.LEFT}
    )
    got = panel_frame(outcome(FrameState.WITHHELD, first, last), SHOT)
    assert got == PanelFrame(b"", {}, True, WithheldCard("unscripted person", SHOT.span))


@pytest.mark.parametrize("state", [FrameState.FAILED, FrameState.RENDERING, FrameState.AUDITING])
def test_panel_frame_refuses_a_frame_that_is_neither_accepted_nor_withheld(
    state: FrameState,
) -> None:
    with pytest.raises(ComicError, match="scene 1, shot 2"):
        panel_frame(outcome(state, audit(Verdict.PASS)), SHOT)


def test_a_withheld_frame_with_no_failed_hard_check_is_refused() -> None:
    soft = audit(Verdict.FAIL, result(Check.LIGHT, False, Severity.SOFT))
    with pytest.raises(ComicError, match="scene 1, shot 2"):
        panel_frame(outcome(FrameState.WITHHELD, soft), SHOT)


def test_a_withheld_frame_needs_its_card_and_only_it_has_one() -> None:
    with pytest.raises(ComicError):
        PanelFrame(b"", {}, True)
    with pytest.raises(ComicError):
        PanelFrame(b"", {}, False, WithheldCard("audit error", SHOT.span))


def test_the_cards_two_lines() -> None:
    card = WithheldCard("unscripted person, text in frame", Span(3, 41, 44))
    assert card_lines(card) == (
        "Frame withheld: failed audit (unscripted person, text in frame)",
        "Script p.3 l.41\u201344",  # an en dash
    )
    # T067: a panel whose renderer failed, said as the storyboard's failed card says it.
    assert card_lines(WithheldCard("", Span(3, 41, 44), failed=True)) == (
        "Frame not drawn: the renderer failed",
        "Script p.3 l.41\u201344",
    )


def test_a_failed_panel_is_a_card_with_no_pixels_and_no_positions() -> None:
    frame = failed_panel(SHOT)
    assert (frame.png, dict(frame.positions), frame.withheld) == (b"", {}, True)
    assert frame.card == WithheldCard("", SHOT.span, failed=True)


# ------------------------------------------------------------------------ pages


def test_one_page_png_per_page_at_trim_size_with_each_frame_at_its_rect() -> None:
    book, given = lettered_sample()
    pages = render_pages(book, given)
    assert len(pages) == len(book.pages) == 2
    for data, page in zip(pages, book.pages, strict=True):
        rendered = image(data)
        assert rendered.size == (1988, 3075)
        assert pixel(rendered, 10, 10) == (255, 255, 255)  # the margin
        for panel in page.panels:
            x, y, w, h = panel.rect
            assert pixel(rendered, x + 1, y + 1) == (0, 0, 0)  # the panel border
            assert pixel(rendered, x + w - 40, y + h - 40) == BLUE  # the frame itself
    assert render_pages(book, given) == pages  # deterministic


def test_lettering_is_drawn_in_its_boxes() -> None:
    book, given = lettered_sample()
    rendered = image(render_pages(book, given)[0])
    panel = book.pages[0].panels[0]
    caption = panel.captions[0]
    assert caption.kind is CaptionKind.SCENE
    cx, cy, cw, ch = caption.rect
    inside = [
        pixel(rendered, x, y)
        for x in range(cx + 4, cx + cw - 4)
        for y in range(cy + 4, cy + ch - 4)
    ]
    assert BLUE not in inside  # the caption box covers the art
    assert (0, 0, 0) in inside or any(sum(p) < 200 for p in inside)  # and carries ink
    bubble = book.pages[0].panels[1].bubbles[0]
    bx, by, bw, _ = bubble.rect
    assert pixel(rendered, bx + bw // 2, by + 2) == (255, 255, 255)  # a white bubble


def test_a_withheld_frames_pixels_never_reach_the_page() -> None:
    book, given = lettered_sample()
    key = (1, 2)
    panel = next(
        p for page in book.pages for p in page.panels if (p.scene_index, p.shot_number) == key
    )
    card = WithheldCard("unscripted person", Span(1, 27, 33))
    given[key] = PanelFrame(solid(panel.rect, RED), {}, True, card)
    pages = [image(p) for p in render_pages(book, given)]

    assert all(RED not in {c for _, c in (page.getcolors(1 << 24) or [])} for page in pages)
    page = pages[0 if panel in book.pages[0].panels else 1]
    x, y, w, h = panel.rect
    assert pixel(page, x + 1, y + 1) == (128, 128, 128)  # the card's grey border
    assert pixel(page, x + w - 10, y + h - 10) == (255, 255, 255)  # a white card
    middle = [pixel(page, x + i, y + h // 2 + j) for i in range(0, w, 3) for j in range(-40, 40, 3)]
    assert any(sum(p) < 200 for p in middle)  # its lines are lettered


def test_a_withheld_frame_is_shown_as_a_card_even_with_garbage_bytes() -> None:
    book, given = lettered_sample()
    key = (2, 1)
    given[key] = PanelFrame(b"not a png", {}, True, WithheldCard("audit error", Span(2, 35, 37)))
    assert len(render_pages(book, given)) == 2


def test_a_frame_not_at_its_rects_size_fails_the_render() -> None:
    book, given = lettered_sample()
    panel = book.pages[1].panels[0]
    x, y, w, h = panel.rect
    given[(panel.scene_index, panel.shot_number)] = PanelFrame(solid((x, y, w - 2, h)), {}, False)
    with pytest.raises(ComicError, match=f"scene {panel.scene_index}, shot {panel.shot_number}"):
        render_pages(book, given)


def test_a_missing_frame_fails_the_render() -> None:
    book, given = lettered_sample()
    del given[(0, 1)]
    with pytest.raises(ComicError, match="scene 0, shot 1"):
        render_pages(book, given)


# ------------------------------------------------------------------------ export


def test_the_pdf_has_one_trim_size_page_per_page() -> None:
    book, given = lettered_sample()
    pdf = to_pdf(render_pages(book, given))
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        assert len(document.pages) == 2
        for page in document.pages:
            assert page.width == pytest.approx(6.625 * 72, abs=0.5)
            assert page.height == pytest.approx(10.25 * 72, abs=0.5)


def test_a_pdf_of_no_pages_is_refused() -> None:
    with pytest.raises(ComicError):
        to_pdf([])


def test_the_json_has_the_readers_shape_and_round_trips_every_span() -> None:
    book, _ = lettered_sample()
    urls = {
        (
            p.scene_index,
            p.shot_number,
        ): f"https://storage.example/frames/{p.scene_index}-{p.shot_number}.png"
        for page in book.pages
        for p in page.panels
        if (p.scene_index, p.shot_number) != (0, 2)
    }
    data = json.loads(json.dumps(to_json(book, urls)))

    assert list(data) == ["pages"]
    assert len(data["pages"]) == len(book.pages)
    for got, page in zip(data["pages"], book.pages, strict=True):
        assert list(got) == ["number", "width", "height", "panels"]
        assert (got["number"], got["width"], got["height"]) == (page.number, 1988, 3075)
        for gp, panel in zip(got["panels"], page.panels, strict=True):
            key = (panel.scene_index, panel.shot_number)
            if key == (0, 2):
                assert list(gp) == ["shot", "rect", "withheld", "bubbles", "captions"]
                assert gp["withheld"] is True
            else:
                assert list(gp) == ["shot", "rect", "frame_url", "withheld", "bubbles", "captions"]
                assert (gp["frame_url"], gp["withheld"]) == (urls[key], False)
            assert gp["shot"] == list(key) and gp["rect"] == list(panel.rect)
            for gb, bubble in zip(gp["bubbles"], panel.bubbles, strict=True):
                assert list(gb) == [
                    "kind",
                    "speaker",
                    "text",
                    "element",
                    "span",
                    "rect",
                    "tail",
                    "font_px",
                    "voice",
                    "linked",
                ]
                assert Span(**gb["span"]) == bubble.span
                assert (gb["kind"], gb["speaker"], gb["text"], gb["element"]) == (
                    bubble.kind.value,
                    bubble.speaker,
                    bubble.text,
                    bubble.element,
                )
                assert gb["rect"] == list(bubble.rect) and gb["font_px"] == bubble.font_px
                assert gb["tail"] == (list(bubble.tail) if bubble.tail else None)
                assert gb["voice"] == bubble.voice.value  # T117
                assert gb["linked"] is bubble.linked  # T118
            for gc, caption in zip(gp["captions"], panel.captions, strict=True):
                assert list(gc) == ["kind", "text", "element", "span", "rect", "font_px", "voice"]
                assert gc["voice"] == caption.voice.value
                assert Span(**gc["span"]) == caption.span
                assert (gc["kind"], gc["text"], gc["element"]) == (
                    caption.kind.value,
                    caption.text,
                    caption.element,
                )
    first = data["pages"][0]["panels"][0]["captions"][0]
    assert first == {
        "kind": "scene",
        "text": "LIGHTHOUSE KITCHEN — NIGHT",
        "element": None,
        "span": {"page": 1, "line_start": 5, "line_end": 5},
        "rect": first["rect"],
        "font_px": 32,
        "voice": "plain",
    }
