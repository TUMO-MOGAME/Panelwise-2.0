"""Settings, read from the environment (see .env.example at the repo root)."""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# The repo-root .env, wherever the API is started from. In the Docker image this path
# doesn't exist and compose supplies the environment instead; a missing file is ignored.
REPO_ENV = Path(__file__).resolve().parents[4] / ".env"


if TYPE_CHECKING:
    from app.verify.model import Check


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ENV, extra="ignore")

    database_url: str = "postgresql+asyncpg://panelwise:panelwise@localhost:5432/panelwise"
    health_check_timeout_s: float = 2.0

    # Nebius Token Factory -- values measured in docs/nebius-findings.md (T001).
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_model_fast: str = "nvidia/Nemotron-3_5-Lightning"
    nebius_model_reasoning: str = "nvidia/nemotron-3-super-120b-a12b"
    # Every vision call (the describer and the agents): Nemotron 3.5 Super VL since T105 (Katlego,
    # 2026-10-17; docs/super-vl-migration.md); DeepSeek-V4.1-Flash before.
    nebius_model_vision: str = "nvidia/Nemotron-3.5-Super-VL"
    # The vision tier's thinking toggle (docs/design/vision-model.md, T105): off, measured (findings
    # § U8); blank sends nothing, as DeepSeek's calls did.
    nebius_vision_thinking: bool | None = False
    llm_request_timeout_s: float = 120.0
    # T075: a dead connection fails in 10 s, and 5 attempts ride out about 80 s of drops.
    llm_connect_timeout_s: float = 10.0
    llm_max_attempts: int = 5
    # A full render loop's attempts per frame (verify.md §4, T071): 1 while the pass rate is
    # unknown, so a systematic FAIL isn't paid for three times.
    render_max_attempts: int = Field(default=3, ge=1, le=3)
    # The rule ladder (verify.md §4; Tumo, 2026-10-13): which failed hard checks withhold a
    # frame. "all" (the default) is every hard check; "" is none, so every check only warns
    # and the card still names it; else a comma list of check names ("no_character"), the
    # rules brought back one at a time. An audit that can't run still withholds.
    audit_withhold_checks: str = "all"

    # Frames (docs/design/storyboard.md §6). The prompt's word budget, a conservative proxy for the
    # text encoder's token limit: 55 words for CLIP's 77 tokens, kept for klein (storyboard.md §10).
    comfyui_max_words: int = 55
    # The renderer: FLUX.2 [klein] 4B on fal.ai (storyboard.md §3.5; FLUX.1 [schnell] before
    # 2026-10-11). No key, no renderer: "Try another render" and "Make the comic" answer 503 and
    # the storyboard job ends at planning.
    fal_key: str = ""
    fal_model: str = "fal-ai/flux-2/klein/4b"  # storyboard.md §3.5 (2026-10-11)
    fal_timeout_s: float = 60.0
    # Frames drawn at once: fal.ai's limit for a new account is 2 (more are queued against the
    # timeout); raise it with the account's limit (storyboard.md §3.5).
    fal_concurrency: int = Field(default=2, ge=1)
    # A directory of private style TOMLs outside the repo; empty means none. Never set on the
    # hosted demo.
    panelwise_private_styles: str = ""

    # Supabase, API side only (deploy.md §6): Storage and the token check (T053).
    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_storage_bucket: str = "panelwise"  # panelwise-dev in a local .env
    # Below Vercel's ~4.5 MB function body limit, which every upload passes through (web.md §4.1);
    # T030 may lower it.
    upload_max_bytes: int = 4_000_000

    # The hosted demo's limits (docs/design/limits.md, T069); unset or 0: off.
    llm_monthly_token_cap: int | None = None
    uploads_per_day: int | None = None
    upload_max_pages: int | None = None
    # Drawings a month, counted from frame_audits (limits.md §4, T030); unset or 0: off.
    image_monthly_generation_cap: int | None = None

    @field_validator(
        "llm_monthly_token_cap",
        "uploads_per_day",
        "upload_max_pages",
        "image_monthly_generation_cap",
        "nebius_vision_thinking",
        mode="before",
    )
    @classmethod
    def _blank_is_off(cls, value: object) -> object:
        # `.env.example` lists the caps with no value: an empty one means off, not an error.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("database_url")
    @classmethod
    def _asyncpg_driver(cls, url: str) -> str:
        # Parsed with SQLAlchemy's own URL parser, the one the engine uses: a "?" or "&" inside
        # the password is part of the password, not the start of the query (PR #13 review).
        parsed = make_url(url)
        # Supabase hands out postgresql:// (or postgres://); the async engine needs +asyncpg.
        if parsed.drivername in ("postgresql", "postgres"):
            parsed = parsed.set(drivername="postgresql+asyncpg")
        # libpq's sslmode= (which Supabase suggests) is ssl= to asyncpg, same values; asyncpg
        # rejects an unknown sslmode keyword at connect time, so the API would never be healthy.
        if "sslmode" in parsed.query:
            query = dict(parsed.query)
            query["ssl"] = query.pop("sslmode")
            parsed = parsed.set(query=query)
        return parsed.render_as_string(hide_password=False)

    @model_validator(mode="after")
    def _ladder_names_hard_checks(self) -> Settings:
        """T094: a misspelt AUDIT_WITHHOLD_CHECKS stops the API starting, never a request."""
        withholding(self)
        return self


def withholding(settings: Settings) -> frozenset[Check] | None:
    """`audit_withhold_checks` read (verify.md §4): None for "all" (every hard check withholds),
    else the checks that do; an unknown name is a ValueError, so a typo can't switch a rule off."""
    from app.verify.model import Check  # here: app.verify imports this module

    raw = settings.audit_withhold_checks.strip()
    if raw.lower() == "all":
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    from app.verify.audit import _SEVERITY  # pyright: ignore[reportPrivateUsage]
    from app.verify.model import Severity

    # Only a hard check can withhold: a soft name here would switch nothing on.
    known = {c.value for c, severity in _SEVERITY.items() if severity is Severity.HARD}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"AUDIT_WITHHOLD_CHECKS names no hard check: {', '.join(unknown)}")
    return frozenset(Check(n) for n in names)
