"""What every renderer backend shares (storyboard.md §6 `render.py`): its error, the record it keeps
of each attempt, and the shape `build_storyboard` needs."""

from dataclasses import dataclass
from typing import Protocol

from app.storyboard.prompt import FramePrompt
from app.storyboard.styles import Style
from app.verify.model import RecordingRenderer

# storyboard.md §6, verbatim: the upload's job, failed at stage rendering when the renderer looks
# down (§4 Failure paths; T066). One frame failing on its own is not a job failure.
RENDER_STAGE_FAILED = (
    "No frame could be drawn, so the storyboard stopped. Try again in a few minutes by uploading "
    "the script again."
)


class RendererError(RuntimeError):
    """A drawing couldn't be made: the backend refused, failed or timed out. Its message names the
    status and model, never a key or a prompt."""


@dataclass(frozen=True)
class RenderRecord:
    """One attempt as the renderer stored it (§3.3): `asset` is its Storage path."""

    shot: tuple[int, int]
    attempt: int
    key: str
    asset: str
    prompt: FramePrompt
    cached: bool
    seconds: float | None


class RenderRecorder(RecordingRenderer, Protocol):
    """A RecordingRenderer whose records are RenderRecords, in one style: build_storyboard's."""

    style: Style

    def record(self, shot: tuple[int, int], attempt: int) -> RenderRecord: ...
