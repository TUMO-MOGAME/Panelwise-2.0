"""Exports what eval/frame-labels.json's frames need to be audited again anywhere: for each labelled
script, the stored project (the newest run of that title on this machine) as one file under
eval/labelled/: its id, screenplay, extraction and plan, and for each labelled attempt its drawing's
Storage path, seed and the audit stored with it (description, judgement, checks, verdict, models,
the agents' answers). No model call, no write to the database, no cost.

    # in the API container, with the repo mounted at /work:
    python /work/eval/tools/export_labelled.py /work
"""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import AuditTarget, FrameAuditRow
from app.projects.model import ProjectRow

COLUMNS = (
    FrameAuditRow.scene_index, FrameAuditRow.shot_number, FrameAuditRow.attempt, FrameAuditRow.seed,
    FrameAuditRow.frame_asset, FrameAuditRow.description, FrameAuditRow.judgement,
    FrameAuditRow.checks, FrameAuditRow.verdict, FrameAuditRow.models, FrameAuditRow.seen,
    FrameAuditRow.found,
)  # fmt: skip


async def main(root: Path) -> None:
    labels = json.loads((root / "eval/frame-labels.json").read_text(encoding="utf-8"))["labels"]
    wanted: dict[str, set[tuple[int, int, int]]] = {}
    for e in labels:
        scene, number = (int(x) for x in e["shot"].split("."))
        wanted.setdefault(e["script"], set()).add((scene - 1, number, int(e["attempt"])))
    out_dir = root / "eval/labelled"
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(Settings())
    async with make_sessions(engine)() as s:
        projects = (await s.execute(select(ProjectRow).where(ProjectRow.plan.is_not(None)).order_by(ProjectRow.created_at.desc()))).scalars().all()
        newest: dict[str, ProjectRow] = {}
        for p in projects:
            newest.setdefault(p.title.split(" (")[0], p)
        for script, keys in sorted(wanted.items()):
            p = newest[script]
            rows = (await s.execute(select(*COLUMNS).where(
                FrameAuditRow.project_id == p.id, FrameAuditRow.target == AuditTarget.STORYBOARD.value,
            ))).all()
            frames = [
                {
                    "shot": f"{r.scene_index + 1}.{r.shot_number}", "attempt": r.attempt, "seed": r.seed,
                    "asset": r.frame_asset,
                    "stored_audit": {
                        "description": r.description, "judgement": r.judgement, "checks": r.checks,
                        "verdict": r.verdict, "models": r.models, "seen": r.seen, "found": r.found,
                    },
                }
                for r in sorted(rows, key=lambda r: (r.scene_index, r.shot_number, r.attempt))
                if (r.scene_index, r.shot_number, r.attempt) in keys
            ]
            missing = keys - {(int(f["shot"].split(".")[0]) - 1, int(f["shot"].split(".")[1]), f["attempt"]) for f in frames}
            if missing:
                print(f"{script}: no stored attempt for {sorted(missing)}")
            body = {
                "script": script, "project_id": str(p.id), "title": p.title,
                "created_at": p.created_at.isoformat(), "screenplay": p.screenplay,
                "extraction": p.extraction, "plan": p.plan, "frames": frames,
            }
            path = out_dir / f"{script}.json"
            path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            print(f"{script}: {len(frames)} frames, project {str(p.id)[:8]}, {path.stat().st_size // 1024} KB")
    await engine.dispose()


asyncio.run(main(Path(sys.argv[1])))
