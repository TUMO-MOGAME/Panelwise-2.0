"""Screenplays, extractions, shots and a style for the prompt tests. Self-written text only."""

from collections.abc import Sequence
from typing import Any

from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.script import Screenplay, Span, parse_text
from app.shots import Framing, Movement, Shot
from app.storyboard import Style, StyleOrigin
from tests.script.conftest import Row, layout

SENTINEL_RATIONALE = "SENTINEL RATIONALE zebra carnival fireworks"

# Three words of style, so the budget arithmetic in the tests is easy to follow.
STYLE = Style(
    key="test",
    label="Test",
    description="A test style.",
    medium="storyboard sketch",
    finish="grayscale",
    emphasis=None,
    negative="",
    grayscale=True,
    default=True,
    origin=StyleOrigin.PUBLIC,
)


def screenplay_of(rows: Sequence[Row]) -> Screenplay:
    return parse_text(layout(rows), [])


def extraction_of(screenplay: Screenplay, characters: Sequence[tuple[str, str]] = ()) -> Extraction:
    """Grounded like the real thing: the given (name, quote) characters, plus every speaker the
    cues name (grounding.md's backfill)."""
    proposals = [
        ProposedEntity.model_validate({"kind": "character", "name": name, "quotes": [quote]})
        for name, quote in characters
    ]
    entities, report = ground(proposals, screenplay)
    return Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


def shot_of(screenplay: Screenplay, scene_index: int, elements: Sequence[int], **kw: Any) -> Shot:
    """A shot as the planner builds one: its span and source from exactly its elements."""
    scene = screenplay.scenes[scene_index]
    covered = [scene.elements[i] for i in elements]
    span = (
        Span(covered[0].span.page, covered[0].span.line_start, covered[-1].span.line_end)
        if covered
        else Span(scene.span.page, scene.span.line_start, scene.span.line_start)
    )
    return Shot(
        scene_index=scene_index,
        number=kw.get("number", 1),
        framing=kw.get("framing", Framing.MEDIUM),
        movement=kw.get("movement", Movement.STATIC),
        elements=tuple(elements),
        characters=tuple(kw.get("characters", ())),
        props=tuple(kw.get("props", ())),
        time_of_day=kw.get("time_of_day"),
        rationale=kw.get("rationale", SENTINEL_RATIONALE),
        span=span,
        source="\n".join(e.text for e in covered) if covered else scene.heading,
    )
