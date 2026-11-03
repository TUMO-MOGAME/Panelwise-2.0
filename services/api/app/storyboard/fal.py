"""The default renderer: FLUX.2 [klein] 4B on fal.ai, the model `Settings.fal_model` names
(FLUX.1 [schnell] before 2026-10-11; storyboard.md §3.5; T026).

One synchronous call per drawing, at most a megapixel in multiples of 16 (fal bills each started
megapixel), fitted to exactly the size asked for and post-processed in the style. Every drawing is
stored by its render key before `render` returns, so the store is the cache and the record is there
for the frame writers. A frame fal's safety checker blacks out never reaches the audit: it is drawn
again with a derived seed.
"""

import asyncio
import io
import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx2
from PIL import Image

from app.core.config import Settings
from app.frames.attempt import RendererFactory
from app.grounding import Extraction
from app.script import Screenplay
from app.shots import Shot
from app.storage import AssetStore
from app.storyboard.prompt import PromptError, build_frame_prompt
from app.storyboard.render import RendererError, RenderRecord
from app.storyboard.styles import Style, StyleRegistry
from app.storyboard.workflow import fit, png_bytes, postprocess, render_key
from app.verify.model import RenderedFrame

log = logging.getLogger(__name__)

MAX_PIXELS = 1_000_000  # fal bills each started megapixel: a drawing never starts a second
FAL_URL = "https://fal.run/{model}"
STEPS = 4  # FLUX.1 [schnell] is distilled for 1-4 steps; klein runs at the same 4 (§3.5)
TRIES = 3  # one call and two retries on a 429, a 5xx or a network error
REDRAWS = 3  # the seed, then two derived seeds when the safety checker blacks a drawing out
GOLDEN = 0x9E3779B1  # spreads the derived seeds across the 32-bit range


