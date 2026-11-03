"""The style registry: how a frame is drawn, never what is in it. docs/design/storyboard.md §3.2.

Ported from FrameFlow's storyboard_styles.py: its three drawn styles (clean, ink, pencil) and what
its same-seed A/B taught (no negations; the medium leads; grayscale is a pixel pass, not a prompt
word). Changed: a style is a TOML file, not a Python dict, so a private pack is data loaded from
outside the repo rather than code; FrameFlow's `classic` (negations, a pre-styles cache key) and its
`fast` draft mode (a CPU-time saving on a laptop) are dropped (§8).

Public styles live in the repo's `styles/`; private ones in `PANELWISE_PRIVATE_STYLES`. Both get the
same checks, and a bad file fails the start-up naming the file: a style can't carry weight syntax
(the renderer's job), name a subject (who is in the frame is the script's job), shadow a public
style, or be the default while private (the demo runs on public styles only, PLAN.md NN2).
"""

import math
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

# services/api/styles, inside the API image's build context (the repo-root styles/ is a symlink to
# it: deploy.md §6), wherever the API is started from.
PUBLIC_STYLES = Path(__file__).resolve().parents[2] / "styles"

# Whole words that would put someone or something legible in every frame, whatever the script
# says. Not a proof a style is content-free; the audit catches the rest.
SUBJECT_WORDS = frozenset(
    {
        "person",
        "people",
        "man",
        "men",
        "woman",
        "women",
        "boy",
        "girl",
        "child",
        "children",
        "figure",
        "figures",
        "crowd",
        "character",
        "face",
        "portrait",
        "animal",
        "text",
        "letters",
        "words",
        "caption",
        "logo",
        "sign",
        "signature",
        "watermark",
    }
)

_KEY = re.compile(r"[a-z0-9-]+")
_WEIGHT_SYNTAX = ("(", ")", ":")
_REQUIRED: Mapping[str, type] = {
    "label": str,
    "description": str,
    "medium": str,
    "finish": str,
    "grayscale": bool,
}
_OPTIONAL: Mapping[str, type] = {"emphasis": float, "negative": str, "default": bool}
_NOT_EMPTY = ("label", "description", "medium")


class StyleOrigin(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class StyleError(ValueError):
    """A style file is invalid, or a style key is unknown."""


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    description: str
    medium: str
    finish: str
    emphasis: float | None
    negative: str
    grayscale: bool
    default: bool
    origin: StyleOrigin


@dataclass(frozen=True)
class StyleRegistry:
    styles: Mapping[str, Style]
    default: str

    def get(self, key: str | None) -> Style:
        """The style for `key`; None means the default."""
        style = self.styles.get(self.default if key is None else key)
        if style is None:
            raise StyleError(f"Unknown style {key!r}; expected one of: {', '.join(self.styles)}")
        return style

    def public(self) -> tuple[Style, ...]:
        return tuple(
            sorted(
                (s for s in self.styles.values() if s.origin is StyleOrigin.PUBLIC),
                key=lambda s: s.key,
            )
        )


def load_styles(public_dir: Path, private_dir: Path | None) -> StyleRegistry:
    public = _load_dir(public_dir, StyleOrigin.PUBLIC)
    private = _load_dir(private_dir, StyleOrigin.PRIVATE) if private_dir is not None else []
    if not public:
        raise StyleError(f"{public_dir}: no public style (the demo runs on public styles only)")

    styles: dict[str, Style] = {}
    for path, style in (*public, *private):
        if style.key in styles:
            raise StyleError(f"{path}: private style {style.key!r} shadows a public style")
        styles[style.key] = style

    defaults = [(path, s) for path, s in (*public, *private) if s.default]
    if len(defaults) != 1:
        named = ", ".join(str(path) for path, _ in defaults) or "none"
        raise StyleError(f"Exactly one style must set default = true; found {named}")
    path, default = defaults[0]
    if default.origin is StyleOrigin.PRIVATE:
        raise StyleError(f"{path}: the default style must be public")
    return StyleRegistry(MappingProxyType(styles), default.key)


def _load_dir(directory: Path, origin: StyleOrigin) -> list[tuple[Path, Style]]:
    if not directory.is_dir():
        raise StyleError(f"{directory}: the {origin} style directory does not exist")
    return [(path, _load_file(path, origin)) for path in sorted(directory.glob("*.toml"))]


def _load_file(path: Path, origin: StyleOrigin) -> Style:
    def fail(why: str) -> StyleError:
        return StyleError(f"{path}: {why}")

    if not _KEY.fullmatch(path.stem):
        raise fail(f"the style key {path.stem!r} must be lower-case letters, digits and hyphens")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise fail(f"not a readable TOML file ({exc})") from exc

    if unknown := sorted(set(data) - set(_REQUIRED) - set(_OPTIONAL)):
        raise fail(f"unknown field(s) {', '.join(unknown)}")
    if missing := sorted(set(_REQUIRED) - set(data)):
        raise fail(f"missing field(s) {', '.join(missing)}")
    for field, value in data.items():
        kind = {**_REQUIRED, **_OPTIONAL}[field]
        # TOML's bool is not a number here, and a whole number is a fine weight.
        ok = (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            if kind is float
            else isinstance(value, kind)
        )
        if not ok:
            raise fail(f"{field} must be a {kind.__name__}, not {type(value).__name__}")
    for field in _NOT_EMPTY:
        if not data[field].strip():
            raise fail(f"{field} is empty")

    emphasis = data.get("emphasis")
    if emphasis is not None and not (math.isfinite(emphasis) and emphasis > 0):
        raise fail("emphasis must be a positive number")
    negative: str = data.get("negative", "")
    for field in ("medium", "finish", "negative"):
        text: str = data.get(field, "")
        if any(c in text for c in _WEIGHT_SYNTAX):
            raise fail(f"{field} contains weight syntax ( ) or : (the renderer adds weights)")
    for field in ("medium", "finish"):
        subjects = sorted(set(re.findall(r"[a-z]+", data[field].lower())) & SUBJECT_WORDS)
        if subjects:
            raise fail(f"{field} names a subject ({', '.join(subjects)}): a style is how, not what")

    return Style(
        key=path.stem,
        label=data["label"].strip(),
        description=data["description"].strip(),
        medium=data["medium"].strip(),
        finish=data["finish"].strip(),
        emphasis=float(emphasis) if emphasis is not None else None,
        negative=negative.strip(),
        grayscale=data["grayscale"],
        default=data.get("default", False),
        origin=origin,
    )
