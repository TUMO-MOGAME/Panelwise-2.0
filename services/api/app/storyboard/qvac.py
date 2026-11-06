"""Panelwise 2.0's renderer: FLUX.2 [klein] 4B on this machine, through QVAC's `qvac serve --openai`
(`POST /v1/images/generations`), the same model fal.ai ran for Panelwise (storyboard.md §3.5).

What FalRenderer does, minus the cloud: the same frame prompt, render key and store-as-cache,
fitted to the size asked for and post-processed in the style. The drawing size is a setting, as
on an integrated GPU time, not a bill, is the cost; fit() scales the drawing to the frame. There's
no safety checker; a drawing that comes back all black is drawn again with a derived seed.
"""

import asyncio
import base64
import binascii
import io
import logging
import math
import time
from typing import Any, cast

import httpx2
from PIL import Image

from app.core.config import Settings
from app.frames.attempt import RendererFactory
from app.grounding import Extraction
from app.script import Screenplay
from app.shots import Shot
from app.storage import AssetStore
from app.storyboard.fal import REDRAWS, derived_seed
from app.storyboard.prompt import PromptError, build_frame_prompt
from app.storyboard.render import RendererError, RenderRecord
from app.storyboard.styles import Style, StyleRegistry
from app.storyboard.workflow import fit, png_bytes, postprocess, render_key
from app.verify.model import RenderedFrame

log = logging.getLogger(__name__)

STEPS = 4  # klein is distilled for 4 steps, as fal.ai ran it (§3.5)


