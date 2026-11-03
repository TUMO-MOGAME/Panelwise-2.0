"""Grounded entity extraction. Design: docs/design/grounding.md."""

from app.grounding.extract import SYSTEM_PROMPT, chunk_scenes, extract, render_chunk
from app.grounding.filter import NOT_POSSESSED, SENTENCE_END, ground
from app.grounding.model import (
    Dropped,
    Entity,
    EntityKind,
    Extraction,
    ExtractionError,
    GroundingReport,
    Quote,
    Source,
)
from app.grounding.schema import ChunkEntities, ProposedEntity
from app.grounding.text import (
    build_cue_index,
    build_index,
    locate,
    locate_after_cue,
    locate_in,
    locate_quote,
    normalize_for_grounding,
)

__all__ = [
    "NOT_POSSESSED",
    "SENTENCE_END",
    "SYSTEM_PROMPT",
    "ChunkEntities",
    "Dropped",
    "Entity",
    "EntityKind",
    "Extraction",
    "ExtractionError",
    "GroundingReport",
    "ProposedEntity",
    "Quote",
    "Source",
    "build_cue_index",
    "build_index",
    "chunk_scenes",
    "extract",
    "ground",
    "locate",
    "locate_after_cue",
    "locate_in",
    "locate_quote",
    "normalize_for_grounding",
    "render_chunk",
]
