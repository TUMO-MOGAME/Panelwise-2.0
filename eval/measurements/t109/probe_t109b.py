"""T109 candidates: the describer's first call with one change each, on the frames that loop
(/tmp/t109_assets.txt) and on control frames that answer fine (/tmp/t109_controls.txt).
Variants: caps (maxItems/maxLength in the schema), penalty (frequency_penalty), prompt (one
sentence), warm (temperature 0.3). Records finish, tokens, validity and the description's
shape (people count, setting, objects, text) to compare with the control's stored description.
Token Factory only; nothing written, nothing drawn.   python probe_t109b.py <variant,...> <runs>"""

import asyncio
import base64
import copy
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

VARIANTS = sys.argv[1].split(",")
RUNS = int(sys.argv[2])
EXTRA = (" Name each kind of object once, even when there are several of it; list at most 20 "
         "objects. Write each piece of writing once, and stop when the writing repeats.")


def capped(schema: dict) -> dict:
    s = copy.deepcopy(schema)
    props = s["properties"]
    props["people"]["maxItems"] = 24
    props["objects"]["maxItems"] = 40
    props["text"]["maxItems"] = 40
    props["text"]["items"]["maxLength"] = 100
    defs = s["$defs"]
    defs["SeenPerson"]["properties"]["appearance"]["maxLength"] = 200
    defs["SeenObject"]["properties"]["name"]["maxLength"] = 60
    return s


async def call(model, variant, image):
    schema = FrameDescription.model_json_schema()
    prompt = DESCRIBE_PROMPT + (EXTRA if variant == "prompt" else "")
    send = capped(schema) if variant == "caps" else schema
    # capsfmt: the caps in the decoding grammar only; the prompt's schema text unchanged
    grammar = capped(schema) if variant == "capsfmt" else send
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    body = {
        "model": model.model_for(Tier.VISION),
        "messages": _with_schema(messages, send),
        "temperature": 0.3 if variant == "warm" else 0.0,
        "max_tokens": 4096,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "FrameDescription", "schema": grammar, "strict": True}},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if variant == "penalty":
        body["frequency_penalty"] = 0.5
    return await model._post(body, body["model"])


async def one(model, variant, label, image, run, out):
    try:
        data = await call(model, variant, image)
    except Exception as exc:  # noqa: BLE001 - a probe records every failure
        rec = {"variant": variant, "label": label, "run": run, "exception": f"{type(exc).__name__}: {exc}"}
        out.append(rec)
        print(json.dumps(rec), flush=True)
        return
    choice = data["choices"][0]
    content = choice["message"].get("content") or ""
    open(f"/tmp/t109b/{variant}-{label.replace(':', '__')}-r{run}.txt", "w", encoding="utf-8").write(content)
    rec = {"variant": variant, "label": label, "run": run, "finish": choice.get("finish_reason"),
           "completion": data.get("usage", {}).get("completion_tokens")}
    try:
        d = FrameDescription.model_validate_json(content)
        rec.update(valid=True, people=len(d.people), setting=d.setting.value if hasattr(d.setting, "value") else d.setting,
                   objects=len(d.objects), distinct_objects=len({o.name for o in d.objects}), text=d.text[:4])
    except ValidationError as exc:
        rec.update(valid=False, error=exc.errors()[0]["msg"][:120])
    out.append(rec)
    print(json.dumps(rec), flush=True)


async def main():
    s = Settings()
    os.makedirs("/tmp/t109b", exist_ok=True)
    model = NebiusChatModel.from_settings(s)
    out = []
    jobs = []
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(url=s.supabase_url, secret_key=s.supabase_secret_key,
                              bucket=s.supabase_storage_bucket, client=client)
        for path in ("/tmp/t109_assets.txt", "/tmp/t109_controls.txt"):
            if not os.path.exists(path):
                continue
            for line in open(path, encoding="utf-8"):
                if not line.strip():
                    continue
                label, asset = line.split()
                png = await store.get(asset)
                image = f"data:image/png;base64,{base64.b64encode(png).decode()}"
                runs = RUNS if path.endswith("assets.txt") else 1
                jobs += [(v, label, image, r) for v in VARIANTS for r in range(1, runs + 1)]
    sem = asyncio.Semaphore(2)

    async def guarded(j):
        async with sem:
            await one(model, *j, out)

    await asyncio.gather(*(guarded(j) for j in jobs))
    json.dump(out, open(f"/tmp/t109b/results-{'_'.join(VARIANTS)}.json", "w"), indent=1)
    await model.aclose()


asyncio.run(main())
