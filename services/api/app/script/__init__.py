"""Screenplay parsing with source spans. Design: docs/design/script.md."""

from app.script.model import (
    Action,
    Dialogue,
    Element,
    IntExt,
    ParseErrorCode,
    Scene,
    Screenplay,
    ScriptParseError,
    Span,
)
from app.script.parser import parse_pdf, parse_text
from app.script.scene_time import ABSOLUTE_TIMES, RELATIVE_TIMES, absolute_time, resolve_times
from app.script.speakers import match_speaker, normalise

__all__ = [
    "ABSOLUTE_TIMES",
    "RELATIVE_TIMES",
    "Action",
    "Dialogue",
    "Element",
    "IntExt",
    "ParseErrorCode",
    "Scene",
    "Screenplay",
    "ScriptParseError",
    "Span",
    "absolute_time",
    "match_speaker",
    "normalise",
    "parse_pdf",
    "parse_text",
    "resolve_times",
]
