"""T122 live: the branch's SupabaseStore.signed_urls (copied in as /tmp/t122_store.py) on a stored
project's accepted frames against the dev bucket: requests made, time, order, every link opening.
Signing writes nothing.   python live_t122.py <project id>"""

import asyncio
import importlib.util
import sys
import time
import uuid

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameRow

spec = importlib.util.spec_from_file_location("t122_store", "/tmp/t122_store.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


async def main() -> None:
    s = Settings()
    engine = make_engine(s)
    async with make_sessions(engine)() as session:
        rows = (await session.execute(select(FrameRow).where(FrameRow.project_id == uuid.UUID(sys.argv[1])))).scalars().all()
    await engine.dispose()
    paths = [r.asset for r in sorted(rows, key=lambda r: (r.scene_index, r.shot_number)) if r.asset]
    sent: list[str] = []

    async def count(request: httpx2.Request) -> None:
        sent.append(f"{request.method} {request.url.path}")

    async with httpx2.AsyncClient(timeout=60, event_hooks={"request": [count]}) as client:
        store = mod.SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                                  bucket=s.supabase_storage_bucket, client=client)
        t = time.perf_counter()
        links = await store.signed_urls(paths, 3600)
        took = time.perf_counter() - t
        print(f"{len(paths)} paths -> {len(links)} links, {len(sent)} request(s) ({sent[0]}), {took*1000:.0f} ms")
        print("in order:", all(p in link for p, link in zip(paths, links, strict=True)))
        opened = [ (await client.get(link)).status_code for link in links ]
        print("every link opens:", set(opened) == {200}, f"({opened.count(200)} of {len(links)})")


asyncio.run(main())
