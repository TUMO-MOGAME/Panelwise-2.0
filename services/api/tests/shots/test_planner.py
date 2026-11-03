"""plan_shots / render_scene: shots.md §3, §4, §9. MockTransport, no network."""

import json
from typing import Any

import httpx2
import pytest

from app.grounding import Extraction, GroundingReport, ProposedEntity, ground
from app.llm import NebiusChatModel, Tier, Usage
from app.script import Screenplay, parse_text
from app.shots import Framing, Movement, ShotError, plan_shots, render_scene
from tests.script.conftest import ACTION, heading, layout, two_page_text

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "r", Tier.VISION: "v"}


def extraction_for(screenplay: Screenplay) -> Extraction:
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {"kind": "character", "name": "NANDI", "quotes": ["NANDI (60s, oilskin coat)"]},
            {"kind": "character", "name": "THABO", "quotes": ["holding a torn map"]},
            {"kind": "prop", "name": "oilskin coat", "quotes": ["oilskin coat"]},
            {"kind": "prop", "name": "torn map", "quotes": ["a torn map"]},
        )
    ]
    entities, report = ground(proposals, screenplay)
    return Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


@pytest.fixture
def screenplay() -> Screenplay:
    text, breaks = two_page_text()
    return parse_text(text, breaks)


def shot(first: int, last: int, **kw: Any) -> dict[str, Any]:
    return {
        "first": first,
        "last": last,
        "framing": kw.get("framing", "medium"),
        "movement": kw.get("movement", "static"),
        "characters": kw.get("characters", []),
        "props": kw.get("props", []),
        "rationale": kw.get("rationale", "covers the beat"),
    }


