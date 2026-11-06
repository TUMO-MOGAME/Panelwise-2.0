"""Timed calls through the app's own clients (Panelwise 2.0, BOOTCAMP.md steps 3 and 4): text per
tier, and one drawing with FLUX.2 [klein].

Start the server first, from the repo root: `qvac serve --openai --port 11435`. Set the QVAC
block of .env.example (in .env or the environment). Then, from services/api:

    uv run python -m tools.qvac_smoke              # fast tier
    uv run python -m tools.qvac_smoke reasoning    # or several: fast reasoning
    uv run python -m tools.qvac_smoke fast draw    # text, then one drawing (QVAC_DRAW_MODEL)

The first call to a tier loads its model (a cold start), so each tier is called twice and the
second call is the one measured. Tokens/sec here is completion tokens over the whole call's
wall time, prompt processing included: a floor, not the decode speed alone. `draw` unloads the
text models first, as the renderer does in a job, then draws one frame at the configured size
and fits it to 1280 x 720, saving it under .local-data/smoke/.
"""

import asyncio
import json
import sys
import time

import httpx2

from app.core.config import REPO_ENV, Settings
from app.llm import NebiusChatModel, Tier
from app.storyboard.qvac import QvacRenderer, finish_frame, qvac_draw_size, qvac_request
from app.storyboard.styles import PUBLIC_STYLES, load_styles

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
# What a frame prompt looks like (storyboard/prompt.py builds the real ones from the plan).
DRAW_PROMPT = (
    "Storyboard frame, ink drawing. Medium shot. Interior of a lighthouse kitchen at night. "
    "A woman in her sixties in an oilskin coat slams a tin kettle onto an old stove. "
    "Rain streaks the dark window behind her."
)
OUT = REPO_ENV.parent / ".local-data" / "smoke"


async def text(model: NebiusChatModel, tier: Tier) -> None:
    result = None
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
    assert result is not None
    print(json.dumps(json.loads(result.content), ensure_ascii=False))


async def draw(settings: Settings) -> None:
    if not settings.qvac_draw_model:
        raise SystemExit("QVAC_DRAW_MODEL is not set (the alias in qvac.config.json: draw)")
    style = load_styles(PUBLIC_STYLES, None).get(None)  # the app's default style
    async with httpx2.AsyncClient() as client:
        renderer = QvacRenderer(
            style=style,
            store=None,  # pyright: ignore[reportArgumentType]  # this draws, it never stores
            screenplay=None,  # pyright: ignore[reportArgumentType]
            extraction=None,  # pyright: ignore[reportArgumentType]
            client=client,
            base_url=settings.nebius_base_url,
            model=settings.qvac_draw_model,
            max_pixels=settings.qvac_draw_max_pixels,
            timeout_s=settings.qvac_draw_timeout_s,
            free_first=(settings.nebius_model_fast, settings.nebius_model_reasoning),
        )
        size = qvac_draw_size(1280, 720, settings.qvac_draw_max_pixels)
        start = time.perf_counter()
        raw = await renderer.draw_one(qvac_request(settings.qvac_draw_model, DRAW_PROMPT, 42, size))
        seconds = time.perf_counter() - start
    png, black = finish_frame(raw, 1280, 720, style)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"draw-{int(time.time())}.png"
    path.write_bytes(png)
    print(f"draw      {seconds:6.1f} s  {size[0]}x{size[1]} fitted to 1280x720  ->  {path}")
    if black:
        print("draw      WARNING: the drawing came back all black")


async def main(names: list[str]) -> None:
    settings = Settings()
    print(f"server: {settings.nebius_base_url}  thinking field: {settings.llm_thinking_field}")
    model = NebiusChatModel.from_settings(settings)
    try:
        for name in names:
            if name == "draw":
                await draw(settings)
            else:
                await text(model, Tier(name))
    finally:
        await model.aclose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["fast"]))
