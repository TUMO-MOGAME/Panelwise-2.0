"""The batch sign call's answer, compared with the single call's: keys, order, the link's form,
and what a missing path returns. Signing writes nothing.   python probe_sign_shape.py <project id>"""

import asyncio
import json
import sys
import uuid

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameRow


async def main() -> None:
    s = Settings()
    engine = make_engine(s)
    async with make_sessions(engine)() as session:
        rows = (await session.execute(select(FrameRow).where(FrameRow.project_id == uuid.UUID(sys.argv[1])))).scalars().all()
    await engine.dispose()
    paths = [r.asset for r in rows if r.asset][:3]
    base = s.supabase_url.rstrip("/")
    h = {"Authorization": f"Bearer {s.supabase_secret_key}", "apikey": s.supabase_secret_key}
    bucket = s.supabase_storage_bucket
    async with httpx2.AsyncClient(timeout=60) as c:
        single = await c.post(f"{base}/storage/v1/object/sign/{bucket}/{paths[0]}", json={"expiresIn": 60}, headers=h)
        print("single:", single.status_code, json.dumps(single.json())[:60], "...")
        asked = [paths[2], "frames/does-not-exist.png", paths[0], paths[1]]
        batch = await c.post(f"{base}/storage/v1/object/sign/{bucket}", json={"expiresIn": 60, "paths": asked}, headers=h)
        print("batch:", batch.status_code)
        for asked_path, item in zip(asked, batch.json()):
            shown = {k: (v[:40] + "..." if isinstance(v, str) and len(v) > 40 else v) for k, v in item.items()}
            print("  asked", asked_path[-12:], "->", shown)
        empty = await c.post(f"{base}/storage/v1/object/sign/{bucket}", json={"expiresIn": 60, "paths": []}, headers=h)
        print("empty paths:", empty.status_code, empty.text[:120])


asyncio.run(main())
