"""extract, chunk_scenes, render_chunk: grounding.md §4 and §6. MockTransport, no network."""

import json
from typing import Any

import httpx2
import pytest

from app.grounding import SYSTEM_PROMPT, ExtractionError, chunk_scenes, extract, render_chunk
from app.llm import NebiusChatModel, Tier
from app.script import Dialogue, Screenplay, parse_text
from tests.script.conftest import two_page_text

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "reasoning-model", Tier.VISION: "v"}


@pytest.fixture
def screenplay() -> Screenplay:
    text, breaks = two_page_text()
    return parse_text(text, breaks)


class Scripted:
    """Answers each chunk from what its user message contains; records every request body."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.fail_on = fail_on

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        chunk = body["messages"][-1]["content"]
        if self.fail_on and self.fail_on in chunk:
            return httpx2.Response(400, json={"detail": "bad"})
        entities: list[dict[str, Any]] = []
        if "KITCHEN" in chunk:
            entities.append(
                {"name": "NANDI", "kind": "character", "quotes": ["NANDI (60s, oilskin coat)"]}
            )
        if "GALLERY" in chunk:
            entities.append(
                {"name": "THABO", "kind": "character", "quotes": ["holding a torn map"]}
            )
            entities.append({"name": "torn map", "kind": "prop", "quotes": ["a torn map"]})
        return httpx2.Response(
            200,
            json={
                "model": "fast-model",
                "choices": [{"message": {"content": json.dumps({"entities": entities})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
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


def test_chunks_hold_whole_scenes_in_order(screenplay: Screenplay) -> None:
    chunks = chunk_scenes(screenplay, chunk_chars=1)  # every scene alone: none is ever split
    assert [[s.index for s in c] for c in chunks] == [[0], [1], [2]]
    assert [[s.index for s in c] for c in chunk_scenes(screenplay, 100_000)] == [[0, 1, 2]]


def test_rendered_chunk_carries_every_element_verbatim(screenplay: Screenplay) -> None:
    rendered = render_chunk(screenplay.scenes)
    for scene in screenplay.scenes:
        assert scene.heading in rendered
        for e in scene.elements:
            assert e.text in rendered
            if isinstance(e, Dialogue):
                assert e.cue in rendered
    assert "(without turning)" in rendered


def test_the_prompt_asks_for_quotes_without_cues_or_parentheticals() -> None:
    # T039: Lightning copied the cue line into dialogue quotes. The filter can strip a speech's
    # own header, but the prompt should not invite it.
    assert "without the speaker's name" in SYSTEM_PROMPT
    assert "parenthetical" in SYSTEM_PROMPT


async def test_extract_calls_the_fast_tier_with_thinking_off_and_strict_schema(
    screenplay: Screenplay,
) -> None:
    handler = Scripted()
    await extract(make(handler), screenplay, chunk_chars=1)

    assert len(handler.bodies) == 3
    body = handler.bodies[0]
    assert body["model"] == "fast-model"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == 0.0
    assert body["response_format"]["json_schema"]["name"] == "ChunkEntities"
    assert body["response_format"]["json_schema"]["strict"] is True


async def test_extract_grounds_merges_and_reports(screenplay: Screenplay) -> None:
    result = await extract(make(Scripted()), screenplay, chunk_chars=1)

    names = {(e.kind.value, e.name) for e in result.entities}
    assert {("character", "NANDI"), ("character", "THABO"), ("prop", "torn map")} <= names
    assert result.report.faithfulness == 1.0
    assert result.report.recall == 1.0
    assert result.models == ("fast-model",)
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (300, 30)


async def test_too_many_chunks_is_refused_before_any_call(screenplay: Screenplay) -> None:
    handler = Scripted()
    with pytest.raises(ExtractionError, match="3 chunks") as caught:
        await extract(make(handler), screenplay, chunk_chars=1, max_chunks=2)
    assert caught.value.scene is None  # the budget, not a scene (web.md §4.1)
    assert handler.bodies == []


async def test_a_failing_chunk_fails_the_extraction_and_names_its_scenes(
    screenplay: Screenplay,
) -> None:
    with pytest.raises(ExtractionError, match="scenes 2") as caught:
        await extract(make(Scripted(fail_on="GALLERY")), screenplay, chunk_chars=1)
    assert caught.value.scene == "2"


def test_the_prompt_asks_for_species_and_other_names() -> None:
    # T051: the model is told what each field is; the filter grounds what comes back.
    assert "species" in SYSTEM_PROMPT and "other_names" in SYSTEM_PROMPT
    assert "even if only in dialogue" in SYSTEM_PROMPT
