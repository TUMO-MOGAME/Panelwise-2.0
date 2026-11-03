"""T103: the storyboard PDF names each line's speaker, as the web's frame sheet does
(storyboard.md §3.4 Speakers and Fitting, §6, §9). The sample screenplay; no network."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from app.script import Dialogue, Screenplay, parse_text
from app.shots import ShotPlan
from app.storyboard import document
from app.storyboard.document import CONTENT_W, document_key, layout_document, render_pdf
from app.storyboard.model import Block, SourceLine
from app.verify.model import FrameState
from tests.comic.test_layout import plan_of
from tests.script.conftest import ACTION, CUE, DIALOGUE, PAREN, Row, heading, layout
from tests.storyboard.conftest import STYLE, shot_of
from tests.storyboard.test_document import blocks, frame, mixed, plan, png, screenplay

cut = document._cut  # pyright: ignore[reportPrivateUsage]
content_bottom = document._content_bottom  # pyright: ignore[reportPrivateUsage]
block_height = document._height  # pyright: ignore[reportPrivateUsage]


def block_of(p: ShotPlan, sp: Screenplay, shot: tuple[int, int]) -> list[Block]:
    frames = [frame(s) for s in p.shots]
    return [b for b in blocks(layout_document(frames, p, sp, STYLE)) if b.shot == shot]


def lines_of(p: ShotPlan, sp: Screenplay, shot: tuple[int, int]) -> list[SourceLine]:
    return [line for b in block_of(p, sp, shot) for line in b.source_lines]


# --- the lines ----------------------------------------------------------------------------------


def test_actions_print_no_speaker() -> None:
    sp = screenplay()
    got = lines_of(plan(sp), sp, (0, 1))  # scene 1's two action elements
    assert not any(line.speaker for line in got)
    assert all(line.of is None for line in got)


def test_each_speech_sits_under_its_speaker_with_its_extension() -> None:
    sp = screenplay()
    got = lines_of(plan(sp), sp, (0, 2))  # NANDI, then THABO (O.S.)
    speakers = [line.text for line in got if line.speaker]
    assert speakers == ["NANDI", "THABO (O.S.)"]
    assert got[0] == SourceLine("NANDI", speaker=True)
    assert got[1] == SourceLine("You came back.", of="NANDI")
    assert all(line.of == "THABO (O.S.)" for line in got[3:])


def test_the_speech_lines_are_the_source() -> None:
    sp = screenplay()
    p = plan(sp)
    for shot in p.shots:
        got = lines_of(p, sp, (shot.scene_index, shot.number))
        words = " ".join(line.text for line in got if not line.speaker).split()
        assert words == shot.source.split()


def test_one_cue_in_a_row_prints_once_and_a_new_extension_again() -> None:
    sp = screenplay()
    got = lines_of(plan(sp), sp, (1, 2))  # THABO, THABO, THABO (CONT'D)
    assert [line.text for line in got if line.speaker] == ["THABO", "THABO (CONT'D)"]


def custom(*rows: Row) -> Screenplay:
    out: list[Row] = [(CUE - 4, "SPEAKERS"), None, heading("1", "INT. ROOM - DAY"), None]
    for row in rows:
        out += [row] if row is not None and row[0] in (CUE, PAREN) else [row, None]
    return parse_text(layout(out), [])


def one_shot(sp: Screenplay, elements: list[int]) -> ShotPlan:
    return plan_of(shot_of(sp, 0, elements, number=1))


def only(p: ShotPlan, sp: Screenplay) -> list[SourceLine]:
    frames = [frame(s) for s in p.shots]
    return [line for b in blocks(layout_document(frames, p, sp, STYLE)) for line in b.source_lines]


def test_an_action_between_two_speeches_of_one_cue_prints_it_twice() -> None:
    sp = custom(
        (CUE, "LERATO"),
        (DIALOGUE, "Wait."),
        (ACTION, "She runs."),
        (CUE, "LERATO"),
        (DIALOGUE, "Wait!"),
    )
    got = only(one_shot(sp, [0, 1, 2]), sp)
    assert [line.text for line in got if line.speaker] == ["LERATO", "LERATO"]


def test_a_parenthetical_is_not_printed() -> None:
    sp = custom((CUE, "LERATO"), (PAREN, "(quietly)"), (DIALOGUE, "Wait."))
    (speech,) = sp.scenes[0].elements
    assert isinstance(speech, Dialogue) and speech.parenthetical
    got = only(one_shot(sp, [0]), sp)
    assert [line.text for line in got] == ["LERATO", "Wait."]


def with_element(sp: Screenplay, index: int, element: Any) -> Screenplay:
    scene = sp.scenes[0]
    elements = (*scene.elements[:index], element, *scene.elements[index + 1 :])
    return replace(sp, scenes=(replace(scene, elements=elements), *sp.scenes[1:]))


def test_a_line_break_in_a_speech_is_kept() -> None:
    sp = custom((CUE, "LERATO"), (DIALOGUE, "Wait."))
    speech = sp.scenes[0].elements[0]
    sp = with_element(sp, 0, replace(speech, text="Wait.\nPlease."))
    got = only(one_shot(sp, [0]), sp)
    assert [line.text for line in got] == ["LERATO", "Wait.", "Please."]


def test_a_cue_too_wide_wraps_to_a_bold_speaker_run() -> None:
    sp = custom((CUE, "LERATO"), (DIALOGUE, "Wait."))
    wide = " ".join(["MAGNIFICENT"] * 12)
    sp = with_element(sp, 0, replace(sp.scenes[0].elements[0], cue=wide))
    got = only(one_shot(sp, [0]), sp)
    run = [line for line in got if line.speaker]
    assert len(run) >= 2
    bold = document._font(True, 22)  # pyright: ignore[reportPrivateUsage]
    assert all(bold.getlength(line.text) <= CONTENT_W for line in run)
    assert " ".join(line.text for line in run) == wide


def test_a_heading_only_shot_and_a_changed_source_print_the_source() -> None:
    sp = screenplay()
    heading_only = plan_of(shot_of(sp, 2, [], number=1))
    assert [line.text for line in only(heading_only, sp)] == [sp.scenes[2].heading]
    p = plan(sp)
    changed = replace(p, shots=(replace(p.shots[1], source="You came back."), *p.shots[2:]))
    got = lines_of(changed, sp, (0, 2))
    assert got == [SourceLine("You came back.")]


def test_an_element_out_of_range_prints_the_source() -> None:
    sp = screenplay()
    p = plan(sp)
    broken = replace(p, shots=(replace(p.shots[1], elements=(2, 9)), *p.shots[2:]))
    got = lines_of(broken, sp, (0, 2))
    assert not any(line.speaker for line in got)


# --- fitting ------------------------------------------------------------------------------------


S, L = SourceLine("A", speaker=True), SourceLine("x", of="A")


@pytest.mark.parametrize(
    ("lines", "room", "want"),
    [
        ([L, L, S, L], 3, 2),  # the run moves on with its speech
        ([L, S, S, L], 3, 1),  # a whole run of two
        ([S, S, L], 2, 2),  # all that fits is the run: it stays
        ([L, L, L], 2, 2),
    ],
)
def test_cut(lines: list[SourceLine], room: int, want: int) -> None:
    assert cut(lines, room) == want


def test_a_long_speech_continues_under_its_speaker_and_no_page_ends_on_one() -> None:
    sp = custom((CUE, "LERATO"), (DIALOGUE, "Wait."))
    speech = sp.scenes[0].elements[0]
    long = "\n".join(f"Line {i}: the lamp turns and the beam sweeps the water." for i in range(90))
    sp = with_element(sp, 0, replace(speech, text=long))
    p = one_shot(sp, [0])
    pages = layout_document([frame(s) for s in p.shots], p, sp, STYLE)
    parts = blocks(pages)
    assert len(parts) >= 2
    for part in parts[1:]:
        assert part.source_lines[0] == SourceLine("LERATO", speaker=True)  # its speaker again
    for part in parts:
        assert not part.source_lines[-1].speaker
        assert part.y + block_height(part) <= content_bottom(STYLE)
    speech_lines = [line.text for b in parts for line in b.source_lines if not line.speaker]
    assert speech_lines == long.split("\n")


# --- drawing and the key ------------------------------------------------------------------------


def test_a_speaker_line_is_drawn_bold(monkeypatch: pytest.MonkeyPatch) -> None:
    sp = screenplay()
    p = plan(sp)
    frames = mixed(p)
    images = {f.shot: png() for f in frames if f.state in (FrameState.PASSED, FrameState.WARNED)}
    real = document._font  # pyright: ignore[reportPrivateUsage]
    drawn: list[tuple[bool, int]] = []

    def spy(bold: bool, size: int) -> Any:
        drawn.append((bold, size))
        return real(bold, size)

    pages = layout_document(frames, p, sp, STYLE)
    monkeypatch.setattr(document, "_font", spy)
    render_pdf(pages, frames, p, sp, STYLE, images)
    speakers = sum(line.speaker for b in blocks(pages) for line in b.source_lines)
    assert speakers > 0
    assert drawn.count((True, 22)) == speakers + len(pages)  # and each page's STORYBOARD


def test_the_version_is_3_and_changes_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert document.DOCUMENT_VERSION == 3
    sp = screenplay()
    frames = mixed(plan(sp))
    pid = uuid.UUID(int=103)
    now = document_key(pid, STYLE, frames)
    monkeypatch.setattr(document, "DOCUMENT_VERSION", 2)
    assert document_key(pid, STYLE, frames) != now


def test_a_page_break_landing_on_a_speaker_moves_it_with_its_speech() -> None:
    # Size the first speech so the first page's last fitting line is LERATO's second cue.
    sp = custom((CUE, "THABO"), (DIALOGUE, "One."), (CUE, "LERATO"), (DIALOGUE, "Two."))
    p = one_shot(sp, [0, 1])
    first = layout_document([frame(s) for s in p.shots], p, sp, STYLE)
    top = first[0].blocks[0]
    fixed = block_height(replace(top, source_lines=()))
    room = (content_bottom(STYLE) - top.y - fixed) // 30
    thabo, lerato = sp.scenes[0].elements
    sp = with_element(sp, 0, replace(thabo, text="\n".join(f"Line {i}." for i in range(room - 2))))
    sp = with_element(sp, 1, replace(lerato, text="\n".join(f"More {i}." for i in range(20))))
    p = one_shot(sp, [0, 1])
    parts = blocks(layout_document([frame(s) for s in p.shots], p, sp, STYLE))
    assert len(parts[0].source_lines) == room - 1  # THABO and his speech; LERATO moved on
    assert not parts[0].source_lines[-1].speaker
    assert parts[1].source_lines[0] == SourceLine("LERATO", speaker=True)
    assert [line.text for line in parts[1].source_lines].count("LERATO") == 1


def test_a_cue_taller_than_a_page_lays_out_and_keeps_every_line() -> None:
    sp = custom((CUE, "LERATO"), (DIALOGUE, "Wait."))
    huge = " ".join(["MAGNIFICENT"] * 400)  # a speaker run longer than a page
    sp = with_element(sp, 0, replace(sp.scenes[0].elements[0], cue=huge))
    p = one_shot(sp, [0])
    parts = blocks(layout_document([frame(s) for s in p.shots], p, sp, STYLE))
    run = [line.text for b in parts for line in b.source_lines if line.speaker]
    assert " ".join(run) == huge  # never repeated: no page before the speech held a speech line
    assert [line.text for b in parts for line in b.source_lines if not line.speaker] == ["Wait."]


def test_an_empty_cue_prints_no_speaker() -> None:
    sp = custom((CUE, "LERATO"), (DIALOGUE, "Wait."))
    sp = with_element(sp, 0, replace(sp.scenes[0].elements[0], cue=""))
    got = only(one_shot(sp, [0]), sp)
    assert got == [SourceLine("Wait.")]


def test_a_page_with_no_room_for_a_line_still_lays_the_block_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # room 0 on an empty page (only a heading taller than the page does it): placed whole, no loop.
    sp = custom((ACTION, "Rain."))
    p = one_shot(sp, [0])
    bottom = content_bottom(STYLE)

    def low(*_: object) -> int:
        return bottom - 590  # the frame, title and audit (579 px) fit; no 30 px line does

    monkeypatch.setattr(document, "_content_top", low)
    parts = blocks(layout_document([frame(s) for s in p.shots], p, sp, STYLE))
    assert [line.text for b in parts for line in b.source_lines] == ["Rain."]
