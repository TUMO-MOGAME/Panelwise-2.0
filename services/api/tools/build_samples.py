"""Build the sample screenplay PDFs in samples/ from their Fountain-style sources.

    cd services/api && uv run python -m tools.build_samples

Every sample is self-written for this repo; never add a copyrighted script (samples/README.md).
A source is a small subset of Fountain (https://fountain.io): a `Key: value` title page, then
blocks separated by blank lines --

  heading      one INT. / EXT. / INT/EXT. line; `#12A#` at its end sets the scene number
  transition   one all-caps line ending in `TO:` or `TO BLACK.`, or FADE OUT.
  dialogue     an all-caps cue, then its lines; a `(...)` line is a parenthetical, and a `===`
               line forces a page break inside the speech
  page break   `===` on its own
  action       anything else (`!` at the start forces it); each source line is its own line

The PDF is US-letter 12 pt Courier at the standard screenplay columns, 54 body lines a page. A
speech that doesn't fit is split with (MORE) and its cue repeated with (CONT'D); a heading is
never left at the foot of a page. The tool then prints what the real parser reads back.
"""

import re
import sys
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fpdf import FPDF

from app.script import Dialogue, Screenplay, parse_pdf

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

# Columns, in characters of 12 pt Courier (7.2 pt each) right of LEFT_EDGE: action and headings
# at 1.5 in, dialogue 2.5 in, parenthetical 3.1 in, cue 3.7 in, transitions 6 in.
NUM, ACTION, DIALOGUE, PAREN, CUE, TRANSITION, RIGHT = 4, 10, 20, 26, 32, 55, 66
LEFT_EDGE, CHAR, LINE, TOP = 36.0, 7.2, 12.0, 72.0
BODY_LINES = 54
ACTION_WIDTH, DIALOGUE_WIDTH, PAREN_WIDTH = 60, 35, 25
# A fixed date keeps a rebuild of unchanged sources byte-stable.
BUILT = datetime(2026, 9, 30, tzinfo=UTC)

type Row = tuple[int, str] | None  # (column, text); None is a blank line
type Kind = Literal["heading", "action", "dialogue", "transition", "break"]


@dataclass(frozen=True)
class Options:
    numbered: bool = True  # scene numbers at both edges of each heading (a shooting script)
    continueds: bool = False  # (CONTINUED) / CONTINUED: where a scene runs over a page


OPTIONS: dict[str, Options] = {
    "the-red-kite": Options(),
    "lost-property": Options(numbered=False),
    "sipho-and-siphokazi": Options(continueds=True),
    "the-night-taxi": Options(),
    "market-day": Options(numbered=False),
    "the-lighthouse-inspector": Options(continueds=True),
    "the-borrowed-bicycle": Options(numbered=False),
    "rooftop-tomatoes": Options(),
    "load-shedding": Options(continueds=True),
    "gogos-recipe": Options(numbered=False),
    "stormwater": Options(),
    "the-choir": Options(),
    "final-whistle": Options(numbered=False),
}


@dataclass(frozen=True)
class Block:
    kind: Kind
    lines: tuple[str, ...]
    number: str = ""


_HEADING = re.compile(r"^(?:INT|EXT)\.?(?:/(?:INT|EXT)\.?)? ")
_NUMBER_TAG = re.compile(r"\s*#([0-9A-Z]+)#$")
_TITLE_KEY = re.compile(r"^([A-Z][A-Za-z ]*):\s+(\S.*)$")
_CUE = re.compile(r"^[A-Z][A-Z0-9 .'#-]*(?: \([A-Z.' ]+\))?$")
_EXTENSION = re.compile(r"\s*\([^)]*\)$")
_SPLIT = "==="


def parse_source(text: str) -> tuple[dict[str, str], list[Block]]:
    text.encode("latin-1")  # the PDF's core Courier font has no other glyphs
    chunks = [c.strip("\n") for c in re.split(r"\n[ \t]*\n", text.strip())]
    meta: dict[str, str] = {}
    title = [_TITLE_KEY.match(line) for line in chunks[0].splitlines()]
    if all(title):
        meta = {m[1]: m[2] for m in title if m}
        chunks = chunks[1:]
    return meta, [_classify([line.rstrip() for line in c.splitlines()]) for c in chunks]