def fal_draw_size(width: int, height: int) -> tuple[int, int]:
    """Scaled down (never up) to at most MAX_PIXELS, each side floored to a multiple of 16."""
    scale = min(1.0, math.sqrt(MAX_PIXELS / (width * height)))
    return max(16, int(width * scale) // 16 * 16), max(16, int(height * scale) // 16 * 16)


def fal_request(prompt: str, seed: int, draw: tuple[int, int]) -> dict[str, Any]:
    """The canonical body (§3.5): a plain prompt (no weights, escapes or negative), seed, PNG."""
    return {
        "prompt": prompt,
        "image_size": {"width": draw[0], "height": draw[1]},
        "seed": seed,
        "num_inference_steps": STEPS,
        "num_images": 1,
        "output_format": "png",
    }


def derived_seed(seed: int, redraw: int) -> int:
    return (seed + redraw * GOLDEN) % 2**32


def _finish(raw: bytes, width: int, height: int, style: Style) -> tuple[bytes, bool]:
    """CPU work, run in a thread: fitted and post-processed PNG, and whether it is all black."""
    image = postprocess(fit(raw, width, height), style.grayscale)
    _, brightest = image.convert("L").getextrema()
    return png_bytes(image), brightest == 0


class FalRenderer:
    """verify.md's RecordingRenderer on fal.ai, in one style, for one screenplay."""

    def __init__(
        self,
        *,
        style: Style,
        store: AssetStore,
        screenplay: Screenplay,
        extraction: Extraction,
        client: httpx2.AsyncClient,
        key: str,
        model: str = "fal-ai/flux/schnell",
        max_words: int = 55,
        timeout_s: float = 60.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.style = style
        self.store = store
        self.screenplay = screenplay
        self.extraction = extraction
        self.client = client
        self.key = key
        self.model = model
        self.max_words = max_words
        self.timeout_s = timeout_s
        self.sleep = sleep
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
        except PromptError as exc:  # a style or budget problem: configuration, never a cut prompt
            raise RendererError(f"shot {key}: {exc}") from exc
        text = prompt.text()
        draw = fal_draw_size(width, height)
        step = "grayscale" if self.style.grayscale else "none"
        started = time.perf_counter()
        bodies = [fal_request(text, derived_seed(seed, k), draw) for k in range(REDRAWS)]
        addresses = [
            render_key({"model": self.model, "request": body}, width, height, step)
            for body in bodies
        ]
        drawn: tuple[int, bytes, bool] | None = None  # (redraw, png, cached)
        # The cache covers redraws (§3.5): a shot whose first seed was flagged is free next time.
        for k, address in enumerate(addresses):
            if await self.store.exists(f"frames/{address}.png"):  # stored drawings were never black
                drawn = (k, await self.store.get(f"frames/{address}.png"), True)
                break
        if drawn is None:
            for k, body in enumerate(bodies):
                answer = await self._call(body)
                if self._flagged(answer):
                    log.warning("fal.ai flagged shot %s attempt %d (redraw %d)", key, attempt, k)
                    continue
                raw = await self._image(answer, draw)
                png, black = await asyncio.to_thread(_finish, raw, width, height, self.style)
                if black:  # flagged in all but name: never stored, never audited
                    log.warning("fal.ai drew shot %s attempt %d black (redraw %d)", key, attempt, k)
                    continue
                await self.store.put(f"frames/{addresses[k]}.png", png, "image/png")
                drawn = (k, png, False)
                break
        if drawn is None:
            raise RendererError("fal.ai's safety checker blocked every drawing of this shot")
        k, png, cached = drawn
        seconds = None if cached else time.perf_counter() - started
        self.records[(key, attempt)] = RenderRecord(
            key, attempt, addresses[k], f"frames/{addresses[k]}.png", prompt, cached, seconds
        )
        return RenderedFrame(key, attempt, bodies[k]["seed"], png, width, height, text)

    def _flagged(self, answer: dict[str, Any]) -> bool:
        """fal.ai's safety result, read fail-closed: no clean list of booleans is an error."""
        flags: object = answer.get("has_nsfw_concepts")
        listed = cast(list[object], flags) if isinstance(flags, list) else []
        if not listed or not all(isinstance(f, bool) for f in listed):
            raise RendererError(f"fal.ai's answer for {self.model} has no safety result")
        return bool(listed[0])

    async def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._send("POST", FAL_URL.format(model=self.model), json=body)
        try:
            answer: object = response.json()
        except ValueError as exc:
            raise RendererError(f"fal.ai answered {self.model} with something not JSON") from exc
        if not isinstance(answer, dict):
            raise RendererError(f"fal.ai answered {self.model} with something not an object")
        return answer  # pyright: ignore[reportUnknownVariableType]

    async def _image(self, answer: dict[str, Any], draw: tuple[int, int]) -> bytes:
        images: object = answer.get("images")
        listed = cast(list[object], images) if isinstance(images, list) else []
        first: object = listed[0] if listed else None
        if not isinstance(first, dict) or not cast(dict[str, Any], first).get("url"):
            raise RendererError(f"fal.ai answered {self.model} with no image")
        image = cast(dict[str, Any], first)
        # The asked side or up to 31 px more: klein draws in multiples of 32 (720 -> 736), and
        # fit() crops the excess (storyboard.md §3.5).
        got = (image.get("width"), image.get("height"))
        if not all(isinstance(g, int) and 0 <= g - d < 32 for g, d in zip(got, draw, strict=True)):
            raise RendererError(
                f"fal.ai drew {image.get('width')} x {image.get('height')} for {self.model}, "
                f"not the {draw[0]} x {draw[1]} asked for"
            )
        raw = (await self._send("GET", str(image["url"]))).content
        try:
            with Image.open(io.BytesIO(raw)) as decoded:
                decoded.verify()
        except (OSError, ValueError) as exc:
            raise RendererError(f"fal.ai's image for {self.model} is not readable") from exc
        return raw

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx2.Response:
        """One request, retried twice on a network error, a 429 or a 5xx; any other failure at once.
        No message carries the key, the URL's query or the prompt."""
        headers = {"Authorization": f"Key {self.key}"} if method == "POST" else {}
        status: int | None = None
        for tried in range(TRIES):
            if tried:
                await self.sleep(float(tried))  # 1 s, then 2 s
            try:
                response = await self.client.request(
                    method, url, headers=headers, timeout=self.timeout_s, **kwargs
                )
            except httpx2.TransportError as exc:
                status = None
                self._retrying(type(exc).__name__, tried)
                continue
            status = response.status_code
            if 200 <= status < 300:
                return response
            if status != 429 and status < 500:
                raise RendererError(f"fal.ai answered {status} for {self.model}")
            self._retrying(str(status), tried)
        what = "no answer" if status is None else f"{status}"
        raise RendererError(f"fal.ai failed for {self.model} after {TRIES} tries ({what})")

    def _retrying(self, what: str, tried: int) -> None:
        """Never silent (§3.5): what went wrong on this try; never the key, query or prompt."""
        log.warning("fal.ai %s for %s (try %d of %d)", what, self.model, tried + 1, TRIES)


def fal_factory(
    registry: StyleRegistry, store: AssetStore, client: httpx2.AsyncClient, settings: Settings
) -> RendererFactory:
    """A fresh renderer per job or attempt, in the registry's default style (§3.5)."""
    style = registry.get(None)

    def factory(screenplay: Screenplay, extraction: Extraction) -> FalRenderer:
        return FalRenderer(
            style=style,
            store=store,
            screenplay=screenplay,
            extraction=extraction,
            client=client,
            key=settings.fal_key,
            model=settings.fal_model,
            max_words=settings.comfyui_max_words,
            timeout_s=settings.fal_timeout_s,
        )

    return factory
