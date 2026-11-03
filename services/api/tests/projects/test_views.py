"""The view builders: web.md §6 (`app/projects/views.py`), §4.2, §4.3.

Pure: no network, no database."""

from collections.abc import Sequence

import pytest

from app.grounding import EntityKind, Extraction, ProposedEntity, ground
from app.llm import Usage
from app.projects.views import (
    entity_views,
    lines_view,
    report_view,
    scene_views,
    shot_id,
    shot_views,
)
from app.script import Dialogue, Scene, Screenplay, Span, parse_pdf, parse_text
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from tests.script.conftest import ACTION, heading, layout, two_page_text
from tools.build_samples import OPTIONS, SAMPLES

SAMPLE_NAMES = sorted(OPTIONS)


@pytest.fixture
def screenplay() -> Screenplay:
    text, breaks = two_page_text()
    return parse_text(text, breaks)


def extraction_for(screenplay: Screenplay, *proposals: dict[str, object]) -> Extraction:
    entities, report = ground([ProposedEntity.model_validate(p) for p in proposals], screenplay)
    return Extraction(entities, report, ("extract-model",), Usage(100, 20, 0))


def shot(
    scene: Scene,
    number: int,
    first: int,
    last: int,
    characters: Sequence[str] = (),
    props: Sequence[str] = (),
) -> Shot:
    covered = scene.elements[first : last + 1]
    return Shot(
        scene_index=scene.index,
        number=number,
        framing=Framing.MEDIUM,
        movement=Movement.STATIC,
        elements=tuple(range(first, last + 1)),
        characters=tuple(characters),
        props=tuple(props),
        time_of_day="NIGHT",
        rationale="Covers the beat.",
        span=Span(covered[0].span.page, covered[0].span.line_start, covered[-1].span.line_end),
        source="\n".join(e.text for e in covered),
    )


def plan_of(*shots: Shot, models: tuple[str, ...] = ("plan-model",)) -> ShotPlan:
    return ShotPlan(shots, PlanReport(0, len(shots), 0, 0, 0), models, Usage(50, 10, 0))


@pytest.fixture
def plan(screenplay: Screenplay) -> ShotPlan:
    kitchen, gallery, stairwell = screenplay.scenes
    return plan_of(
        shot(kitchen, 1, 0, 1, characters=["NANDI"]),
        # THABO speaks off screen (O.S.) while the shot holds on NANDI.
        shot(kitchen, 2, 2, 3, characters=["NANDI"]),
        shot(gallery, 1, 0, 3, characters=["THABO"], props=["torn map"]),
        shot(stairwell, 1, 0, 0),
    )


# --- lines ---------------------------------------------------------------------------


def test_lines_are_the_text_split_on_newlines_with_page_starts(screenplay: Screenplay) -> None:
    view = lines_view(screenplay)
    assert view.lines == screenplay.text.split("\n")
    assert view.page_starts == list(screenplay.page_starts)
    assert view.page_starts[0] == 1


# --- scenes --------------------------------------------------------------------------


def test_scenes_carry_resolved_time_counts_and_whether_the_time_was_carried(
    screenplay: Screenplay, plan: ShotPlan
) -> None:
    views = scene_views(screenplay, plan)
    assert [(v.index, v.number, v.heading) for v in views] == [
        (0, "1", "INT. LIGHTHOUSE KITCHEN - NIGHT"),
        (1, "2", "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS"),
        (2, "3", "INT. LIGHTHOUSE STAIRWELL"),
    ]
    assert [(v.time_of_day, v.time_carried) for v in views] == [
        ("NIGHT", False),  # its own heading says NIGHT
        ("NIGHT", True),  # CONTINUOUS borrows it
        ("NIGHT", True),  # no time at all: carried from the scene before
    ]
    assert [v.elements for v in views] == [4, 4, 1]
    assert [v.shots for v in views] == [2, 1, 1]


def test_shots_are_null_until_planning_ends(screenplay: Screenplay) -> None:
    assert [v.shots for v in scene_views(screenplay, None)] == [None, None, None]


def test_a_scene_with_no_clock_anywhere_is_not_carried() -> None:
    text = layout(
        [
            heading("1", "INT. ROOM"),
            None,
            (ACTION, "Quiet."),
            None,
            heading("2", "EXT. YARD - DAY"),
            None,
            (ACTION, "Sun."),
        ]
    )
    views = scene_views(parse_text(text), None)
    assert [(v.time_of_day, v.time_carried) for v in views] == [(None, False), ("DAY", False)]


# --- entities --------------------------------------------------------------------------


