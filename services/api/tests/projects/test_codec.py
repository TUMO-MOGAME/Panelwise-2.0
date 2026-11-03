"""codec: the stage columns' jsonb, lossless (web.md §3, §7; T046). load(dump(x)) == x."""

import json
from dataclasses import replace

import pytest

from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.projects.codec import (
    CodecError,
    dump_extraction,
    dump_plan,
    dump_screenplay,
    load_extraction,
    load_plan,
    load_screenplay,
)
from app.script import Screenplay, Span, parse_pdf
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from tools.build_samples import OPTIONS, SAMPLES


def sample(name: str) -> Screenplay:
    return parse_pdf((SAMPLES / f"{name}.pdf").read_bytes())


def extraction_of(screenplay: Screenplay) -> Extraction:
    first = screenplay.scenes[0].elements[0].text
    proposals = [
        ProposedEntity.model_validate(
            {"kind": "prop", "name": first.split()[1], "quotes": [first[:30]], "other_names": []}
        )
    ]
    entities, report = ground(proposals, screenplay)
    return Extraction(entities, report, ("fast-model",), Usage(10, 5, 0))


def plan_of(screenplay: Screenplay) -> ShotPlan:
    shots = tuple(
        Shot(s.index, i + 1, Framing.WIDE, Movement.PAN, (i,), ("A",), (), "NIGHT", "why",
             e.span, e.text)
        for s in screenplay.scenes for i, e in enumerate(s.elements)
    )  # fmt: skip
    return ShotPlan(
        shots, PlanReport(len(screenplay.scenes), len(shots), 1, 0, 2), ("m",), Usage(1, 2, 3)
    )


@pytest.mark.parametrize("name", sorted(OPTIONS))
def test_every_sample_round_trips_through_json(name: str) -> None:
    screenplay = sample(name)
    extraction, plan = extraction_of(screenplay), plan_of(screenplay)

    def stored(data: object) -> object:
        return json.loads(json.dumps(data))  # what jsonb hands back

    assert load_screenplay(stored(dump_screenplay(screenplay))) == screenplay
    assert load_extraction(stored(dump_extraction(extraction))) == extraction
    assert load_plan(stored(dump_plan(plan))) == plan


def test_the_dump_is_plain_json_with_readable_fields() -> None:
    screenplay = sample("the-red-kite")
    data = dump_screenplay(screenplay)
    assert data["page_count"] == screenplay.page_count
    assert len(data["scenes"]) == len(screenplay.scenes)
    assert {e["_t"] for s in data["scenes"] for e in s["elements"]} == {"Action", "Dialogue"}
    assert len(dump_plan(plan_of(screenplay))["shots"]) == sum(
        len(s.elements) for s in screenplay.scenes
    )


def test_optional_fields_and_enums_survive() -> None:
    screenplay = sample("sipho-and-siphokazi")  # a heading with no time: time_of_day None
    assert any(s.time_of_day is None for s in screenplay.scenes)
    assert load_screenplay(json.loads(json.dumps(dump_screenplay(screenplay)))) == screenplay


def test_a_wrong_shape_is_a_codec_error_not_a_crash() -> None:
    data = dump_screenplay(sample("the-red-kite"))
    data["scenes"][0]["elements"][0]["_t"] = "Explosion"
    with pytest.raises(CodecError):
        load_screenplay(data)
    with pytest.raises(CodecError):
        load_screenplay({"text": "x"})


def test_a_span_is_a_value_not_a_reference() -> None:
    plan = plan_of(sample("the-red-kite"))
    loaded = load_plan(json.loads(json.dumps(dump_plan(plan))))
    assert loaded.shots[0].span == plan.shots[0].span and isinstance(loaded.shots[0].span, Span)
    assert replace(loaded.shots[0], number=99) != plan.shots[0]