class Scripted:
    """Answers per scene, recognised by its heading; records every request body."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.fail_on = fail_on

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        scene = body["messages"][-1]["content"]
        if self.fail_on and self.fail_on in scene:
            return httpx2.Response(400, json={"detail": "bad"})
        if "KITCHEN" in scene:
            shots = [
                shot(0, 1, framing="wide", characters=["NANDI"], props=["oilskin coat"]),
                # "MARIA" is not in the script; the torn map is not in this scene.
                shot(
                    2,
                    3,
                    framing="close_up",
                    characters=["Nandi", "THABO", "MARIA"],
                    props=["torn map"],
                ),
            ]
        elif "GALLERY" in scene:
            shots = [
                shot(0, 0, framing="wide", movement="tracking", characters=["THABO"]),
                shot(2, 3, characters=["THABO"], props=["torn map"]),
            ]  # gap at 1
        else:
            shots = [shot(5, 9)]  # out of bounds for a one-element scene
        return httpx2.Response(
            200,
            json={
                "model": "fast-model",
                "choices": [{"message": {"content": json.dumps({"shots": shots})}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )


def make(handler: Scripted) -> NebiusChatModel:
    async def no_sleep(_: float) -> None:
        return None

    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        sleep=no_sleep,
    )


async def test_one_fast_call_per_scene_with_thinking_off_and_strict_schema(
    screenplay: Screenplay,
) -> None:
    handler = Scripted()
    await plan_shots(make(handler), screenplay, extraction_for(screenplay))

    assert len(handler.bodies) == 3
    body = handler.bodies[0]
    assert body["model"] == "fast-model"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["json_schema"]["name"] == "ScenePlan"
    assert body["response_format"]["json_schema"]["strict"] is True


async def test_every_element_of_every_scene_is_in_exactly_one_shot(
    screenplay: Screenplay,
) -> None:
    plan = await plan_shots(make(Scripted()), screenplay, extraction_for(screenplay))

    for scene in screenplay.scenes:
        covered = [i for s in plan.shots if s.scene_index == scene.index for i in s.elements]
        assert covered == list(range(len(scene.elements)))
    numbers = [(s.scene_index, s.number) for s in plan.shots]
    assert numbers == [(0, 1), (0, 2), (1, 1), (1, 2), (2, 1)]
    assert plan.report.ranges_repaired == 2  # the gallery's gap, the stairwell's bounds


async def test_span_and_source_are_exactly_the_covered_elements(screenplay: Screenplay) -> None:
    plan = await plan_shots(make(Scripted()), screenplay, extraction_for(screenplay))
    first = plan.shots[0]
    elements = screenplay.scenes[0].elements

    assert first.elements == (0, 1)
    assert (first.span.line_start, first.span.line_end, first.span.page) == (
        elements[0].span.line_start,
        elements[1].span.line_end,
        1,
    )
    assert first.source == "\n".join(e.text for e in elements[:2])
    assert (first.framing, first.movement) == (Framing.WIDE, Movement.STATIC)


async def test_only_extracted_names_present_in_the_scene_survive(screenplay: Screenplay) -> None:
    plan = await plan_shots(make(Scripted()), screenplay, extraction_for(screenplay))
    close = plan.shots[1]

    assert close.characters == ("NANDI", "THABO")  # "Nandi" matched; "MARIA" dropped
    assert close.props == ()  # the torn map belongs to the gallery, not the kitchen
    assert plan.shots[3].props == ("torn map",)
    assert (plan.report.characters_dropped, plan.report.props_dropped) == (1, 1)


async def test_time_of_day_is_the_resolved_clock_never_the_models(
    screenplay: Screenplay,
) -> None:
    plan = await plan_shots(make(Scripted()), screenplay, extraction_for(screenplay))
    # Kitchen is NIGHT; the gallery is CONTINUOUS and the stairwell has none: both borrow NIGHT.
    assert [s.time_of_day for s in plan.shots] == ["NIGHT"] * 5


async def test_the_model_sees_numbered_elements_and_only_the_allowed_names(
    screenplay: Screenplay,
) -> None:
    handler = Scripted()
    await plan_shots(make(handler), screenplay, extraction_for(screenplay))
    kitchen = handler.bodies[0]["messages"][-1]["content"]

    assert "[0] Rain hammers the window." in kitchen
    assert "[2] NANDI (without turning): You came back." in kitchen
    assert "[3] THABO (O.S.): The boat didn't." in kitchen
    assert "Characters in this scene: NANDI, THABO" in kitchen
    assert "Props in this scene: oilskin coat" in kitchen
    assert "torn map" not in kitchen
    assert "Time of day: NIGHT" in kitchen
    assert "4 elements, [0] to [3]: no shot goes past [3], and at most 4 shots." in kitchen


def test_render_scene_without_names_or_time_says_so(screenplay: Screenplay) -> None:
    rendered = render_scene(screenplay.scenes[2], [], [], None)
    assert rendered.startswith("INT. LIGHTHOUSE STAIRWELL")
    assert "[0] Silence." in rendered
    assert "Characters in this scene: none" in rendered
    # The model padded a one-element scene with six shots over [0]-[14]; it's told the bounds.
    assert "1 element, [0] to [0]: no shot goes past [0], and at most 1 shot." in rendered
    assert "Time of day" not in rendered


async def test_a_scene_with_no_elements_gets_one_shot_without_a_call() -> None:
    rows = [
        heading("1", "EXT. HARBOUR - DAWN"),
        None,
        heading("2", "INT. SHED - DAWN"),
        None,
        (ACTION, "A lamp flickers."),
    ]
    screenplay = parse_text(layout(rows))
    handler = Scripted()
    plan = await plan_shots(make(handler), screenplay, extraction_for(screenplay))

    empty = plan.shots[0]
    assert (empty.elements, empty.framing, empty.movement) == ((), Framing.WIDE, Movement.STATIC)
    assert empty.source == "EXT. HARBOUR - DAWN"
    assert empty.span == screenplay.scenes[0].span.__class__(1, 1, 1)
    assert len(handler.bodies) == 1  # only the shed was asked about


async def test_a_failing_scene_fails_the_plan_and_names_it(screenplay: Screenplay) -> None:
    with pytest.raises(ShotError, match="scene 2") as caught:
        await plan_shots(make(Scripted(fail_on="GALLERY")), screenplay, extraction_for(screenplay))
    assert caught.value.scene == "2"


async def test_the_plan_reports_models_and_usage(screenplay: Screenplay) -> None:
    plan = await plan_shots(make(Scripted()), screenplay, extraction_for(screenplay))
    assert plan.models == ("fast-model",)
    assert (plan.usage.prompt_tokens, plan.usage.completion_tokens) == (150, 60)
    assert (plan.report.scenes, plan.report.shots) == (3, 5)


def test_grounding_report_type_is_what_extraction_carries() -> None:
    # Guard: the fixture builds a real grounded extraction, not a hand-made stand-in.
    text, breaks = two_page_text()
    ex = extraction_for(parse_text(text, breaks))
    assert isinstance(ex.report, GroundingReport)
    assert ex.report.faithfulness == 1.0
