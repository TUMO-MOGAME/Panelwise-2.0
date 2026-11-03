"""NebiusChatModel -- docs/design/llm.md §4 and §6. No network: httpx2.MockTransport."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.core.config import Settings
from app.llm import (
    LLMConfigError,
    LLMEmptyResponse,
    LLMRequestError,
    NebiusChatModel,
    Tier,
)

KEY = "nb-secret-key-do-not-leak"
MODELS = {
    Tier.FAST: "nvidia/Nemotron-3_5-Lightning",
    Tier.REASONING: "nvidia/nemotron-3-super-120b-a12b",
    Tier.VISION: "zai-org/GLM-5.3-Flash",
}
HI = [{"role": "user", "content": "hi"}]

type Handler = Callable[[httpx2.Request], httpx2.Response]


def completion(
    content: str | None = "ok",
    *,
    model: str = "nvidia/Nemotron-3_5-Lightning",
    reasoning: str | None = None,
    usage: dict[str, Any] | None = None,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": usage or {"prompt_tokens": 5, "completion_tokens": 2},
    }


class Recorder:
    """A transport that answers from a script and remembers every request."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def body(self, i: int = 0) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[i].content)
        return body


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make(
    rec: Recorder, sleeps: Sleeps | None = None, models: dict[Tier, str] | None = None
) -> NebiusChatModel:
    return NebiusChatModel(
        api_key=KEY,
        base_url="https://api.tokenfactory.nebius.com/v1",
        models=MODELS if models is None else models,
        transport=httpx2.MockTransport(rec),
        sleep=sleeps or Sleeps(),
    )


def ok(body: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None):
    return httpx2.Response(status, json=body, headers=headers)


# --- the request ------------------------------------------------------------------


async def test_fast_tier_sends_exactly_the_contracted_body_with_thinking_off() -> None:
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI)

    req = rec.requests[0]
    assert req.url == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert rec.body() == {
        "model": MODELS[Tier.FAST],
        "messages": HI,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }


async def test_reasoning_tier_defaults_to_thinking_on() -> None:
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI, Tier.REASONING)

    assert rec.body()["model"] == MODELS[Tier.REASONING]
    assert rec.body()["chat_template_kwargs"] == {"enable_thinking": True}


async def test_vision_tier_sends_no_thinking_toggle_by_default() -> None:
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI, Tier.VISION)

    assert rec.body()["model"] == MODELS[Tier.VISION]
    assert "chat_template_kwargs" not in rec.body()


# T105 (vision-model.md §6): the vision tier's thinking toggle is a setting, unset by default.


def make_vision(rec: Recorder, vision_thinking: bool | None) -> NebiusChatModel:
    return NebiusChatModel(
        api_key=KEY,
        base_url="https://api.tokenfactory.nebius.com/v1",
        models=MODELS,
        transport=httpx2.MockTransport(rec),
        sleep=Sleeps(),
        vision_thinking=vision_thinking,
    )


@pytest.mark.parametrize("think", [False, True])
async def test_vision_thinking_is_sent_on_every_vision_call(think: bool) -> None:
    rec = Recorder(ok(completion()))
    await make_vision(rec, think).chat(HI, Tier.VISION)
    assert rec.body()["chat_template_kwargs"] == {"enable_thinking": think}


async def test_vision_thinking_leaves_the_other_tiers_alone() -> None:
    rec = Recorder(ok(completion()), ok(completion()))
    model = make_vision(rec, True)
    await model.chat(HI, Tier.FAST)
    await model.chat(HI, Tier.REASONING)
    assert rec.body(0)["chat_template_kwargs"] == {"enable_thinking": False}
    assert rec.body(1)["chat_template_kwargs"] == {"enable_thinking": True}


async def test_unset_vision_thinking_sends_the_body_unchanged() -> None:
    rec = Recorder(ok(completion()))
    await make_vision(rec, None).chat(HI, Tier.VISION)
    assert rec.body() == {"model": MODELS[Tier.VISION], "messages": HI, "temperature": 0.0}


async def test_explicit_thinking_overrides_vision_thinking() -> None:
    rec = Recorder(ok(completion()))
    await make_vision(rec, False).chat(HI, Tier.VISION, thinking=True)
    assert rec.body()["chat_template_kwargs"] == {"enable_thinking": True}


