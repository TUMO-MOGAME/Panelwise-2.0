"""What a shot plan is. docs/design/shots.md §3."""

from dataclasses import dataclass
from enum import StrEnum

from app.llm import Usage
from app.script import Span


class Framing(StrEnum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    OVER_SHOULDER = "over_shoulder"
    POV = "pov"
    INSERT = "insert"


class Movement(StrEnum):
    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRACKING = "tracking"
    HANDHELD = "handheld"
    CRANE = "crane"


class ShotError(RuntimeError):
    """A scene couldn't be planned; no partial plan is returned. `scene` is its number, as the
    script prints it (web.md §4.1 names it)."""

    def __init__(self, message: str, *, scene: str) -> None:
        super().__init__(message)
        self.scene = scene


@dataclass(frozen=True)
class Shot:
    """One storyboard frame or comic panel. `source` is the verbatim text it cites."""

    scene_index: int
    number: int
    framing: Framing
    movement: Movement
    elements: tuple[int, ...]
    characters: tuple[str, ...]
    props: tuple[str, ...]
    time_of_day: str | None
    rationale: str
    span: Span
    source: str


@dataclass(frozen=True)
class PlanReport:
    scenes: int
    shots: int
    ranges_repaired: int
    characters_dropped: int
    props_dropped: int
    characters_added: int = 0  # T092; the default lets older stored plans load


@dataclass(frozen=True)
class ShotPlan:
    shots: tuple[Shot, ...]
    report: PlanReport
    models: tuple[str, ...]
    usage: Usage
