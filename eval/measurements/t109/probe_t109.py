"""T109 probe: why the describer's answer fails its schema on Super VL. For each asset in
/tmp/t109_assets.txt ("label asset" per line), sends describe_frame's exact first call (the prompt,
the schema instruction, json_schema strict, temperature 0, max_tokens 4096) RUNS times and records
finish_reason, tokens, length and the validation error; every raw answer is saved to /tmp/t109/.
Token Factory only; nothing written to the database, nothing drawn."""

import asyncio
import base64
import dataclasses
import json
import os
import sys

import httpx2
from pydantic import ValidationError

from app.core.config import Settings
from app.llm import NebiusChatModel
from app.llm.client import Tier
from app.llm.structured import _with_schema
from app.storage import SupabaseStore
from app.verify.audit import DESCRIBE_PROMPT
from app.verify.schema import FrameDescription

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


async def one(model, label, image, run, out):
    schema = FrameDescription.model_json_schema()
    messages = [
        {"role": "system", "content": DESCRIBE_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    fmt = {"type": "json_schema", "json_schema": {"name": "FrameDescription", "schema": schema, "strict": True}}
    try:
        r = await model.chat(_with_schema(messages, schema), Tier.VISION, temperature=0.0, max_tokens=4096,
                             response_format=fmt)
    except Exception as exc:  # noqa: BLE001 - a probe records every failure
        out.append({"label": label, "run": run, "exception": f"{type(exc).__name__}: {exc}"})
        return
    name = f"{label.replace(':', '__')}-r{run}.txt"
    open(f"/tmp/t109/{name}", "w", encoding="utf-8").write(r.content)
    rec = {"label": label, "run": run, "finish": r.finish_reason, "chars": len(r.content),
           "usage": dataclasses.asdict(r.usage) if dataclasses.is_dataclass(r.usage) else str(r.usage),
           "model": r.model}
    try:
        FrameDescription.model_validate_json(r.content)
        rec["valid"] = True
    except ValidationError as exc:
        rec["valid"] = False
        rec["errors"] = [{"type": e["type"], "loc": e["loc"], "msg": e["msg"][:160]} for e in exc.errors()[:5]]
    out.append(rec)
    print(json.dumps(rec), flush=True)


async def main():
    s = Settings()
    os.makedirs("/tmp/t109", exist_ok=True)
    model = NebiusChatModel.from_settings(s)
    out = []
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        jobs = []
        for line in open("/tmp/t109_assets.txt", encoding="utf-8"):
            if not line.strip():
                continue
            label, asset = line.split()
            png = await store.get(asset)
            image = f"data:image/png;base64,{base64.b64encode(png).decode()}"
            jobs += [(label, image, run) for run in range(1, RUNS + 1)]
    sem = asyncio.Semaphore(2)

    async def guarded(j):
        async with sem:
            await one(model, *j, out)

    await asyncio.gather(*(guarded(j) for j in jobs))
    json.dump(out, open("/tmp/t109/results.json", "w"), indent=1)
    await model.aclose()


asyncio.run(main())