@pytest.mark.parametrize(
    ("raw", "want"), [("", None), ("  ", None), ("false", False), ("true", True)]
)
async def test_from_settings_passes_nebius_vision_thinking(
    raw: str, want: bool | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEBIUS_VISION_THINKING", raw)
    settings = Settings(_env_file=None, nebius_api_key=KEY)  # pyright: ignore[reportCallIssue]
    assert settings.nebius_vision_thinking is want
    rec = Recorder(ok(completion()))
    model = NebiusChatModel.from_settings(settings)
    model._client = httpx2.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url="https://api.tokenfactory.nebius.com/v1", transport=httpx2.MockTransport(rec)
    )
    await model.chat(HI, Tier.VISION)
    sent = rec.body().get("chat_template_kwargs")
    assert sent == (None if want is None else {"enable_thinking": want})


async def test_explicit_thinking_overrides_the_tier_default() -> None:
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI, Tier.FAST, thinking=True)

    assert rec.body()["chat_template_kwargs"] == {"enable_thinking": True}


async def test_optional_fields_are_sent_only_when_given() -> None:
    rf = {"type": "json_object"}
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI, temperature=0.7, max_tokens=64, response_format=rf)

    body = rec.body()
    assert (body["temperature"], body["max_tokens"], body["response_format"]) == (0.7, 64, rf)


async def test_a_tier_without_a_model_is_a_config_error_and_sends_nothing() -> None:
    rec = Recorder()
    model = make(rec, models={Tier.FAST: MODELS[Tier.FAST], Tier.VISION: ""})

    with pytest.raises(LLMConfigError, match="vision"):
        await model.chat(HI, Tier.VISION)
    assert rec.requests == []


def test_from_settings_refuses_a_missing_api_key() -> None:
    with pytest.raises(LLMConfigError, match="NEBIUS_API_KEY"):
        NebiusChatModel.from_settings(Settings(_env_file=None, nebius_api_key=""))  # pyright: ignore[reportCallIssue]


def test_from_settings_maps_each_tier_to_its_setting() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        nebius_api_key=KEY,
        nebius_model_fast="f",
        nebius_model_reasoning="r",
        nebius_model_vision="v",
    )
    model = NebiusChatModel.from_settings(settings)

    assert [model.model_for(t) for t in Tier] == ["f", "r", "v"]


# --- the result -------------------------------------------------------------------


async def test_result_reports_the_answering_model_and_usage_with_reasoning_tokens() -> None:
    usage = {
        "prompt_tokens": 32,
        "completion_tokens": 271,
        "completion_tokens_details": {"reasoning_tokens": 266},
    }
    rec = Recorder(ok(completion("391", model="nvidia/served-id", usage=usage)))
    result = await make(rec).chat(HI, Tier.REASONING)

    assert result.content == "391"
    assert result.model == "nvidia/served-id"
    assert result.tier is Tier.REASONING
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (32, 271)
    assert result.usage.reasoning_tokens == 266
    assert result.finish_reason == "stop"


async def test_missing_usage_details_count_as_zero_reasoning_tokens() -> None:
    rec = Recorder(ok(completion(usage={"prompt_tokens": 1, "completion_tokens": 1})))
    result = await make(rec).chat(HI)

    assert result.usage.reasoning_tokens == 0


async def test_content_is_stripped_of_a_leading_think_block_and_whitespace() -> None:
    rec = Recorder(ok(completion("\n<think>\n17*23 is...\n</think>\n\n391\n")))
    result = await make(rec).chat(HI)

    assert result.content == "391"


async def test_empty_content_with_reasoning_says_thinking_used_the_budget() -> None:
    rec = Recorder(ok(completion("", reasoning="let me think", finish_reason="length")))

    with pytest.raises(LLMEmptyResponse, match="thinking=False"):
        await make(rec).chat(HI, Tier.REASONING)


async def test_empty_content_without_reasoning_names_the_finish_reason() -> None:
    rec = Recorder(ok(completion(None, finish_reason="content_filter")))

    with pytest.raises(LLMEmptyResponse, match="content_filter"):
        await make(rec).chat(HI)


