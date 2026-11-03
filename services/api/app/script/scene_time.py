"""What time of day a scene is shot at, when its heading only borrows one.

Ported from FrameFlow's scene_time.py. A heading's time is often relative -- CONTINUOUS, LATER,
SAME -- meaning "whatever the last scene was". A reader carries the clock forward; every
generative step has to be told, or it invents one (FrameFlow once drew an overcast afternoon in
the middle of a night chase). No clock upstream means None: a wrong clock is worse than none.
"""

from collections.abc import Sequence

from app.script.model import Scene

ABSOLUTE_TIMES = frozenset(
    {
        "DAY",
        "NIGHT",
        "DAWN",
        "DUSK",
        "MORNING",
        "AFTERNOON",
        "EVENING",
        "MIDNIGHT",
        "SUNRISE",
        "SUNSET",
        "MAGIC HOUR",
    }
)
RELATIVE_TIMES = frozenset(
    {
        "CONTINUOUS",
        "CONT'D",
        "CONTINUED",
        "LATER",
        "SAME",
        "SAME TIME",
        "MOMENTS LATER",
        "SECONDS LATER",
        "A MOMENT LATER",
    }
)


def absolute_time(value: str | None) -> str | None:
    """The absolute clock in a time-of-day field, or None if it only borrows one."""
    cleaned = (value or "").strip().upper()
    return cleaned if cleaned in ABSOLUTE_TIMES else None


def resolve_times(scenes: Sequence[Scene]) -> list[str | None]:
    """One clock per scene: its own, else the nearest earlier scene's, else None."""
    resolved: list[str | None] = []
    clock: str | None = None
    for scene in scenes:
        clock = absolute_time(scene.time_of_day) or clock
        resolved.append(clock)
    return resolved
