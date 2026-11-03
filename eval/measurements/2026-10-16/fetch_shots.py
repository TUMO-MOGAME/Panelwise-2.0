"""Save the stored storyboard drawings of the given title:shot pairs (newest run per title, every
attempt) to /work/fs/, named title__shot-aN.png, and print each one's described people.

    python fetch_shots.py the-lighthouse-inspector:4.2 the-night-taxi:6.3 ...
"""

import asyncio
import os
import sys

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.projects.model import ProjectRow
from app.storage import SupabaseStore


async def main() -> None:
    wanted = [a.split(":") for a in sys.argv[1:]]
    s = Settings()
    engine = make_engine(s)
    os.makedirs("/work/fs", exist_ok=True)
    async with make_sessions(engine)() as session:
        projects = (await session.execute(select(ProjectRow).order_by(ProjectRow.created_at.desc()))).scalars().all()
        newest: dict[str, ProjectRow] = {}
        for p in projects:
            if p.plan is not None:
                newest.setdefault(p.title.split(" (")[0], p)
        rows = []
        for title, shot in wanted:
            si, n = (int(x) for x in shot.split("."))
            rows += [
                (title, shot, r)
                for r in (await session.execute(select(FrameAuditRow).where(
                    FrameAuditRow.project_id == newest[title].id, FrameAuditRow.target == "storyboard",
                    FrameAuditRow.scene_index == si - 1, FrameAuditRow.shot_number == n,
                ).order_by(FrameAuditRow.attempt))).scalars().all()
            ]
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        for title, shot, r in rows:
            name = f"{title}__{shot}-a{r.attempt}.png"
            open(f"/work/fs/{name}", "wb").write(await store.get(r.frame_asset))
            people = (r.description or {}).get("people", [])
            print(name, r.verdict, [f"{p['position']}: {p['appearance']}" for p in people])
    await engine.dispose()


asyncio.run(main())
