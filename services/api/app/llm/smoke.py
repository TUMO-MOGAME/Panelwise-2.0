"""One real call per text tier against Token Factory: does the configured account work?

    cd services/api && uv run python -m app.llm.smoke

Prints the model that answered and its token usage; never the key. Exit 1 if a tier fails,
or if the fast tier spent tokens thinking (findings U2: it must not). Costs a fraction of a cent.
"""

import asyncio
import sys

from pydantic import BaseModel

from app.core.config import Settings
from app.llm import LLMError, NebiusChatModel, Tier, structured_chat


class Product(BaseModel):
    product: int


async def main() -> int:
    try:
        model = NebiusChatModel.from_settings(Settings())
    except LLMError as exc:
        print(f"FAIL  {exc}")
        return 1

    failed = False
    question = [{"role": "user", "content": "What is 17 * 23?"}]
    try:
        for tier in (Tier.FAST, Tier.REASONING):
            try:
                result = await structured_chat(model, question, Product, tier, max_tokens=2048)
            except LLMError as exc:
                print(f"FAIL  {tier:<9} {exc}")
                failed = True
                continue
            u = result.chat.usage
            correct = result.value.product == 391
            thinking_leak = tier is Tier.FAST and u.reasoning_tokens > 0
            failed = failed or not correct or thinking_leak
            print(
                f"{'ok  ' if correct and not thinking_leak else 'FAIL'}  {tier:<9} "
                f"{result.chat.model}  answer={result.value.product}  "
                f"tokens in={u.prompt_tokens} out={u.completion_tokens} "
                f"reasoning={u.reasoning_tokens}"
                + ("  <- fast tier must not think" if thinking_leak else "")
            )
    finally:
        await model.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
