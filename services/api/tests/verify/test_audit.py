"""describe_frame / audit_frame: verify.md §4, §9. MockTransport, no network."""

import base64
import json
from typing import Any

import httpx2
import pytest

from app.grounding import Extraction
from app.llm import NebiusChatModel, Tier
from app.script import Screenplay
from app.verify import Check, RenderedFrame, Verdict, audit_frame, describe_frame
from tests.verify.conftest import described, judged, kitchen_shot

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "judge-model", Tier.VISION: "vision-model"}
PNG = b"\x89PNG\r\n\x1a\nnot-really-a-frame"


def frame() -> RenderedFrame:
    return RenderedFrame((0, 1), 2, 1234, PNG, 1024, 576, "a woman pours tea")


def reply(model: str, content: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )


class Scripted:
    """The describer answers `description`, the judge `judgement`; every body is recorded."""

    def __init__(self, description: str, judgement: str, fail: str | None = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.answers = {"vision-model": description, "judge-model": judgement}
        self.fail = fail

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if body["model"] == self.fail:
            return httpx2.Response(400, json={"detail": "bad"})
        return reply(body["model"], self.answers[body["model"]])


def model_for(handler: Scripted) -> NebiusChatModel:
    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        max_attempts=1,
    )


async def test_the_describer_sees_the_image_and_nothing_about_the_shot() -> None:
    handler = Scripted(described().model_dump_json(), "")
    description, chat = await describe_frame(model_for(handler), PNG)

    assert description == described()
    assert chat.model == "vision-model"
    (body,) = handler.bodies
    assert body["model"] == "vision-model"
    sent = json.dumps(body)
    image = f"data:image/png;base64,{base64.b64encode(PNG).decode()}"
    assert image in sent
    for detail in ("NANDI", "oilskin", "pours tea", "LIGHTHOUSE", "KITCHEN", "mugs"):
        assert detail.lower() not in sent.lower(), detail


async def test_audit_describes_then_judges_with_the_spec(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(described().model_dump_json(), judged().model_dump_json())
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)

    assert [b["model"] for b in handler.bodies] == ["vision-model", "judge-model"]
    describer = json.dumps(handler.bodies[0])
    for detail in ("NANDI", "oilskin", "pours tea", "LIGHTHOUSE", "KITCHEN", "mugs"):
        assert detail.lower() not in describer.lower(), detail
    judge = json.dumps(handler.bodies[1])
    assert "image_url" not in judge
    assert base64.b64encode(PNG).decode() not in judge
    for detail in (
        "NANDI",
        "oilskin coat",
        "pours tea into two chipped mugs",
        "KITCHEN",
        "NIGHT",
        "older woman",
    ):
        assert detail in judge, detail
    assert handler.bodies[1]["chat_template_kwargs"] == {"enable_thinking": True}

    assert audit.verdict is Verdict.PASS
    assert (audit.shot, audit.attempt, audit.seed) == ((0, 1), 2, 1234)
    assert audit.description == described()
    assert audit.judgement == judged()
    assert audit.positions == {"NANDI": "left"}
    assert audit.models == ("vision-model", "judge-model")
    assert (audit.usage.prompt_tokens, audit.usage.completion_tokens) == (200, 40)
    assert {c.check for c in audit.checks} == set(Check)


async def test_an_unscripted_person_fails_the_frame(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    description = described(
        people=[
            {"position": "left", "appearance": "older woman"},
            {"position": "right", "appearance": "a soldier"},
        ]
    )
    judgement = judged(
        people=[
            {"person": 0, "character": "NANDI", "support": None},
            {"person": 1, "character": None, "support": "a soldier stands guard"},
        ]
    )
    handler = Scripted(description.model_dump_json(), judgement.model_dump_json())
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.FAIL
    assert [c.check for c in audit.checks if not c.ok] == [Check.UNSCRIPTED_PERSON]


@pytest.mark.parametrize("failing_model", ["vision-model", "judge-model"])
async def test_a_failed_model_call_is_an_error_never_a_pass(
    screenplay: Screenplay, extraction: Extraction, failing_model: str
) -> None:
    handler = Scripted(
        described().model_dump_json(), judged().model_dump_json(), fail=failing_model
    )
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.ERROR
    assert audit.checks == ()
    assert audit.positions == {}
    assert audit.judgement is None
    assert (audit.description is None) is (failing_model == "vision-model")


async def test_a_judgement_that_never_validates_is_an_error(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(described().model_dump_json(), '{"people": "nobody"}')
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.ERROR
    assert len(handler.bodies) == 3  # describe, judge, one repair
    assert audit.description == described()


async def test_a_judgement_that_skips_a_person_is_an_error(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted(described().model_dump_json(), judged(people=[]).model_dump_json())
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.ERROR
    assert audit.judgement == judged(people=[])


async def test_a_description_that_never_validates_is_an_error_and_nothing_is_judged(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    handler = Scripted('{"people": "a few"}', judged().model_dump_json())
    audit = await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    assert audit.verdict is Verdict.ERROR
    assert [b["model"] for b in handler.bodies] == ["vision-model", "vision-model"]  # + repair
    assert audit.description is None and audit.judgement is None


async def test_a_failed_call_logs_its_step_and_why_never_the_script(
    screenplay: Screenplay, extraction: Extraction, caplog: pytest.LogCaptureFixture
) -> None:
    # An empty reply from the describer: its step and the LLMError's own words (model, finish
    # reason), so a run's log tells budget-starved thinking from a model that said nothing.
    handler = Scripted("", judged().model_dump_json())
    with caplog.at_level("WARNING", logger="app.verify.audit"):
        audit = await audit_frame(
            model_for(handler), frame(), kitchen_shot(), screenplay, extraction
        )
    assert audit.verdict is Verdict.ERROR
    (record,) = [r for r in caplog.records if r.name == "app.verify.audit"]
    assert "attempt 2 failed at describe: vision-model returned no content" in record.getMessage()
    # A judgement that never validates: the judge step, its type only (it can quote the script).
    caplog.clear()
    handler = Scripted(described().model_dump_json(), '{"people": "nobody"}')
    with caplog.at_level("WARNING", logger="app.verify.audit"):
        await audit_frame(model_for(handler), frame(), kitchen_shot(), screenplay, extraction)
    (record,) = [r for r in caplog.records if r.name == "app.verify.audit"]
    assert record.getMessage().endswith("failed at judge: ValidationError")
    assert "nobody" not in record.getMessage()