async def test_content_as_a_list_of_parts_is_joined_from_its_text_parts() -> None:
    parts = [{"type": "text", "text": "39"}, {"type": "image_url"}, {"type": "text", "text": "1"}]
    rec = Recorder(ok(completion(None) | {"choices": [{"message": {"content": parts}}]}))

    assert (await make(rec).chat(HI)).content == "391"


async def test_a_200_that_is_not_json_is_an_llm_error_not_a_decode_error() -> None:
    rec = Recorder(httpx2.Response(200, text="<html>gateway</html>"))

    with pytest.raises(LLMRequestError) as err:
        await make(rec).chat(HI)
    assert err.value.status == 200


# --- retries ----------------------------------------------------------------------


async def test_429_honours_retry_after_then_succeeds() -> None:
    sleeps = Sleeps()
    rec = Recorder(ok({}, 429, {"retry-after": "7"}), ok(completion("done")))
    result = await make(rec, sleeps).chat(HI)

    assert result.content == "done"
    assert sleeps.calls == [7.0]


async def test_retry_after_is_capped_at_30_seconds() -> None:
    sleeps = Sleeps()
    rec = Recorder(ok({}, 429, {"retry-after": "600"}), ok(completion()))
    await make(rec, sleeps).chat(HI)

    assert sleeps.calls == [30.0]


async def test_5xx_and_network_errors_back_off_exponentially() -> None:
    sleeps = Sleeps()
    rec = Recorder(ok({}, 503), httpx2.ConnectError("refused"), ok(completion("done")))
    result = await make(rec, sleeps).chat(HI)

    assert result.content == "done"
    assert sleeps.calls == [2.0, 4.0]


async def test_exhausted_retries_raise_with_the_last_status() -> None:
    rec = Recorder(*(ok({}, 502) for _ in range(5)))

    with pytest.raises(LLMRequestError) as err:
        await make(rec).chat(HI)
    assert err.value.status == 502
    assert len(rec.requests) == 5


async def test_a_400_is_not_retried_and_the_error_never_contains_the_key() -> None:
    rec = Recorder(ok({"detail": "bad request"}, 400))

    with pytest.raises(LLMRequestError) as err:
        await make(rec).chat(HI)
    assert err.value.status == 400
    assert len(rec.requests) == 1
    assert KEY not in str(err.value)
    assert MODELS[Tier.FAST] in str(err.value)


async def test_exhausted_network_errors_raise_with_no_status() -> None:
    rec = Recorder(
        httpx2.ConnectError("a"),
        httpx2.ReadTimeout("b"),
        httpx2.ConnectError("c"),
        httpx2.RemoteProtocolError("d"),
        httpx2.ConnectError("e"),
    )

    with pytest.raises(LLMRequestError) as err:
        await make(rec).chat(HI)
    assert err.value.status is None
    assert len(rec.requests) == 5


# --- T075: riding out a minute-long drop -------------------------------------------


async def test_four_dropped_connections_then_an_answer_waits_2_4_8_16_seconds() -> None:
    sleeps = Sleeps()
    rec = Recorder(*(httpx2.ConnectError("dropped") for _ in range(4)), ok(completion("done")))
    result = await make(rec, sleeps).chat(HI)

    assert result.content == "done"
    assert sleeps.calls == [2.0, 4.0, 8.0, 16.0]


async def test_five_dropped_connections_give_up_after_five_attempts() -> None:
    sleeps = Sleeps()
    rec = Recorder(*(httpx2.ConnectError("dropped") for _ in range(5)))

    with pytest.raises(LLMRequestError) as err:
        await make(rec, sleeps).chat(HI)
    assert err.value.status is None
    assert len(rec.requests) == 5
    assert sleeps.calls == [2.0, 4.0, 8.0, 16.0]
    assert "5 attempts" in str(err.value)


async def test_a_second_read_timeout_ends_the_call() -> None:
    rec = Recorder(httpx2.ReadTimeout("slow"), httpx2.ReadTimeout("slow"), ok(completion()))

    with pytest.raises(LLMRequestError) as err:
        await make(rec).chat(HI)
    assert err.value.status is None
    assert len(rec.requests) == 2


async def test_one_read_timeout_among_dropped_connections_still_answers() -> None:
    rec = Recorder(
        httpx2.ReadTimeout("slow"), httpx2.ConnectError("dropped"), ok(completion("done"))
    )
    result = await make(rec).chat(HI)

    assert result.content == "done"
    assert len(rec.requests) == 3


