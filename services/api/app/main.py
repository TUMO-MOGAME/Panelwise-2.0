"""The Panelwise API. Run: uv run uvicorn app.main:app"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

import httpx2
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import errors
from app.api.v1 import health, projects
from app.core.auth import SupabaseJwtVerifier, TokenVerifier
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.attempt import RendererFactory
from app.jobs import fail_interrupted, fail_interrupted_frames
from app.limits.usage import record_usage
from app.llm import LLMConfigError, NebiusChatModel
from app.storage import AssetStore, SupabaseStore
from app.storyboard.fal import fal_factory
from app.storyboard.styles import PUBLIC_STYLES, StyleError, StyleRegistry, load_styles

log = logging.getLogger(__name__)


async def sweep(sessions: async_sessionmaker[AsyncSession]) -> None:
    """web.md §4.1: a job still QUEUED or RUNNING at startup was cut off by the restart, and so was
    a frame still rendering or auditing (T021); both halves in one transaction. If the database is
    unreachable, log and start anyway: the health check reports it, and the next start sweeps."""
    try:
        async with sessions() as session, session.begin():
            count = await fail_interrupted(session)
            frames = await fail_interrupted_frames(session)
    except Exception as exc:
        log.warning("restart sweep skipped: the database is unreachable (%s)", type(exc).__name__)
        return
    if count or frames:
        log.info("restart sweep: %d job(s) and %d frame(s) marked failed", count, frames)


class _Unset:
    pass


UNSET = _Unset()


def create_app(
    settings: Settings | None = None,
    *,
    verifier: TokenVerifier | _Unset | None = UNSET,
    store: AssetStore | _Unset | None = UNSET,
    model: NebiusChatModel | _Unset | None = UNSET,
    renderer_factory: RendererFactory | None = None,
    fal: bool = False,
) -> FastAPI:
    """The app. `verifier` and `store` default to Supabase's, built from settings (None when
    SUPABASE_URL or its secret key is unset: the routes then answer 503); `model` defaults to
    Token Factory's (None without NEBIUS_API_KEY: a job then fails at once); `renderer_factory` is
    given by a test, or built for fal.ai (storyboard.md §3.5) only with `fal=True` -- the
    module's `app`, never a test's -- when FAL_KEY and the store are set and the public styles
    load; else None ("Try another render" and "Make the comic" answer 503, the upload's job ends
    at planning)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # The engine connects lazily, on first use -- building it never touches the network.
        # Deployed, DATABASE_URL is Supabase's session pooler (docs/design/deploy.md §6).
        engine = make_engine(settings)
        sessions = make_sessions(engine)

        async def postgres() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        app.state.health_checks = {"postgres": postgres}
        app.state.sessions = sessions
        client = httpx2.AsyncClient(timeout=30)
        url, key = settings.supabase_url, settings.supabase_secret_key
        app.state.verifier = (
            (SupabaseJwtVerifier(supabase_url=url, client=client) if url else None)
            if isinstance(verifier, _Unset)
            else verifier
        )
        app.state.store = (
            (
                SupabaseStore(
                    url=url, secret_key=key, bucket=settings.supabase_storage_bucket, client=client
                )
                if url and key
                else None
            )
            if isinstance(store, _Unset)
            else store
        )
        if isinstance(model, _Unset):
            try:
                app.state.model = NebiusChatModel.from_settings(settings)
            except LLMConfigError:
                app.state.model = None
            else:  # every answer's tokens count toward the month (limits.md §4, T069)
                app.state.model.on_usage = partial(record_usage, sessions)
        else:
            app.state.model = model
        # The styles load whether or not there's a renderer: a storyboard drawn earlier can still
        # be exported, in its style (storyboard.md §3.4 Style).
        app.state.styles = None
        try:
            private = settings.panelwise_private_styles
            app.state.styles = load_styles(PUBLIC_STYLES, Path(private) if private else None)
        except StyleError, OSError:
            log.exception("the styles didn't load: no renderer and no storyboard PDF")
        app.state.renderer_factory = renderer_factory
        styles: StyleRegistry | None = app.state.styles
        store_ = app.state.store
        if renderer_factory is None and fal and settings.fal_key and store_ and styles:
            app.state.renderer_factory = fal_factory(styles, store_, client, settings)
        tasks: set[asyncio.Task[None]] = set()  # running jobs: one reference each, never GC'd
        app.state.tasks = tasks
        await sweep(sessions)
        try:
            yield
        finally:
            # A job cut off here stays RUNNING; the next start's sweep fails it (web.md §4.1).
            for task in list(tasks):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(model, _Unset) and app.state.model is not None:
                await app.state.model.aclose()
            await client.aclose()
            await engine.dispose()

    app = FastAPI(title="Panelwise API", lifespan=lifespan)
    app.state.settings = settings
    errors.install(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    return app


app = create_app(fal=True)
