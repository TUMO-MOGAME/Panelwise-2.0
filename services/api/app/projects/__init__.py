"""Projects: a screenplay upload and what the pipeline makes of it. Design: docs/design/web.md."""

from app.projects.pipeline import (
    BANDS,
    NO_HEADINGS,
    NO_TEXT_LAYER,
    NOT_A_PDF,
    READ_FAILED,
    TOO_LONG,
    UNEXPECTED,
    OnAdvance,
    PipelineError,
    PipelineResult,
    Stage,
    StageResult,
    run_pipeline,
)

__all__ = [
    "BANDS",
    "NOT_A_PDF",
    "NO_HEADINGS",
    "NO_TEXT_LAYER",
    "READ_FAILED",
    "TOO_LONG",
    "UNEXPECTED",
    "OnAdvance",
    "PipelineError",
    "PipelineResult",
    "Stage",
    "StageResult",
    "run_pipeline",
]
