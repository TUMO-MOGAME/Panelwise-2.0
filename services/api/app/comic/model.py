"""What a comic book is. docs/design/comic.md §3, §6.

Every lettered piece of text carries the `Span` it came from: Non-negotiable I (every panel
traces back to a verbatim span) holds for the words on the page as much as for the art.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.script import Span
from app.verify.model import HeadSeen, Position

type Rect = tuple[int, int, int, int]  # x, y, w, h (page px)
type Point = tuple[int, int]  # x, y (page px)


class BubbleKind(StrEnum):
    SPEECH = "speech"
    OFF_PANEL = "off_panel"


class CaptionKind(StrEnum):
    SCENE = "scene"
    VOICE_OVER = "voice_over"


class Voice(StrEnum):
    """T117: the balloon's shape, from the script's own words (comic.md §3)."""

    PLAIN = "plain"
    THOUGHT = "thought"
    WHISPER = "whisper"
    SHOUT = "shout"
    DISTRESS = "distress"
    RADIO = "radio"


class ComicError(RuntimeError):
    """The comic can't be laid out or lettered without cutting script text; no partial book.
    `shot` is the (scene_index, shot_number) it names, when it names one: the comic job's failure
    copy names that shot (comic.md §4a, SPEC US3)."""

    def __init__(self, message: str, *, shot: tuple[int, int] | None = None) -> None:
        super().__init__(message)
        self.shot = shot


@dataclass(frozen=True)
class Bubble:
    """One `Dialogue` element, lettered verbatim. `element` indexes `scene.elements`."""

    kind: BubbleKind
    speaker: str
    text: str
    element: int
    span: Span
    rect: Rect
    tail: Point | None
    font_px: int
    voice: Voice = Voice.PLAIN  # T117
    linked: bool = False  # T118: joined to the bubble before it by a connector; tail None


@dataclass(frozen=True)
class Caption:
    """A scene caption (`element` None, span the heading) or a voice-over line."""

    kind: CaptionKind
    text: str
    element: int | None
    span: Span
    rect: Rect
    font_px: int
    voice: Voice = Voice.PLAIN  # T117: PLAIN, or RADIO for a broadcast voice-over


@dataclass(frozen=True)
class Panel:
    """One shot, named by `(scene_index, shot_number)`; its frame is rendered at `rect`'s size."""

    scene_index: int
    shot_number: int
    rect: Rect
    bubbles: tuple[Bubble, ...]
    captions: tuple[Caption, ...]


@dataclass(frozen=True)
class Page:
    number: int
    width: int
    height: int
    panels: tuple[Panel, ...]


@dataclass(frozen=True)
class LayoutReport:
    panels: int
    bubbles: int
    captions: int
    relayouts: int


@dataclass(frozen=True)
class ComicBook:
    pages: tuple[Page, ...]
    report: LayoutReport


@dataclass(frozen=True)
class WithheldCard:
    """What a withheld panel's card letters (comic.md §4 step 6): the failed checks and the span;
    `failed` for a panel whose renderer raised (T067), which has no checks."""

    checks: str
    span: Span
    failed: bool = False


@dataclass(frozen=True)
class PanelFrame:
    """A panel's frame, rendered at its rect's size. A withheld one is shown only as its card:
    `png` is never decoded when `withheld`, whatever it holds."""

    png: bytes
    positions: Mapping[str, Position]
    withheld: bool
    card: WithheldCard | None = None
    heads: tuple[HeadSeen, ...] = ()  # T098: the accepted audit's head boxes (T097); () on a card

    def __post_init__(self) -> None:
        if self.withheld != (self.card is not None):
            raise ComicError("a PanelFrame carries a withheld card exactly when it is withheld")
