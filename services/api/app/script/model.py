"""What a parsed screenplay is. docs/design/script.md §3.

Every element carries the page and lines it came from: Non-negotiable I (every panel traces
back to a verbatim span) is only possible if the parser kept one.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class IntExt(StrEnum):
    INT = "INT"
    EXT = "EXT"
    INT_EXT = "INT/EXT"


type ParseErrorCode = Literal["not_a_pdf", "no_text_layer", "no_headings"]


class ScriptParseError(ValueError):
    """The input can't be read as a screenplay. Raised instead of returning an empty one.

    `code` says which way, one per raise, so a caller picks its copy by code and never by the
    message (web.md §4.1)."""

    def __init__(self, code: ParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ParseErrorCode = code


@dataclass(frozen=True)
class Span:
    """Where an element came from: `page` of its first line, and 1-based inclusive line numbers
    into `Screenplay.text`."""

    page: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class Action:
    text: str
    span: Span


@dataclass(frozen=True)
class Dialogue:
    cue: str
    extension: str | None
    parenthetical: str | None
    text: str
    span: Span


type Element = Action | Dialogue


@dataclass(frozen=True)
class Scene:
    index: int
    number: str
    heading: str
    int_ext: IntExt
    location: str
    time_of_day: str | None
    elements: tuple[Element, ...]
    span: Span


@dataclass(frozen=True)
class Screenplay:
    """`page_starts` is the 1-based first line of each page in `text`: `page_starts[0] == 1` and
    `len(page_starts) == page_count`, so a reader can break pages where the PDF did."""

    text: str
    page_count: int
    scenes: tuple[Scene, ...]
    page_starts: tuple[int, ...]
