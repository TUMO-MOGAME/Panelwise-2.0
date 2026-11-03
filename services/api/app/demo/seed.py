"""The judge seed (docs/design/limits.md §4, T069): one shared judge login, and a finished copy of
the sample project in it, so a judge opens a storyboard and comic without spending anything.

    JUDGE_EMAIL=… JUDGE_PASSWORD=… python -m app.demo.seed [--from PROJECT_ID]

Run once against the hosted database (and again whenever; it is idempotent). The password comes
from the environment, never the command line, and is never printed.
"""

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from typing import cast

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.rows import ComicRow
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import AuditTarget, FrameAuditRow, FrameRow
from app.jobs import JobKind, JobRow, JobState
from app.projects.model import ProjectRow

_PAGE = 200  # users per page when looking an existing judge up


def _error_code(response: httpx2.Response) -> str:
    """GoTrue's `error_code` (e.g. `email_exists`, `weak_password`), or "" without one."""
    try:
        body: object = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    fields = cast(dict[str, object], body)
    return str(fields.get("error_code") or fields.get("code") or "")


class SeedError(RuntimeError):
    """Why the seed stopped: never the secret key or the password."""


@dataclass(frozen=True)
class Copied:
    project_id: uuid.UUID
    copied: bool  # False: the judge already had this sample


async def ensure_judge(
    client: httpx2.AsyncClient, url: str, secret: str, email: str, password: str
) -> uuid.UUID:
    """Create the judge (confirmed), or set an existing judge's password. Idempotent."""
    base = f"{url.rstrip('/')}/auth/v1/admin/users"
    headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}
    made = await client.post(
        base, headers=headers, json={"email": email, "password": password, "email_confirm": True}
    )
    if made.status_code in (200, 201):
        return uuid.UUID(made.json()["id"])
    code = _error_code(made)
    if made.status_code != 422 or code != "email_exists":
        # A weak password or a malformed email is a 422 too: say which (never the password).
        raise SeedError(f"Supabase Auth refused to create the judge ({made.status_code} {code})")
    page = 1
    while True:
        listed = await client.get(base, headers=headers, params={"page": page, "per_page": _PAGE})
        if listed.status_code != 200:
            raise SeedError(f"Supabase Auth refused to list users ({listed.status_code})")
        users = listed.json().get("users", [])
        if not users:  # an empty page is the end, whatever page size the server allows
            raise SeedError("the judge's email exists in Supabase Auth but wasn't listed")
        found = next((u for u in users if str(u.get("email", "")).lower() == email.lower()), None)
        if found is not None:
            break
        page += 1
    updated = await client.put(
        f"{base}/{found['id']}",
        headers=headers,
        json={"password": password, "email_confirm": True},  # an unconfirmed judge can't sign in
    )
    if updated.status_code != 200:
        raise SeedError(
            f"Supabase Auth refused to set the judge's password ({updated.status_code})"
        )
    return uuid.UUID(found["id"])


