"""Contact sheets of the frames /work/twice.json flags (split or copies): 4 a sheet, each 640x360
with its title, shot, attempt and the answer's panels/copies printed above it. /work/tw/sheetNN.png"""

import asyncio
import io
import json
import os

import httpx2
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.storage import SupabaseStore


async def main() -> None:
    rows = [r for r in json.load(open("/work/twice.json"))
            if "error" not in r["answer"] and (r["answer"]["panels"] > 1 or r["answer"]["copies"])]
    os.makedirs("/work/tw", exist_ok=True)
    s = Settings()
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        tiles = []
        for r in rows:
            img = Image.open(io.BytesIO(await store.get(r["asset"]))).convert("RGB").resize((640, 360))
            tile = Image.new("RGB", (640, 390), "white")
            tile.paste(img, (0, 30))
            a = r["answer"]
            ImageDraw.Draw(tile).text(
                (4, 6), f"{r['title'][:20]} {r['shot']} a{r['attempt']}  panels={a['panels']} copies={a['copies'][:3]}",
                fill="black")
            tiles.append(tile)
    for n in range(0, len(tiles), 4):
        sheet = Image.new("RGB", (1290, 790), "grey")
        for k, tile in enumerate(tiles[n:n + 4]):
            sheet.paste(tile, ((k % 2) * 650, (k // 2) * 400))
        sheet.save(f"/work/tw/sheet{n // 4:02d}.png")
    print(len(tiles), "tiles")


asyncio.run(main())
