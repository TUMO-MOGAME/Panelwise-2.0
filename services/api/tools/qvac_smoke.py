"""Timed chat calls per tier through the app's own LLM client (Panelwise 2.0, BOOTCAMP.md step 3).

Start the server first, from the repo root: `qvac serve --openai --port 11435`. Set the QVAC
block of .env.example (in .env or the environment). Then, from services/api:

    uv run python -m tools.qvac_smoke              # fast tier
    uv run python -m tools.qvac_smoke reasoning    # or several: fast reasoning

The first call to a tier loads its model (a cold start), so each tier is called twice and the
second call is the one measured. Tokens/sec here is completion tokens over the whole call's
wall time, prompt processing included: a floor, not the decode speed alone.
"""

import asyncio
import json
import sys
import time

from app.core.config import Settings
from app.llm import NebiusChatModel, Tier

# A Panelwise-shaped job: pull one structured fact out of a screenplay line, as JSON.
SCENE = (
    "INT. LIGHTHOUSE KITCHEN - NIGHT\n"
    "MARA (60s, oilskin coat) slams a tin kettle onto the stove. Rain hammers the window."
)
MESSAGES = [
    {"role": "system", "content": "Answer with JSON only."},
    {
        "role": "user",
        "content": "From this scene heading and action, give the location, time of day and "
        'the characters, as {"location": str, "time": str, "characters": [str]}.\n\n' + SCENE,
    },
]


async def main(tiers: list[Tier]) -> None:
    settings = Settings()
    model = NebiusChatModel.from_settings(settings)
    print(f"server: {settings.nebius_base_url}  thinking field: {settings.llm_thinking_field}")
    try:
        for tier in tiers:
            for label in ("cold", "warm"):
                start = time.perf_counter()
                result = await model.chat(
                    MESSAGES, tier, response_format={"type": "json_object"}, max_tokens=256
                )
                seconds = time.perf_counter() - start
                tokens = result.usage.completion_tokens
                print(
                    f"{tier:<9} {label}  {seconds:6.1f} s  {tokens:4d} tokens  "
                    f"{tokens / seconds:5.1f} tok/s  model={result.model}"
                )
            print(json.dumps(json.loads(result.content), ensure_ascii=False))
    finally:
        await model.aclose()


if __name__ == "__main__":
    asyncio.run(main([Tier(name) for name in sys.argv[1:]] or [Tier.FAST]))
