"""Save a project's newest comic pages to /tmp/comic/page<N>.png.  python fetch_comic.py <project id>"""

import asyncio
import os
import sys
import uuid

import httpx2
from sqlalchemy import select

from app.comic.rows import ComicRow
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.storage import SupabaseStore


async def main() -> None:
    s = Settings()
    engine = make_engine(s)
    os.makedirs("/tmp/comic", exist_ok=True)
    async with make_sessions(engine)() as session:
        row = (await session.execute(select(ComicRow).where(ComicRow.project_id == uuid.UUID(sys.argv[1])))).scalars().first()
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        for i, path in enumerate(row.pages, 1):
            open(f"/tmp/comic/page{i}.png", "wb").write(await store.get(path))
            print(f"page{i}.png", path)
    await engine.dispose()


asyncio.run(main())
