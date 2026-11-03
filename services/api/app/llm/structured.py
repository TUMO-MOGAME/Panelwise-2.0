"""structured_chat: a chat call that returns a validated Pydantic object.

docs/design/llm.md §4. Token Factory enforces `json_schema` on Nemotron (findings U1), so the
repair retry is a backstop, not the plan. Validation fixes shape, never truth: grounding is
the caller's job, and is never loosened to absorb a failure here.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from app.llm.client import ChatResult, Message, NebiusChatModel, Tier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    chat: ChatResult
    repaired: bool


def _with_schema(messages: Sequence[Message], schema: dict[str, object]) -> list[Message]:
    instruction = f"Reply with JSON only, matching this JSON Schema: {json.dumps(schema)}"
    out = [dict(m) for m in messages]
    # One system message only: some chat templates reject a second.
    if out and out[0].get("role") == "system":
        content = out[0].get("content")
        if isinstance(content, str):
            out[0]["content"] = f"{content}\n\n{instruction}"
            return out
        if isinstance(content, list):
            parts = cast(list[Any], content)
            out[0]["content"] = [*parts, {"type": "text", "text": instruction}]
            return out
    out.insert(0, {"role": "system", "content": instruction})
    return out


async def structured_chat[T: BaseModel](
    model: NebiusChatModel,
    messages: Sequence[Message],
    response_model: type[T],
    tier: Tier = Tier.FAST,
    *,
    max_repair_attempts: int = 1,
    thinking: bool | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    grammar: Mapping[str, Any] | None = None,
) -> StructuredResult[T]:
    """`grammar` (T109): the schema the decoder enforces, in place of the model's own, for limits
    the prompt doesn't show. The prompt's schema text and the validation stay `response_model`'s."""
    schema = response_model.model_json_schema()
    decoded = dict(grammar) if grammar is not None else schema
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": response_model.__name__, "schema": decoded, "strict": True},
    }
    turns = _with_schema(messages, schema)

    attempts_left = max_repair_attempts
    while True:
        result = await model.chat(
            turns,
            tier,
            thinking=thinking,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        try:
            value = response_model.model_validate_json(result.content)
        except ValidationError as exc:
            if attempts_left <= 0:
                raise
            attempts_left -= 1
            # The type only: a validation message quotes the output, which quotes the script.
            logger.warning("%s from %s: repairing", type(exc).__name__, result.model)
            turns = [
                *turns,
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": (
                        f"Your previous response failed schema validation:\n{exc}\n"
                        "Reply with only the corrected JSON, matching the schema exactly."
                    ),
                },
            ]
            continue
        return StructuredResult(
            value=value, chat=result, repaired=attempts_left < max_repair_attempts
        )
