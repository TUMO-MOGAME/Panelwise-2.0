"""Signed URLs, measured: a project's accepted frames signed one at a time (as
GET /projects/{id}/frames does today, SupabaseStore.signed_url in a loop) against Supabase's batch
call (POST /storage/v1/object/sign/{bucket} with "paths"). Signing writes nothing.

    python probe_sign.py <project id> <rounds>
"""

import asyncio
import statistics
import sys
import time
import uuid

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameRow
from app.storage import SupabaseStore


async def main() -> None:
    project, rounds = uuid.UUID(sys.argv[1]), int(sys.argv[2])
    s = Settings()
    engine = make_engine(s)
    async with make_sessions(engine)() as session:
        rows = (await session.execute(select(FrameRow).where(FrameRow.project_id == project))).scalars().all()
    await engine.dispose()
    paths = [r.asset for r in rows if r.asset]
    print(f"{len(paths)} frames")
    base = s.supabase_url.rstrip("/")
    headers = {"Authorization": f"Bearer {s.supabase_secret_key}", "apikey": s.supabase_secret_key}
    seq, batch = [], []
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        await store.signed_url(paths[0], 3600)  # warm the connection
        for _ in range(rounds):
            t = time.perf_counter()
            for p in paths:
                await store.signed_url(p, 3600)
            seq.append(time.perf_counter() - t)

            t = time.perf_counter()
            r = await client.post(f"{base}/storage/v1/object/sign/{s.supabase_storage_bucket}",
                                  json={"expiresIn": 3600, "paths": paths}, headers=headers)
            r.raise_for_status()
            signed = r.json()
            batch.append(time.perf_counter() - t)
            assert len(signed) == len(paths) and all(x.get("signedURL") for x in signed), signed[:2]
    print(f"sequential: median {statistics.median(seq)*1000:.0f} ms, per URL {statistics.median(seq)/len(paths)*1000:.0f} ms  {[round(x*1000) for x in seq]}")
    print(f"batch:      median {statistics.median(batch)*1000:.0f} ms  {[round(x*1000) for x in batch]}")


asyncio.run(main())
