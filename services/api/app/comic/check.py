"""The comic's local check (comic.md §4a *The local check*; T064): make a T062 copy's comic with the
sketch renderer and the real audit, so the reader has a real comic before any image model exists.

It refuses a real project: only a T062 copy ("… (architecture check)") in the dev bucket. A sketch
comic shows the path a comic takes, not a grounded one. It spends the audit calls of every panel
not already accepted: run it only with the owner's go-ahead.

    uv run python -m app.comic.check <project-id>
"""

import argparse
import asyncio
import sys
import uuid

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.job import ComicRefused, run_comic_job, start_comic
from app.comic.rows import ComicRow
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.check import DEV_BUCKET, CheckRefused, SketchRenderer
from app.frames.model import AuditTarget, FrameAuditRow
from app.jobs import JobRow
from app.llm import NebiusChatModel
from app.projects.model import ProjectRow
from app.storage import AssetStore, SupabaseStore

COPY_SUFFIX = " (architecture check)"  # T062's copies, never a real project


async def run_comic_check(
    sessions: async_sessionmaker[AsyncSession],
    store: AssetStore,
    model: NebiusChatModel,
    project_id: uuid.UUID,
    *,
    bucket: str,
) -> uuid.UUID:
    """Refuses (nothing written) unless the bucket is the dev one and the project is a planned
    T062 copy; then creates the comic job and runs it to the end. Returns the job's id."""
    if bucket != DEV_BUCKET:
        raise CheckRefused(f"the comic check runs only against {DEV_BUCKET!r}, not {bucket!r}")
    async with sessions() as session:
        project = await session.get(ProjectRow, project_id)
    if project is None or not project.title.endswith(COPY_SUFFIX):
        raise CheckRefused("the comic check runs only on an architecture-check copy (T062)")
    if project.plan is None:
        raise CheckRefused("that project has no plan to draw")
    try:
        async with sessions() as session, session.begin():
            job = await start_comic(session, project.id, project.owner, renderer=True, store=True)
    except ComicRefused as refused:  # a comic already running, or the copy's storyboard not done
        raise CheckRefused(f"the comic can't start: {refused.code}") from refused
    await run_comic_job(
        job.id,
        sessions=sessions,
        store=store,
        model=model,
        factory=lambda screenplay, extraction: SketchRenderer(store),
    )
    return job.id


async def _main(project_id: uuid.UUID) -> int:
    settings = Settings()
    if not (settings.supabase_url and settings.supabase_secret_key):
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are needed (the dev bucket).", file=sys.stderr)
        return 2
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    try:
        async with httpx2.AsyncClient(timeout=60) as client:
            store = SupabaseStore(
                url=settings.supabase_url,
                secret_key=settings.supabase_secret_key,
                bucket=settings.supabase_storage_bucket,
                client=client,
            )
            model = NebiusChatModel.from_settings(settings)
            try:
                job_id = await run_comic_check(
                    sessions, store, model, project_id, bucket=settings.supabase_storage_bucket
                )
            except CheckRefused as exc:
                print(f"refused: {exc}", file=sys.stderr)
                return 2
            async with sessions() as session:
                job = await session.get(JobRow, job_id)
                comic = await session.get(ComicRow, project_id)
                audits = (
                    await session.scalars(
                        select(FrameAuditRow)
                        .where(
                            FrameAuditRow.job_id == job_id,
                            FrameAuditRow.target == AuditTarget.COMIC.value,
                        )
                        .order_by(
                            FrameAuditRow.scene_index,
                            FrameAuditRow.shot_number,
                            FrameAuditRow.attempt,
                        )
                    )
                ).all()
    finally:
        await engine.dispose()
    if job is None:
        print(f"job {job_id} is gone", file=sys.stderr)
        return 1
    print(f"job {job_id}: {job.state}" + (f" ({job.error})" if job.error else ""))
    tried: dict[tuple[int, int], list[str]] = {}
    for a in audits:
        tried.setdefault((a.scene_index, a.shot_number), []).append(f"{a.attempt}:{a.verdict}")
    for (scene, shot), verdicts in tried.items():
        print(f"panel {scene}.{shot}: {', '.join(verdicts)}")
    if comic is not None and comic.job_id == job_id:
        withheld = [
            f"{p['shot'][0]}.{p['shot'][1]}"
            for page in comic.layout["pages"]
            for p in page["panels"]
            if p["withheld"]
        ]
        print(f"comic: {len(comic.pages)} pages, pdf {comic.pdf}")
        print(f"withheld panels: {', '.join(withheld) or 'none'}")
    return 0 if job.state == "done" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.comic.check",
        description="Make a T062 copy's comic with the sketch renderer and the real audit.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.project_id)))


if __name__ == "__main__":
    main()
