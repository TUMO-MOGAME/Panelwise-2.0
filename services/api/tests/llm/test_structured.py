"""structured_chat -- docs/design/llm.md §4 and §6. No network: httpx2.MockTransport."""

import json
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, ValidationError

from app.llm import NebiusChatModel, Tier, structured_chat

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "reasoning-model", Tier.VISION: "v"}


class Character(BaseModel):
    name: str
    evidence: str


class Scene(BaseModel):
    characters: list[Character]
    location: str


VALID = {"characters": [{"name": "NANDI", "evidence": "NANDI pours tea."}], "location": "KITCHEN"}


def answer(content: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "model": "fast-model",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


class Recorder:
    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        return answer(self.contents.pop(0))


def make(rec: Recorder) -> NebiusChatModel:
    async def no_sleep(_: float) -> None:
        return None

    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(rec),
        sleep=no_sleep,
    )


async def test_valid_first_answer_returns_the_object_unrepaired() -> None:
    rec = Recorder(json.dumps(VALID))
    result = await structured_chat(make(rec), [{"role": "user", "content": "scene"}], Scene)

    assert result.value == Scene.model_validate(VALID)
    assert result.repaired is False
    assert result.chat.model == "fast-model"
    assert len(rec.bodies) == 1


async def test_request_uses_strict_json_schema_named_after_the_model() -> None:
    rec = Recorder(json.dumps(VALID))
    await structured_chat(make(rec), [{"role": "user", "content": "scene"}], Scene)

    assert rec.bodies[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "Scene", "schema": Scene.model_json_schema(), "strict": True},
    }


async def test_schema_is_appended_to_the_existing_system_message_not_a_second_one() -> None:
    rec = Recorder(json.dumps(VALID))
    messages = [
        {"role": "system", "content": "Extract only what the scene states."},
        {"role": "user", "content": "scene"},
    ]
    await structured_chat(make(rec), messages, Scene)

    sent = rec.bodies[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert sent[0]["content"].startswith("Extract only what the scene states.")
    assert json.dumps(Scene.model_json_schema()) in sent[0]["content"]
    # The caller's list is left untouched.
    assert messages[0]["content"] == "Extract only what the scene states."


async def test_without_a_system_message_one_is_added_first() -> None:
    rec = Recorder(json.dumps(VALID))
    await structured_chat(make(rec), [{"role": "user", "content": "scene"}], Scene)

    sent = rec.bodies[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert json.dumps(Scene.model_json_schema()) in sent[0]["content"]


async def test_invalid_then_valid_repairs_with_the_specified_turns() -> None:
    bad = '{"characters": ["NANDI"], "location": "KITCHEN"}'
    rec = Recorder(bad, json.dumps(VALID))
    result = await structured_chat(make(rec), [{"role": "user", "content": "scene"}], Scene)

    assert result.repaired is True
    assert result.value == Scene.model_validate(VALID)
    repair = rec.bodies[1]["messages"]
    assert repair[:-2] == rec.bodies[0]["messages"]
    assert repair[-2] == {"role": "assistant", "content": bad}
    assert repair[-1]["role"] == "user"
    assert "only the corrected JSON" in repair[-1]["content"]
    assert rec.bodies[1]["response_format"] == rec.bodies[0]["response_format"]


async def test_invalid_twice_raises_validation_error() -> None:
    rec = Recorder("not json", '{"location": 3}')

    with pytest.raises(ValidationError):
        await structured_chat(make(rec), [{"role": "user", "content": "scene"}], Scene)
    assert len(rec.bodies) == 2


async def test_two_repair_attempts_can_both_be_used_and_still_report_repaired() -> None:
    rec = Recorder("not json", '{"location": 3}', json.dumps(VALID))
    result = await structured_chat(
        make(rec), [{"role": "user", "content": "s"}], Scene, max_repair_attempts=2
    )

    assert result.repaired is True
    assert len(rec.bodies) == 3
    assert len(rec.bodies[2]["messages"]) == len(rec.bodies[0]["messages"]) + 4


async def test_a_system_message_made_of_parts_gets_the_schema_as_another_part() -> None:
    rec = Recorder(json.dumps(VALID))
    system = {"role": "system", "content": [{"type": "text", "text": "Be literal."}]}
    await structured_chat(make(rec), [system, {"role": "user", "content": "s"}], Scene)

    sent = rec.bodies[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert sent[0]["content"][0] == {"type": "text", "text": "Be literal."}
    assert json.dumps(Scene.model_json_schema()) in sent[0]["content"][1]["text"]
    assert len(system["content"]) == 1  # the caller's message is left untouched


async def test_no_repair_attempts_raises_on_the_first_invalid_answer() -> None:
    rec = Recorder("not json")

    with pytest.raises(ValidationError):
        await structured_chat(
            make(rec), [{"role": "user", "content": "s"}], Scene, max_repair_attempts=0
        )
    assert len(rec.bodies) == 1


async def test_tier_and_call_options_are_passed_through() -> None:
    rec = Recorder(json.dumps(VALID))
    await structured_chat(
        make(rec),
        [{"role": "user", "content": "s"}],
        Scene,
        Tier.REASONING,
        thinking=False,
        temperature=0.3,
        max_tokens=500,
    )

    body = rec.bodies[0]
    assert body["model"] == "reasoning-model"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert (body["temperature"], body["max_tokens"]) == (0.3, 500)


# --- T109: a grammar the decoder enforces but the prompt doesn't show (llm.md §6, §9) -----------


def capped() -> dict[str, Any]:
    schema = Scene.model_json_schema()
    schema["properties"]["characters"]["maxItems"] = 3
    return schema


async def test_grammar_goes_to_response_format_and_the_prompt_keeps_the_model_schema() -> None:
    rec = Recorder(json.dumps(VALID))
    await structured_chat(
        make(rec), [{"role": "system", "content": "Extract."}], Scene, grammar=capped()
    )

    body = rec.bodies[0]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "Scene", "schema": capped(), "strict": True},
    }
    prompt = body["messages"][0]["content"]
    assert json.dumps(Scene.model_json_schema()) in prompt
    assert "maxItems" not in prompt


async def test_a_repair_turn_sends_the_same_grammar() -> None:
    rec = Recorder("not json", json.dumps(VALID))
    result = await structured_chat(
        make(rec), [{"role": "user", "content": "s"}], Scene, grammar=capped()
    )

    assert result.repaired is True
    assert [b["response_format"]["json_schema"]["schema"] for b in rec.bodies] == [capped()] * 2


async def test_without_a_grammar_the_body_is_today_s() -> None:
    plain, none = Recorder(json.dumps(VALID)), Recorder(json.dumps(VALID))
    await structured_chat(make(plain), [{"role": "user", "content": "s"}], Scene)
    await structured_chat(make(none), [{"role": "user", "content": "s"}], Scene, grammar=None)

    assert plain.bodies == none.bodies
    assert plain.bodies[0]["response_format"]["json_schema"]["schema"] == Scene.model_json_schema()