def test_entities_keep_kind_source_scene_indexes_and_every_located_quote(
    screenplay: Screenplay,
) -> None:
    extraction = extraction_for(
        screenplay,
        {"kind": "prop", "name": "torn map", "quotes": ["a torn map"]},
        # Not in the script: dropped by grounding, so never listed.
        {"kind": "prop", "name": "lantern", "quotes": ["a brass lantern"]},
    )
    views = entity_views(extraction)

    assert [(v.kind, v.name, v.source) for v in views] == [
        (e.kind.value, e.name, e.source.value) for e in extraction.entities
    ]
    assert "lantern" not in {v.name for v in views}
    assert extraction.report.dropped  # the lantern is counted in the report instead
    by_name = {v.name: v for v in views}
    assert by_name["torn map"].scenes == [1]
    assert by_name["torn map"].source == "model"
    assert by_name["THABO"].source == "cue"
    assert by_name["LIGHTHOUSE KITCHEN"].kind == "location"
    assert by_name["LIGHTHOUSE KITCHEN"].source == "heading"
    quote = by_name["torn map"].quotes[0]
    assert quote.text == "a torn map"
    assert (quote.span.page, quote.span.line_start, quote.span.line_end) == (1, 24, 24)


def test_every_quote_is_on_the_lines_its_span_names(screenplay: Screenplay) -> None:
    lines = screenplay.text.split("\n")
    extraction = extraction_for(
        screenplay, {"kind": "prop", "name": "torn map", "quotes": ["a torn map"]}
    )
    for view in entity_views(extraction):
        for quote in view.quotes:
            source = " ".join(
                line.strip() for line in lines[quote.span.line_start - 1 : quote.span.line_end]
            )
            assert quote.text.upper() in source.upper()


# --- report ----------------------------------------------------------------------------


def test_the_report_is_grounding_s_plus_the_run_s_models_and_tokens(
    screenplay: Screenplay, plan: ShotPlan
) -> None:
    extraction = extraction_for(
        screenplay, {"kind": "prop", "name": "lantern", "quotes": ["a brass lantern"]}
    )
    r = extraction.report
    view = report_view(extraction, plan)

    assert (view.faithfulness, view.entities_proposed, view.entities_grounded) == (
        r.faithfulness,
        r.entities_proposed,
        r.entities_grounded,
    )
    assert (view.quotes_proposed, view.quotes_located) == (r.quotes_proposed, r.quotes_located)
    assert (view.recall, view.cues_total, view.cues_found_by_model) == (
        r.recall,
        r.cues_total,
        r.cues_found_by_model,
    )
    assert view.models == ["extract-model", "plan-model"]
    assert (view.prompt_tokens, view.completion_tokens) == (150, 30)


def test_before_planning_the_report_has_the_extraction_alone(screenplay: Screenplay) -> None:
    view = report_view(extraction_for(screenplay), None)
    assert view.models == ["extract-model"]
    assert (view.prompt_tokens, view.completion_tokens) == (100, 20)


def test_a_model_used_by_both_stages_is_listed_once(screenplay: Screenplay) -> None:
    view = report_view(extraction_for(screenplay), plan_of(models=("extract-model",)))
    assert view.models == ["extract-model"]


# --- shots -----------------------------------------------------------------------------


def test_shot_ids_are_scene_number_dot_shot_number(screenplay: Screenplay, plan: ShotPlan) -> None:
    assert [shot_id(screenplay, s) for s in plan.shots] == ["1.1", "1.2", "2.1", "3.1"]


def test_a_lettered_scene_number_stays_in_the_id() -> None:
    text = layout([heading("12A", "INT. ROOM - DAY"), None, (ACTION, "Quiet.")])
    screenplay = parse_text(text)
    assert shot_id(screenplay, shot(screenplay.scenes[0], 2, 0, 0)) == "12A.2"


def test_shot_views_mirror_the_plan_in_order(screenplay: Screenplay, plan: ShotPlan) -> None:
    views = shot_views(screenplay, extraction_for(screenplay), plan)

    assert [v.id for v in views] == ["1.1", "1.2", "2.1", "3.1"]
    for view, s in zip(views, plan.shots, strict=True):
        assert (view.scene_index, view.number) == (s.scene_index, s.number)
        assert (view.framing, view.movement) == (s.framing.value, s.movement.value)
        assert view.characters == list(s.characters)
        assert view.props == list(s.props)
        assert (view.time_of_day, view.rationale, view.source) == (
            s.time_of_day,
            s.rationale,
            s.source,
        )
        assert (view.span.page, view.span.line_start, view.span.line_end) == (
            s.span.page,
            s.span.line_start,
            s.span.line_end,
        )


def test_segments_are_one_per_covered_element_with_its_lines_and_cue(
    screenplay: Screenplay, plan: ShotPlan
) -> None:
    views = shot_views(screenplay, extraction_for(screenplay), plan)
    for view, s in zip(views, plan.shots, strict=True):
        scene = screenplay.scenes[s.scene_index]
        covered = [scene.elements[i] for i in s.elements]
        assert [(g.line_start, g.line_end) for g in view.segments] == [
            (e.span.line_start, e.span.line_end) for e in covered
        ]
        assert [g.cue for g in view.segments] == [
            e.cue if isinstance(e, Dialogue) else None for e in covered
        ]
        assert [g.extension for g in view.segments] == [
            e.extension if isinstance(e, Dialogue) else None for e in covered
        ]


