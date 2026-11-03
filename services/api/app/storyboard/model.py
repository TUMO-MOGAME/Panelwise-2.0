"""The storyboard's results (storyboard.md §3.3, §6 `model.py`): a frame per shot as the job left
it, the storyboard, and the document's blocks (T027)."""

from dataclasses import dataclass

from app.verify.model import Check, FrameState, Verdict

type Rect = tuple[int, int, int, int]  # x, y, w, h in page px


@dataclass(frozen=True)
class StoryboardFrame:
    shot: tuple[int, int]
    state: FrameState
    asset: str | None  # only for PASSED or WARNED
    prompt: str | None  # the last attempt's text, as sent
    seed: int | None
    attempts: int
    verdict: Verdict
    noted_checks: tuple[Check, ...]
    failure: str | None = None  # T027: "render" or "restart" for a FAILED frame, from its row


@dataclass(frozen=True)
class Storyboard:
    style: str
    width: int
    height: int
    frames: tuple[StoryboardFrame, ...]
    renders: int  # drawings made this run
    cached: int  # attempts answered from the store


@dataclass(frozen=True)
class SourceLine:
    """One printed line of a block's source (T103): a speaker line prints Bold; `of` is the speaker
    label of a speech's line, so a speech continued on the next page gets its speaker again."""

    text: str
    speaker: bool = False
    of: str | None = None


@dataclass(frozen=True)
class Block:
    shot: tuple[int, int]
    y: int
    frame_rect: Rect | None
    title: str
    span_label: str
    audit_line: str | None
    source_lines: tuple[SourceLine, ...]
    continued: bool


@dataclass(frozen=True)
class StoryboardPage:
    number: int
    scene_index: int
    blocks: tuple[Block, ...]


class StoryboardError(RuntimeError):
    """A shot's renderer failed (§4): the storyboard can't be finished. `shot` names it."""

    def __init__(self, message: str, *, shot: tuple[int, int]) -> None:
        super().__init__(message)
        self.shot = shot
