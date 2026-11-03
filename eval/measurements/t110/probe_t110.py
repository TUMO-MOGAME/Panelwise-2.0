"""T110 probe: why absent characters slip past no_character on Super VL. Audits the six labelled
`absent` frames DeepSeek withheld and Super VL showed, RUNS times each, with this process's code and
settings (audit_frame as the loop runs it), and prints what each step said: the described people,
the judge's person calls, the sex answers (seen), the presence answers (found), the failed checks
and the laddered verdict. Token Factory only; nothing written, nothing drawn.

    python probe_t110.py <root holding eval/> <runs>
"""

import asyncio
import io
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import httpx2
from PIL import Image

from app.core.config import Settings, withholding
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.storage import SupabaseStore
from app.verify.audit import apply_ladder, audit_frame
from app.verify.model import RenderedFrame

FRAMES = [("final-whistle", "2.3"), ("final-whistle", "4.3"), ("lost-property", "7.4"),
          ("lost-property", "9.6"), ("the-bread-van", "4.4"), ("the-lighthouse-inspector", "7.5")]


def plain(x):
    if is_dataclass(x):
        return asdict(x)
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    return x


async def main() -> None:
    root, runs = Path(sys.argv[1]), int(sys.argv[2])
    labels = json.loads((root / "eval/frame-labels.json").read_text(encoding="utf-8"))["labels"]
    settings = Settings()
    ladder = withholding(settings)
    model = NebiusChatModel.from_settings(settings)
    out = []
    async with httpx2.AsyncClient(timeout=120) as client:
        store = SupabaseStore(url=settings.supabase_url, secret_key=settings.supabase_secret_key,
                              bucket=settings.supabase_storage_bucket, client=client)
        for script, shot in FRAMES:
            bundle = json.loads((root / f"eval/labelled/{script}.json").read_text(encoding="utf-8"))
            sp, ex = load_screenplay(bundle["screenplay"]), load_extraction(bundle["extraction"])
            shots = {(s.scene_index, s.number): s for s in load_plan(bundle["plan"]).shots}
            label = next(e for e in labels if e["script"] == script and e["shot"] == shot)
            frame = next(f for f in bundle["frames"] if f["shot"] == shot and f["attempt"] == label["attempt"])
            png = await store.get(frame["asset"])
            with Image.open(io.BytesIO(png)) as image:
                width, height = image.size
            scene, number = (int(x) for x in shot.split("."))
            key = (scene - 1, number)
            planned = shots[key]
            for run in range(1, runs + 1):
                rendered = RenderedFrame(key, frame["attempt"], frame["seed"], png, width, height, "")
                audit = await audit_frame(model, rendered, planned, sp, ex)
                laddered = apply_ladder(audit, ladder)
                rec = {
                    "script": script, "shot": shot, "run": run, "label": label["label"],
                    "faults": label["faults"], "note": label.get("note", ""),
                    "shot_characters": list(planned.characters),
                    "verdict": laddered.verdict.value,
                    "failed": [f"{c.check.value}:{c.severity.value}" for c in audit.checks if not c.ok],
                    "people": [plain(p) for p in (audit.description.people if audit.description else [])],
                    "calls": [plain(p) for p in (audit.judgement.people if audit.judgement else [])],
                    "seen": [plain(s) for s in audit.seen],
                    "found": [plain(f) for f in audit.found],
                    "no_character": next((c.detail for c in audit.checks if c.check.value == "no_character"), None),
                }
                out.append(rec)
                print(json.dumps(rec), flush=True)
    (root / "t110.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    await model.aclose()


asyncio.run(main())
