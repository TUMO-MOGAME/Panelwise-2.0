"""What the script and storyboard pages read: web.md §6 views, built from a project's stage results.

Pure: no database, no I/O. T047 loads the stage columns and calls these. Every view keeps the
spans it was given and adds nothing the parse, the grounded extraction or the plan doesn't hold:
dropped entities never appear, and a shot's segments are exactly the lines of its elements.
"""

from collections import Counter

from app.api.v1.schemas import (
    EntityView,
    LinesView,
    QuoteView,
    ReportView,
    SceneView,
    Segment,
    ShotView,
    SpanRef,
)
from app.grounding import EntityKind, Extraction
from app.script import (
    Dialogue,
    Element,
    Screenplay,
    Span,
    absolute_time,
    match_speaker,
    resolve_times,
)
from app.shots import Shot, ShotPlan


def _span(span: Span) -> SpanRef:
    return SpanRef(page=span.page, line_start=span.line_start, line_end=span.line_end)


def lines_view(screenplay: Screenplay) -> LinesView:
    return LinesView(lines=screenplay.text.split("\n"), page_starts=list(screenplay.page_starts))


def scene_views(screenplay: Screenplay, plan: ShotPlan | None) -> list[SceneView]:
    times = resolve_times(screenplay.scenes)
    shots = Counter(shot.scene_index for shot in plan.shots) if plan is not None else None
    return [
        SceneView(
            index=scene.index,
            number=scene.number,
            heading=scene.heading,
            time_of_day=times[scene.index],
            # Carried: the scene has a clock, but its own heading didn't give it.
            time_carried=times[scene.index] is not None
            and absolute_time(scene.time_of_day) is None,
            elements=len(scene.elements),
            shots=shots[scene.index] if shots is not None else None,
        )
        for scene in screenplay.scenes
    ]


def entity_views(extraction: Extraction) -> list[EntityView]:
    return [
        EntityView(
            kind=entity.kind,
            name=entity.name,
            source=entity.source,
            scenes=list(entity.scenes),
            quotes=[QuoteView(text=q.text, span=_span(q.span)) for q in entity.quotes],
        )
        for entity in extraction.entities
    ]


def report_view(extraction: Extraction, plan: ShotPlan | None) -> ReportView:
    r = extraction.report
    usages = [extraction.usage] + ([plan.usage] if plan is not None else [])
    models = extraction.models + (plan.models if plan is not None else ())
    return ReportView(
        faithfulness=r.faithfulness,
        entities_proposed=r.entities_proposed,
        entities_grounded=r.entities_grounded,
        quotes_proposed=r.quotes_proposed,
        quotes_located=r.quotes_located,
        recall=r.recall,
        cues_total=r.cues_total,
        cues_found_by_model=r.cues_found_by_model,
        models=list(dict.fromkeys(models)),
        prompt_tokens=sum(u.prompt_tokens for u in usages),
        completion_tokens=sum(u.completion_tokens for u in usages),
    )


def shot_id(screenplay: Screenplay, shot: Shot) -> str:
    return f"{screenplay.scenes[shot.scene_index].number}.{shot.number}"


def _segment(element: Element, shot: Shot, characters: list[str]) -> Segment:
    if not isinstance(element, Dialogue):
        return Segment(
            line_start=element.span.line_start,
            line_end=element.span.line_end,
            cue=None,
            extension=None,
            on_screen=True,
        )
    # A cue that matches no character, or matches one the shot doesn't show, is off screen: the
    # line is heard, not seen, so the lined script draws it wavy.
    speaker = match_speaker(element.cue, characters)
    return Segment(
        line_start=element.span.line_start,
        line_end=element.span.line_end,
        cue=element.cue,
        extension=element.extension,
        on_screen=speaker is not None and speaker in shot.characters,
    )


def shot_views(screenplay: Screenplay, extraction: Extraction, plan: ShotPlan) -> list[ShotView]:
    characters = [e.name for e in extraction.entities if e.kind is EntityKind.CHARACTER]
    views: list[ShotView] = []
    for shot in plan.shots:
        elements = screenplay.scenes[shot.scene_index].elements
        views.append(
            ShotView(
                id=shot_id(screenplay, shot),
                scene_index=shot.scene_index,
                number=shot.number,
                framing=shot.framing,
                movement=shot.movement,
                characters=list(shot.characters),
                props=list(shot.props),
                time_of_day=shot.time_of_day,
                rationale=shot.rationale,
                span=_span(shot.span),
                source=shot.source,
                segments=[_segment(elements[i], shot, characters) for i in shot.elements],
            )
        )
    return views
