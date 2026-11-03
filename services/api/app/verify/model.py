"""What a frame audit is. docs/design/verify.md §3, §6.

`RenderedFrame` and `Renderer` are the shapes T008's renderer provides: verify depends on them and
nothing more, so the audit runs on any PNG, rendered or not.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Protocol

from app.llm import Usage
from app.shots import Shot

if TYPE_CHECKING:
    from app.verify.schema import FrameDescription, Judgement


class Position(StrEnum):
    LEFT = "left"
    CENTRE = "centre"
    RIGHT = "right"


class Setting(StrEnum):
    INTERIOR = "interior"
    EXTERIOR = "exterior"
    UNCLEAR = "unclear"


class Light(StrEnum):
    DAY = "day"
    NIGHT = "night"
    DAWN_OR_DUSK = "dawn_or_dusk"
    UNCLEAR = "unclear"


class ShotSize(StrEnum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE = "close"
    EXTREME_CLOSE = "extreme_close"
    UNCLEAR = "unclear"


class ObjectKind(StrEnum):
    SCRIPTED_PROP = "scripted_prop"
    SET_DRESSING = "set_dressing"
    UNSCRIPTED = "unscripted"


class ObjectCategory(StrEnum):
    FURNITURE = "furniture"
    ARCHITECTURE = "architecture"
    NATURE = "nature"
    CLOTHING = "clothing"
    ANIMAL = "animal"
    VEHICLE = "vehicle"
    WEAPON = "weapon"
    SCREEN_OR_SIGN = "screen_or_sign"
    FOOD = "food"
    OTHER = "other"


class Check(StrEnum):
    UNSCRIPTED_PERSON = auto()
    UNSCRIPTED_OBJECT = auto()
    TEXT_IN_FRAME = auto()
    SETTING = auto()
    MISSING_CHARACTER = auto()
    LIGHT = auto()
    FRAMING = auto()
    SIGNATURE = auto()  # T077: soft
    NO_CHARACTER = auto()  # T080: hard
    BACKGROUND_OBJECT = auto()  # T083: soft
    DRAWN_SEX = auto()  # T095: hard
    SPLIT_PANELS = auto()  # T104: hard
    DRAWN_TWICE = auto()  # T104: hard


class Severity(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class Verdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"


class FrameState(StrEnum):
    RENDERING = auto()
    AUDITING = auto()
    PASSED = auto()
    WARNED = auto()
    WITHHELD = auto()
    FAILED = auto()


@dataclass(frozen=True)
class RenderedFrame:
    shot: tuple[int, int]
    attempt: int
    seed: int
    png: bytes
    width: int
    height: int
    prompt: str


class Renderer(Protocol):
    # width x height: the storyboard's 16:9 size, or a comic panel's rect (comic.md §4 step 6)
    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame: ...


class SupportsAsset(Protocol):
    @property
    def asset(self) -> str: ...  # the attempt's Storage path, frames/<...>.png; read-only


class RecordingRenderer(Renderer, Protocol):
    """A Renderer that remembers where it stored each attempt (T021): recorded before `render`
    returns, so a lookup after it never misses. The frame writers need the path."""

    def record(self, shot: tuple[int, int], attempt: int) -> SupportsAsset: ...


@dataclass(frozen=True)
class CheckResult:
    check: Check
    severity: Severity
    ok: bool
    detail: str


@dataclass(frozen=True)
class Audit:
    shot: tuple[int, int]
    attempt: int
    seed: int
    description: FrameDescription | None
    judgement: Judgement | None
    checks: tuple[CheckResult, ...]
    verdict: Verdict
    positions: dict[str, Position]
    models: tuple[str, ...]
    usage: Usage
    seen: tuple[PersonSeen, ...] = ()  # T095: the sex agent's answers
    found: tuple[PersonFound, ...] = ()  # T099: the presence agent's answers
    layout: FrameLayout | None = None  # T104: the layout agent's answer, cleaned
    matched: Mapping[int, str] = field(default_factory=dict[int, str])  # T097: matched_people, kept
    heads: tuple[HeadSeen, ...] = ()  # T097: the head agent's kept answers


@dataclass(frozen=True)
class FrameLayout:
    """The layout agent's answer, cleaned (T104): how many panels the frame is drawn as, and the
    pairs of described people who are the same person drawn twice, as sorted (a, b)."""

    panels: int
    copies: tuple[tuple[int, int], ...]
    reason: str


# x0, y0, x1, y1: fractions of the frame's width and height, from its top-left (T097)
type HeadBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class HeadSeen:
    """Where one described person's head is (T097): the person's index, the character they
    were accepted as (None for a person matched to no one), and the head's box."""

    person: int
    character: str | None
    box: HeadBox


@dataclass(frozen=True)
class PersonSeen:
    """The sex agent's answer about one matched person (T095): the described person's index,
    the character they were accepted as, and male, female or unclear."""

    person: int
    character: str
    sex: str


@dataclass(frozen=True)
class PersonFound:
    """The presence agent's answer about one drawn character (T099): the described person
    it is, or None, and why."""

    character: str
    person: int | None
    reason: str


@dataclass(frozen=True)
class FrameOutcome:
    shot: tuple[int, int]
    state: FrameState
    frame: RenderedFrame | None
    audits: tuple[Audit, ...]