def qvac_draw_size(width: int, height: int, max_pixels: int) -> tuple[int, int]:
    """Scaled down (never up) to at most max_pixels, each side floored to a multiple of 16
    (the server asks for multiples of 8; klein's latents want 16)."""
    scale = min(1.0, math.sqrt(max_pixels / (width * height)))
    return max(16, int(width * scale) // 16 * 16), max(16, int(height * scale) // 16 * 16)


def qvac_request(model: str, prompt: str, seed: int, draw: tuple[int, int]) -> dict[str, Any]:
    return {
        "model": model,
        "prompt": prompt,
        "size": f"{draw[0]}x{draw[1]}",
        "seed": seed,
        "steps": STEPS,
        "n": 1,
        "response_format": "b64_json",
    }


def finish_frame(raw: bytes, width: int, height: int, style: Style) -> tuple[bytes, bool]:
    """CPU work, run in a thread: fitted and post-processed PNG, and whether it is all black."""
    image = postprocess(fit(raw, width, height), style.grayscale)
    _, brightest = image.convert("L").getextrema()
    return png_bytes(image), brightest == 0


class QvacRenderer:
    """verify.md's RecordingRenderer on QVAC, in one style, for one screenplay."""

    def __init__(
        self,
        *,
        style: Style,
        store: AssetStore,
        screenplay: Screenplay,
        extraction: Extraction,
        client: httpx2.AsyncClient,
        base_url: str,
        model: str,
        max_pixels: int,
        max_words: int = 55,
        timeout_s: float = 900.0,
        free_first: tuple[str, ...] = (),
    ) -> None:
        self.style = style
        self.store = store
        self.screenplay = screenplay
        self.extraction = extraction
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/images/generations"
        self.model = model
        # The text models' aliases, unloaded before the first drawing: QVAC keeps a model loaded
        # until told otherwise, and Qwen3 4B beside FLUX.2 [klein] and its encoder is ~9 GB.
        self.free_first = free_first
        self.freed = False
        self.max_pixels = max_pixels
        self.max_words = max_words
        self.timeout_s = timeout_s
        self.records: dict[tuple[tuple[int, int], int], RenderRecord] = {}

    def record(self, shot: tuple[int, int], attempt: int) -> RenderRecord:
        return self.records[(shot, attempt)]

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        key = (shot.scene_index, shot.number)
        try:
            prompt = build_frame_prompt(
                shot, self.screenplay, self.extraction, self.style, max_words=self.max_words
            )
        except PromptError as exc:
            raise RendererError(f"shot {key}: {exc}") from exc
        text = prompt.text()
        draw = qvac_draw_size(width, height, self.max_pixels)
        step = "grayscale" if self.style.grayscale else "none"
        started = time.perf_counter()
        bodies = [
            qvac_request(self.model, text, derived_seed(seed, k), draw) for k in range(REDRAWS)
        ]
        # "qvac:" keeps these apart from fal.ai's drawings of the same request in a shared store.
        addresses = [
            render_key({"model": f"qvac:{self.model}", "request": body}, width, height, step)
            for body in bodies
        ]
        drawn: tuple[int, bytes, bool] | None = None  # (redraw, png, cached)
        for k, address in enumerate(addresses):
            if await self.store.exists(f"frames/{address}.png"):
                drawn = (k, await self.store.get(f"frames/{address}.png"), True)
                break
        if drawn is None:
            for k, body in enumerate(bodies):
                raw = await self.draw_one(body)
                png, black = await asyncio.to_thread(finish_frame, raw, width, height, self.style)
                if black:
                    log.warning("QVAC drew shot %s attempt %d black (redraw %d)", key, attempt, k)
                    continue
                await self.store.put(f"frames/{addresses[k]}.png", png, "image/png")
                drawn = (k, png, False)
                break
        if drawn is None:
            raise RendererError("every QVAC drawing of this shot came back black")
        k, png, cached = drawn
        seconds = None if cached else time.perf_counter() - started
        if seconds is not None:
            log.info(
                "QVAC drew shot %s attempt %d in %.1f s at %dx%d", key, attempt, seconds, *draw
            )
        self.records[(key, attempt)] = RenderRecord(
            key, attempt, addresses[k], f"frames/{addresses[k]}.png", prompt, cached, seconds
        )
        return RenderedFrame(key, attempt, bodies[k]["seed"], png, width, height, text)

    async def _free_text_models(self) -> None:
        """Once per renderer: unload the text models (`DELETE /v1/models/{alias}`), so drawing
        has the memory. Best effort: an alias not loaded, or a failed call, only logs; the next
        text call loads its model again (a cold start)."""
        if self.freed:
            return
        self.freed = True
        for alias in dict.fromkeys(self.free_first):
            try:
                response = await self.client.delete(f"{self.base_url}/models/{alias}", timeout=60.0)
            except httpx2.TransportError as exc:
                log.warning("QVAC: could not unload %s (%s)", alias, type(exc).__name__)
                continue
            if response.status_code == 200:
                log.info("QVAC: unloaded %s before drawing", alias)

    async def draw_one(self, body: dict[str, Any]) -> bytes:
        """One drawing. No retry: a local server that fails will fail the same way again. No
        message carries the prompt."""
        await self._free_text_models()
        try:
            response = await self.client.post(self.url, json=body, timeout=self.timeout_s)
        except httpx2.TransportError as exc:
            raise RendererError(
                f"QVAC unreachable for {self.model} ({type(exc).__name__})"
            ) from exc
        if response.status_code != 200:
            raise RendererError(f"QVAC answered {response.status_code} for {self.model}")
        try:
            answer: object = response.json()
            data = cast(list[dict[str, Any]], cast(dict[str, Any], answer)["data"])
            raw = base64.b64decode(str(data[0]["b64_json"]), validate=True)
            with Image.open(io.BytesIO(raw)) as decoded:
                decoded.verify()
        except (ValueError, KeyError, IndexError, TypeError, binascii.Error, OSError) as exc:
            raise RendererError(f"QVAC's image for {self.model} is not readable") from exc
        return raw


def qvac_factory(
    registry: StyleRegistry, store: AssetStore, client: httpx2.AsyncClient, settings: Settings
) -> RendererFactory:
    """A fresh renderer per job or attempt, in the registry's default style."""
    style = registry.get(None)

    def factory(screenplay: Screenplay, extraction: Extraction) -> QvacRenderer:
        return QvacRenderer(
            style=style,
            store=store,
            screenplay=screenplay,
            extraction=extraction,
            client=client,
            base_url=settings.nebius_base_url,
            model=settings.qvac_draw_model,
            max_pixels=settings.qvac_draw_max_pixels,
            max_words=settings.comfyui_max_words,
            free_first=(settings.nebius_model_fast, settings.nebius_model_reasoning),
            timeout_s=settings.qvac_draw_timeout_s,
        )

    return factory
