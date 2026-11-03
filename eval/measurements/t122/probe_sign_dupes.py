"""Two facts for T122's contract: (1) a path asked twice in one batch is answered twice, position by
position; (2) the batch link has the single call's form: the same path up to "?token=". Signing
writes nothing.   python probe_sign_dupes.py <project id>"""

import asyncio
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
    a, b = [r.asset for r in rows if r.asset][:2]
    base = s.supabase_url.rstrip("/")
    h = {"Authorization": f"Bearer {s.supabase_secret_key}", "apikey": s.supabase_secret_key}
    bucket = s.supabase_storage_bucket
    async with httpx2.AsyncClient(timeout=60) as c:
        single = (await c.post(f"{base}/storage/v1/object/sign/{bucket}/{a}", json={"expiresIn": 60}, headers=h)).json()["signedURL"]
        asked = [a, b, a]
        batch = (await c.post(f"{base}/storage/v1/object/sign/{bucket}", json={"expiresIn": 60, "paths": asked}, headers=h)).json()
        print("answers:", len(batch), "for", len(asked), "asked")
        print("positions echo the paths:", [item["path"] for item in batch] == asked)
        print("the duplicate is signed both times:", bool(batch[0]["signedURL"]) and bool(batch[2]["signedURL"]))
        print("same form as the single call (before ?token=):", batch[0]["signedURL"].split("?")[0] == single.split("?")[0])
        ok = (await c.get(f"{base}/storage/v1{batch[2]['signedURL']}")).status_code
        print("the batch link opens the image:", ok)


asyncio.run(main())
