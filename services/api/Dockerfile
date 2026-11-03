# Panelwise API. Versions pinned per PLAN.md § Technical Context.
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.14.7-slim-trixie
COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /srv/api

# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Migrations: the CMD below runs them before the server starts (docs/design/deploy.md §6).
COPY alembic.ini ./
COPY migrations ./migrations
# The comic lettering font (docs/design/comic.md §2); a missing font fails the comic job.
COPY assets ./assets
# The public styles (docs/design/deploy.md §6); the renderer loads them at start-up.
COPY styles ./styles

RUN useradd --system --uid 10001 panelwise
USER panelwise

EXPOSE 8000
# Render sets PORT (10000); locally and in compose it's 8000.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/v1/health', timeout=4).status == 200 else 1)"
# Migrations first, then the server: the API runs one instance on Render, so nothing races the
# migration. A failed migration exits before serving, so the deploy
# never turns healthy and Render keeps the previous one (docs/design/deploy.md §4, §6).
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
