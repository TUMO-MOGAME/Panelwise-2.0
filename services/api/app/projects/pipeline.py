"""The pipeline core: PDF bytes -> parsed script -> grounded extraction -> shot plan.

docs/design/web.md §3 (stages, progress bands), §4.1 (failure copy), §6 (the contract). No
database: T046 runs this as a job and writes what `on_advance` reports, one transaction per call,
so a page never sees a stage's column without the job's advance. T026 adds the rendering stage.

Every failure the user can cause, or that a model call can, leaves as a `PipelineError` carrying
the copy the job row shows. The copy is chosen by `ScriptParseError.code`, the exception's type
and its `scene`, never by its message: a message is for the log (it stays on `__cause__`).
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.grounding import Extraction, ExtractionError, chunk_scenes, extract
from app.llm import NebiusChatModel
from app.script import ParseErrorCode, Screenplay, ScriptParseError, parse_pdf
from app.shots import ShotError, ShotPlan, plan_shots


class Stage(StrEnum):
    PARSING = "parsing"
    EXTRACTING = "extracting"
    PLANNING = "planning"
    RENDERING = "rendering"


# web.md §3: progress is 0-100 over the whole job; a stage reports its band's start as it begins.
BANDS: Mapping[Stage, tuple[int, int]] = MappingProxyType(
    {
        Stage.PARSING: (0, 5),
        Stage.EXTRACTING: (5, 40),
        Stage.PLANNING: (40, 60),
        Stage.RENDERING: (60, 100),
    }
)

type StageResult = Screenplay | Extraction | ShotPlan
type OnAdvance = Callable[[Stage, int, StageResult | None], Awaitable[None]]

# web.md §4.1, verbatim. A test holds each one to the doc.
NOT_A_PDF = (
    "This file couldn't be opened as a PDF. Export the script from your screenwriting app as a "
    "PDF and upload that."
)
NO_TEXT_LAYER = (
    "This PDF has no text layer. It looks like a scan. Export the script from your screenwriting "
    "app as a PDF and upload that."
)
NO_HEADINGS = (
    "No scene headings found. Panelwise reads screenplays formatted with headings like INT. "
    "KITCHEN - NIGHT."
)
TOO_LONG = "This script is longer than this demo reads. Upload a shorter one."
READ_FAILED = (
    "Reading the script failed at scene {n}. Nothing was saved from this run. Upload the script "
    "again to retry."
)
UNEXPECTED = "Something went wrong on our side while reading this script. Upload it again to retry."

_PARSE_COPY: Mapping[ParseErrorCode, str] = MappingProxyType(
    {"not_a_pdf": NOT_A_PDF, "no_text_layer": NO_TEXT_LAYER, "no_headings": NO_HEADINGS}
)


@dataclass(frozen=True)
class PipelineResult:
    screenplay: Screenplay
    extraction: Extraction
    plan: ShotPlan


class PipelineError(RuntimeError):
    """A stage failed. `message` is web.md §4.1's copy for it, verbatim: what the user reads."""

    def __init__(self, stage: Stage, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message


async def run_pipeline(
    pdf: bytes,
    model: NebiusChatModel,
    *,
    on_advance: OnAdvance,
    chunk_chars: int = 12_000,
    max_chunks: int = 40,
) -> PipelineResult:
    """Parse, extract and plan, awaiting `on_advance(stage, progress, finished)` as each stage
    begins -- with its band's start and the result of the stage before it -- and starts the
    stage only once the hook has returned."""
    await on_advance(Stage.PARSING, BANDS[Stage.PARSING][0], None)
    try:
        # pdfplumber is synchronous and CPU-bound; keep the event loop free for other requests.
        screenplay = await asyncio.to_thread(parse_pdf, pdf)
    except ScriptParseError as exc:
        raise PipelineError(Stage.PARSING, _PARSE_COPY[exc.code]) from exc

    await on_advance(Stage.EXTRACTING, BANDS[Stage.EXTRACTING][0], screenplay)
    # Checked here, not left to extract(), so an over-long script is told apart from a failed
    # call -- and it is refused before anything is billed.
    if len(chunk_scenes(screenplay, chunk_chars)) > max_chunks:
        raise PipelineError(Stage.EXTRACTING, TOO_LONG)
    try:
        extraction = await extract(
            model, screenplay, chunk_chars=chunk_chars, max_chunks=max_chunks
        )
    except ExtractionError as exc:
        copy = TOO_LONG if exc.scene is None else READ_FAILED.format(n=exc.scene)
        raise PipelineError(Stage.EXTRACTING, copy) from exc

    await on_advance(Stage.PLANNING, BANDS[Stage.PLANNING][0], extraction)
    try:
        plan = await plan_shots(model, screenplay, extraction)
    except ShotError as exc:
        raise PipelineError(Stage.PLANNING, READ_FAILED.format(n=exc.scene)) from exc

    return PipelineResult(screenplay=screenplay, extraction=extraction, plan=plan)
