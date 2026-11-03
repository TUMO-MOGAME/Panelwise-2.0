"""Render helpers shared by every backend (storyboard.md §3.3, §6 `workflow.py`): fitting a drawing
to the exact size asked for, the style's post-processing, and the render key that addresses a
stored frame. Pure. ComfyUI's graph helpers (`Workflow`, `load_workflow`, `substitute`) were
never built: the ComfyUI backend (T003) was cut 2026-10-19."""

import hashlib
import io
import json
from collections.abc import Mapping
from typing import Any

from PIL import Image, ImageOps

RENDER_VERSION: int = 1  # bumped whenever `fit` or a post-processing pass changes the pixels


def fit(png: bytes, width: int, height: int) -> Image.Image:
    """The drawing scaled to cover `width x height` and centre-cropped to exactly that: the crop
    removes only the rounding excess between the drawn and asked aspect, never composition."""
    with Image.open(io.BytesIO(png)) as drawn:
        image = drawn.convert("RGB")
    scale = max(width / image.width, height / image.height)
    size = (max(width, round(image.width * scale)), max(height, round(image.height * scale)))
    resized: Image.Image = image.resize(size, resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
    left, top = (size[0] - width) // 2, (size[1] - height) // 2
    return resized.crop((left, top, left + width, top + height))


def postprocess(image: Image.Image, grayscale: bool) -> Image.Image:
    """The style's pass (FrameFlow's `image_postprocess.py`): grayscale, then autocontrast."""
    if not grayscale:
        return image
    return ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=0.5)


def png_bytes(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(
        out, format="PNG"
    )  # Pillow writes no text chunks unless asked: same pixels, same bytes
    return out.getvalue()


def render_key(graph: Mapping[str, Any], width: int, height: int, postprocess: str) -> str:
    """sha256 hex of the canonical JSON of what was submitted (sorted keys, no whitespace), then
    the requested size, RENDER_VERSION and the post-processing step, each after a 0x1f (§3.3)."""
    canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    tail = "\x1f".join([f"{width}x{height}", str(RENDER_VERSION), postprocess])
    return hashlib.sha256(f"{canonical}\x1f{tail}".encode()).hexdigest()