def test_an_off_screen_speaker_s_dialogue_is_marked(screenplay: Screenplay, plan: ShotPlan) -> None:
    views = shot_views(screenplay, extraction_for(screenplay), plan)
    held_on_nandi = views[1]  # NANDI speaks, then THABO (O.S.)
    assert [(g.cue, g.extension, g.on_screen) for g in held_on_nandi.segments] == [
        ("NANDI", None, True),
        ("THABO", "O.S.", False),
    ]
    action = views[0]
    assert [g.on_screen for g in action.segments] == [True, True]
    gallery = views[2]  # THABO is in frame for all of his speech
    assert all(g.on_screen for g in gallery.segments)


def test_a_cue_matching_no_character_is_off_screen(screenplay: Screenplay) -> None:
    kitchen = screenplay.scenes[0]
    plan = plan_of(shot(kitchen, 1, 2, 3, characters=["NANDI", "THABO"]))
    # An extraction without THABO: his cue matches nobody, so it can't be shown as on screen.
    extraction = extraction_for(screenplay)
    extraction = Extraction(
        tuple(e for e in extraction.entities if e.name != "THABO"),
        extraction.report,
        extraction.models,
        extraction.usage,
    )
    view = shot_views(screenplay, extraction, plan)[0]
    assert [(g.cue, g.on_screen) for g in view.segments] == [("NANDI", True), ("THABO", False)]


def test_a_short_cue_matches_the_full_name_in_frame() -> None:
    text = layout(
        [
            heading("1", "INT. ROOM - DAY"),
            None,
            (ACTION, "THABO MOLEFE waits."),
            None,
            (32, "THABO"),
            (20, "Well?"),
        ]
    )
    screenplay = parse_text(text)
    extraction = extraction_for(
        screenplay, {"kind": "character", "name": "THABO MOLEFE", "quotes": ["THABO MOLEFE waits."]}
    )
    names = [e.name for e in extraction.entities if e.kind is EntityKind.CHARACTER]
    assert "THABO MOLEFE" in names
    plan = plan_of(shot(screenplay.scenes[0], 1, 0, 1, characters=["THABO MOLEFE"]))
    view = shot_views(screenplay, extraction, plan)[0]
    assert [(g.cue, g.on_screen) for g in view.segments] == [(None, True), ("THABO", True)]


def test_a_heading_only_shot_has_no_segments() -> None:
    text = layout([heading("1", "EXT. FIELD - DAY"), None, heading("2", "INT. BARN - DAY")])
    screenplay = parse_text(text)
    field = screenplay.scenes[0]
    establishing = Shot(
        field.index,
        1,
        Framing.WIDE,
        Movement.STATIC,
        (),
        (),
        (),
        "DAY",
        "Establishes the location.",
        Span(field.span.page, field.span.line_start, field.span.line_start),
        field.heading,
    )
    view = shot_views(screenplay, extraction_for(screenplay), plan_of(establishing))[0]
    assert view.segments == []
    assert view.source == "EXT. FIELD - DAY"


# --- the samples -----------------------------------------------------------------------


def sample_plan(screenplay: Screenplay, extraction: Extraction) -> ShotPlan:
    """One shot per element, every speaker of the scene in frame except in odd-numbered shots."""
    speakers = {
        e.name: set(e.scenes) for e in extraction.entities if e.kind is EntityKind.CHARACTER
    }
    shots: list[Shot] = []
    for scene in screenplay.scenes:
        cast = [name for name, scenes in speakers.items() if scene.index in scenes]
        for i in range(len(scene.elements)):
            shots.append(shot(scene, i + 1, i, i, characters=cast if i % 2 == 0 else ()))
    return plan_of(*shots)


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_every_builder_on_the_samples(name: str) -> None:
    screenplay = parse_pdf((SAMPLES / f"{name}.pdf").read_bytes())
    extraction = extraction_for(screenplay)
    plan = sample_plan(screenplay, extraction)
    lines = screenplay.text.split("\n")

    assert lines_view(screenplay).lines == lines
    scenes = scene_views(screenplay, plan)
    assert len(scenes) == len(screenplay.scenes)
    assert sum(s.shots or 0 for s in scenes) == len(plan.shots)
    assert {e.name for e in entity_views(extraction)} == {e.name for e in extraction.entities}
    assert report_view(extraction, plan).cues_total == extraction.report.cues_total

    views = shot_views(screenplay, extraction, plan)
    assert len({v.id for v in views}) == len(views)
    for view, s in zip(views, plan.shots, strict=True):
        element = screenplay.scenes[s.scene_index].elements[s.elements[0]]
        (segment,) = view.segments
        # Every segment is on the lines of the element it names: nothing unlocated is drawn.
        assert (segment.line_start, segment.line_end) == (
            element.span.line_start,
            element.span.line_end,
        )
        if isinstance(element, Dialogue):
            assert segment.on_screen == (s.number % 2 == 1)  # even index = odd number: in frame
        else:
            assert segment.on_screen