def _classify(lines: list[str]) -> Block:
    first = lines[0]
    if lines == [_SPLIT]:
        return Block("break", ())
    if len(lines) == 1 and _HEADING.match(first):
        tag = _NUMBER_TAG.search(first)
        heading = first[: tag.start()] if tag else first
        return Block("heading", (heading,), tag[1] if tag else "")
    if (
        len(lines) == 1
        and first.isupper()
        and (first.endswith(("TO:", "TO BLACK.")) or first == "FADE OUT.")
    ):
        return Block("transition", (first,))
    if first.startswith("!"):
        return Block("action", (first[1:], *lines[1:]))
    if len(lines) >= 2 and _CUE.match(first):
        return Block("dialogue", tuple(lines))
    return Block("action", tuple(lines))


def _wrap(text: str, width: int) -> list[str]:
    # Breaking after a hyphen is what screenwriting software does, and what the samples test.
    return textwrap.wrap(text, width, break_on_hyphens=True, break_long_words=False)


def _speech_rows(lines: Sequence[str]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    speech: list[str] = []

    def end_speech() -> None:
        rows.extend((DIALOGUE, w) for w in _wrap(" ".join(speech), DIALOGUE_WIDTH))
        speech.clear()

    for line in lines:
        if line == _SPLIT:
            end_speech()
            rows.append((-1, _SPLIT))
        elif line.startswith("("):
            end_speech()
            rows.extend((PAREN, w) for w in _wrap(line, PAREN_WIDTH))
        else:
            speech.append(line.strip())
    end_speech()
    return rows


@dataclass
class Page:
    rows: list[Row] = field(default_factory=list[Row])
    footer: str | None = None


class Pager:
    def __init__(self, options: Options) -> None:
        self.options = options
        self.pages = [Page()]
        self.in_scene = False
        self.scene_count = 0

    @property
    def rows(self) -> list[Row]:
        return self.pages[-1].rows

    def room(self, rows: int) -> bool:
        gap = 1 if self.rows and self.rows[-1] is not None else 0
        return len(self.rows) + gap + rows <= BODY_LINES

    def turn(self) -> None:
        if self.options.continueds and self.in_scene:
            self.pages[-1].footer = "(CONTINUED)"
            self.pages.append(Page([(ACTION, "CONTINUED:"), None]))
        else:
            self.pages.append(Page())

    def put(self, rows: Sequence[Row]) -> None:
        if self.rows and self.rows[-1] is not None:
            self.rows.append(None)
        self.rows.extend(rows)

    def block(self, block: Block) -> None:
        match block.kind:
            case "break":
                self.turn()
            case "heading":
                self.heading(block)
            case "transition":
                if not self.room(1):
                    self.turn()
                self.put([(TRANSITION, block.lines[0])])
                self.in_scene = False
            case "action":
                rows = [(ACTION, w) for line in block.lines for w in _wrap(line, ACTION_WIDTH)]
                if not self.room(len(rows)):
                    self.turn()
                self.put(rows)
            case "dialogue":
                self.speech(block.lines[0], _speech_rows(block.lines[1:]))

    def heading(self, block: Block) -> None:
        # An explicit "4A" sets the count, so the next unmarked scene is 5.
        self.scene_count = int(re.sub(r"\D.*$", "", block.number) or self.scene_count + 1)
        text = block.lines[0]
        if self.options.numbered:
            number = block.number or str(self.scene_count)
            row = (NUM, f"{number:<{ACTION - NUM}}{text}".ljust(RIGHT - NUM) + number)
        else:
            row = (ACTION, text)
        self.in_scene = False
        if not self.room(4):  # the heading, a blank line and two lines of the scene
            self.turn()
        self.put([row])
        self.in_scene = True

    def speech(self, cue: str, body: list[tuple[int, str]]) -> None:
        rows = [(CUE, cue), *body]
        while True:
            split = next((i for i, r in enumerate(rows) if r[1] == _SPLIT), None)
            whole = rows if split is None else rows[:split]
            if split is None and self.room(len(whole)):
                self.put(rows)
                return
            # How many rows fit above a (MORE); a parenthetical stays with the line it qualifies.
            keep = len(whole)
            while keep >= 2 and not self.room(keep + 1):
                keep -= 1
            while keep >= 2 and rows[keep - 1][0] == PAREN:
                keep -= 1
            # Screenwriting software breaks a speech only between sentences; with no sentence end
            # above the fold, the whole speech moves overleaf (unless it is longer than a page).
            # A forced `===` split is taken as written.
            if keep != split:
                sentence = next(
                    (k for k in range(keep, 1, -1) if rows[k - 1][1].endswith((".", "!", "?"))),
                    None,
                )
                if sentence is not None:
                    keep = sentence
                elif len(whole) + 1 < BODY_LINES:
                    keep = 0
            if keep < 2:  # not even the cue and one sentence: the whole speech starts overleaf
                if not self.rows or self.rows == [(ACTION, "CONTINUED:"), None]:
                    raise ValueError(f"speech by {cue} cannot be split between sentences")
                self.turn()
                continue
            self.put([*rows[:keep], (CUE, "(MORE)")])
            self.turn()
            rest = rows[keep + 1 :] if keep == split else rows[keep:]
            rows = [(CUE, _EXTENSION.sub("", cue) + " (CONT'D)"), *rest]


def paginate(blocks: Sequence[Block], options: Options) -> list[Page]:
    pager = Pager(options)
    for block in blocks:
        pager.block(block)
    return pager.pages


def render(meta: dict[str, str], pages: Sequence[Page]) -> bytes:
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_font("Courier", size=12)
    pdf.set_auto_page_break(False)
    pdf.set_creation_date(BUILT)
    pdf.set_title(meta.get("Title", ""))
    pdf.set_author(meta.get("Author", ""))

    def x(column: int) -> float:
        return LEFT_EDGE + column * CHAR

    if meta:  # the title page: not numbered, and the parser ignores it (no scene heading yet)
        pdf.add_page()
        centred = [meta["Title"].upper(), "", meta.get("Credit", "Written by"), "", meta["Author"]]
        for n, text in enumerate(centred):
            pdf.text(306 - len(text) * CHAR / 2, 252 + n * LINE, text)
        for n, text in enumerate(v for k, v in meta.items() if k.startswith("Notes")):
            pdf.text(x(ACTION), 672 + n * LINE, text)
    for number, page in enumerate(pages, 1):
        pdf.add_page()
        if number > 1:
            pdf.text(x(RIGHT), TOP - 3 * LINE, f"{number}.")
        for n, row in enumerate(page.rows):
            if row is not None:
                pdf.text(x(row[0]), TOP + n * LINE, row[1])
        if page.footer:
            pdf.text(x(TRANSITION), TOP + (BODY_LINES + 1) * LINE, page.footer)
    return bytes(pdf.output())


def build(name: str) -> bytes:
    meta, blocks = parse_source((SAMPLES / f"{name}.fountain").read_text(encoding="utf-8"))
    return render(meta, paginate(blocks, OPTIONS[name]))


def speakers(screenplay: Screenplay) -> list[str]:
    """Every distinct cue name, in order of first appearance."""
    cues = (e.cue for s in screenplay.scenes for e in s.elements if isinstance(e, Dialogue))
    return list(dict.fromkeys(cues))


def main() -> int:
    for name in OPTIONS:
        data = build(name)
        (SAMPLES / f"{name}.pdf").write_bytes(data)
        screenplay = parse_pdf(data)
        elements = [e for s in screenplay.scenes for e in s.elements]
        speeches = sum(isinstance(e, Dialogue) for e in elements)
        print(
            f"{name}: {screenplay.page_count} pages (incl. title), "
            f"{len(screenplay.scenes)} scenes, {len(elements) - speeches} action + "
            f"{speeches} dialogue elements, speakers: {', '.join(speakers(screenplay))}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