async def test_a_long_retry_after_still_waits_at_most_30_seconds() -> None:
    sleeps = Sleeps()
    rec = Recorder(ok({}, 503, {"retry-after": "60"}), ok(completion()))
    await make(rec, sleeps).chat(HI)

    assert sleeps.calls == [30.0]


async def test_the_backoff_itself_is_capped_at_30_seconds() -> None:
    sleeps = Sleeps()
    rec = Recorder(*(httpx2.ConnectError("dropped") for _ in range(7)))
    model = NebiusChatModel(
        api_key=KEY,
        base_url="https://api.tokenfactory.nebius.com/v1",
        models=MODELS,
        max_attempts=7,
        transport=httpx2.MockTransport(rec),
        sleep=sleeps,
    )

    with pytest.raises(LLMRequestError):
        await model.chat(HI)
    assert sleeps.calls == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


async def test_each_request_carries_a_10_second_connect_timeout() -> None:
    rec = Recorder(ok(completion()))
    await make(rec).chat(HI)

    timeout = rec.requests[0].extensions["timeout"]
    assert (timeout["connect"], timeout["read"]) == (10.0, 120.0)


async def test_from_settings_passes_the_connect_timeout_and_5_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = Recorder(*(httpx2.ConnectError("dropped") for _ in range(5)))
    real = httpx2.AsyncClient

    def mocked(**kwargs: Any) -> httpx2.AsyncClient:
        kwargs["transport"] = httpx2.MockTransport(rec)
        return real(**kwargs)

    monkeypatch.setattr(httpx2, "AsyncClient", mocked)
    settings = Settings(_env_file=None, nebius_api_key=KEY)  # pyright: ignore[reportCallIssue]
    model = NebiusChatModel.from_settings(settings)
    monkeypatch.setattr(model, "_sleep", Sleeps())

    with pytest.raises(LLMRequestError):
        await model.chat(HI)
    assert len(rec.requests) == 5
    assert rec.requests[0].extensions["timeout"]["connect"] == 10.0


# --- usage (T069, limits.md §6) ---------------------------------------------------


async def test_on_usage_is_awaited_once_per_answer_and_never_for_a_failure() -> None:
    seen: list[tuple[int, int]] = []

    async def meter(result: Any) -> None:
        seen.append((result.usage.prompt_tokens, result.usage.completion_tokens))

    rec = Recorder(ok(completion(usage={"prompt_tokens": 9, "completion_tokens": 4})), ok({}, 400))
    model = NebiusChatModel(
        api_key=KEY,
        base_url="https://api.tokenfactory.nebius.com/v1",
        models=MODELS,
        transport=httpx2.MockTransport(rec),
        sleep=Sleeps(),
        on_usage=meter,
    )
    await model.chat(HI)
    with pytest.raises(LLMRequestError):
        await model.chat(HI)
    assert seen == [(9, 4)]


async def test_an_empty_answer_is_billed_so_it_is_counted_before_it_raises() -> None:
    # Review of T069: a reasoning call that spends max_tokens thinking returns no content but is
    # billed; the budget must see it.
    seen: list[tuple[int, int]] = []

    async def meter(result: Any) -> None:
        seen.append((result.usage.prompt_tokens, result.usage.completion_tokens))

    empty = completion(None, usage={"prompt_tokens": 50, "completion_tokens": 4000})
    model = NebiusChatModel(
        api_key=KEY,
        base_url="https://api.tokenfactory.nebius.com/v1",
        models=MODELS,
        transport=httpx2.MockTransport(Recorder(ok(empty))),
        sleep=Sleeps(),
        on_usage=meter,
    )
    with pytest.raises(LLMEmptyResponse):
        await model.chat(HI)
    assert seen == [(50, 4000)]


def test_the_vision_defaults_are_super_vl_with_thinking_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T105 (vision-model.md §6, Katlego 2026-10-17): every vision call is Nemotron 3.5 Super VL."""
    monkeypatch.delenv("NEBIUS_MODEL_VISION", raising=False)
    monkeypatch.delenv("NEBIUS_VISION_THINKING", raising=False)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.nebius_model_vision == "nvidia/Nemotron-3.5-Super-VL"
    assert settings.nebius_vision_thinking is False