async def copy_sample(
    sessions: async_sessionmaker[AsyncSession], source_id: uuid.UUID, judge: uuid.UUID
) -> Copied:
    """Copy a settled project into the judge's account, once (limits.md §4): the project, a done
    storyboard job, its frames and audits, and its comic if it has one. Assets are content
    addresses, shared, never copied. Raises before writing if the source isn't settled."""
    async with sessions() as session, session.begin():
        source = await session.get(ProjectRow, source_id)
        if source is None or source.plan is None:
            raise SeedError(f"no planned project {source_id}")
        mine = await session.scalar(
            select(ProjectRow).where(
                ProjectRow.owner == judge, ProjectRow.pdf_path == source.pdf_path
            )
        )
        if mine is not None:
            return Copied(mine.id, copied=False)
        upload = await session.scalar(
            select(JobRow)
            .where(JobRow.project_id == source_id, JobRow.kind == JobKind.STORYBOARD)
            .order_by(JobRow.created_at.desc(), JobRow.id.desc())
            .limit(1)
        )
        frames = list(
            await session.scalars(select(FrameRow).where(FrameRow.project_id == source_id))
        )
        if (
            upload is None
            or upload.state != JobState.DONE
            or not frames
            or any(f.state in ("rendering", "auditing") for f in frames)
        ):
            raise SeedError("the source's storyboard hasn't settled: copy a finished one")
        audits = list(
            await session.scalars(
                select(FrameAuditRow).where(FrameAuditRow.project_id == source_id)
            )
        )
        comic = await session.get(ComicRow, source_id)

        copy = ProjectRow(
            id=uuid.uuid4(),
            owner=judge,
            title=source.title,
            pdf_path=source.pdf_path,
            screenplay=source.screenplay,
            extraction=source.extraction,
            plan=source.plan,
            created_at=source.created_at,  # so the sample never counts toward the day's uploads
        )
        session.add(copy)
        await session.flush()
        board = JobRow(
            id=uuid.uuid4(),
            project_id=copy.id,
            kind=JobKind.STORYBOARD,
            state=JobState.DONE,
            stage=upload.stage,
            progress=100,
        )
        session.add(board)
        comic_job: JobRow | None = None
        if comic is not None:
            comic_job = JobRow(
                id=uuid.uuid4(),
                project_id=copy.id,
                kind=JobKind.COMIC,
                state=JobState.DONE,
                stage="rendering",
                progress=100,
            )
            session.add(comic_job)
        await session.flush()
        for f in frames:
            session.add(
                FrameRow(
                    project_id=copy.id,
                    scene_index=f.scene_index,
                    shot_number=f.shot_number,
                    state=f.state,
                    attempt=f.attempt,
                    job_id=board.id,
                    asset=f.asset,
                    withheld_check=f.withheld_check,
                    failure=f.failure,
                )
            )
        for a in audits:
            is_comic = a.target == AuditTarget.COMIC.value
            if is_comic and comic_job is None:
                continue  # a comic attempt with no stored comic: nothing reads it
            session.add(
                FrameAuditRow(
                    project_id=copy.id,
                    job_id=comic_job.id if is_comic and comic_job else board.id,
                    target=a.target,
                    scene_index=a.scene_index,
                    shot_number=a.shot_number,
                    attempt=a.attempt,
                    seed=a.seed,
                    frame_asset=a.frame_asset,
                    description=a.description,
                    judgement=a.judgement,
                    checks=a.checks,
                    positions=a.positions,
                    # The agents' answers (T095, T099, T104), so `recheck` decides the copy as the
                    # source: without them it would read every agent check as not asked.
                    seen=a.seen,
                    found=a.found,
                    layout=a.layout,
                    verdict=a.verdict,
                    models=a.models,
                    prompt_tokens=a.prompt_tokens,
                    completion_tokens=a.completion_tokens,
                    # T030: the source's time, so a copy never counts as this month's drawings.
                    created_at=a.created_at,
                )
            )
        if comic is not None and comic_job is not None:
            session.add(
                ComicRow(
                    project_id=copy.id,
                    job_id=comic_job.id,
                    layout=comic.layout,
                    pages=list(comic.pages),
                    pdf=comic.pdf,
                )
            )
        return Copied(copy.id, copied=True)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.demo.seed", description=__doc__)
    parser.add_argument("--from", dest="source", type=uuid.UUID, help="a settled project to copy")
    args = parser.parse_args(argv)
    email, password = os.environ.get("JUDGE_EMAIL", ""), os.environ.get("JUDGE_PASSWORD", "")
    if not email or not password:
        print("Set JUDGE_EMAIL and JUDGE_PASSWORD in the environment.", file=sys.stderr)
        return 2
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are needed.", file=sys.stderr)
        return 2
    try:
        async with httpx2.AsyncClient(timeout=30) as client:
            judge = await ensure_judge(
                client, settings.supabase_url, settings.supabase_secret_key, email, password
            )
        print(f"judge: {email} ({judge})")
        if args.source is not None:
            engine = make_engine(settings)
            try:
                copied = await copy_sample(make_sessions(engine), args.source, judge)
            finally:
                await engine.dispose()
            verb = "copied" if copied.copied else "already there (not updated)"
            print(f"sample: {verb}, project {copied.project_id}")
    except SeedError as error:
        print(f"seed stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
