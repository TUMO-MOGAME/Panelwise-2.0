"""T105 measurement (docs/design/vision-model.md §4, §9): today's audit_frame on every stored attempt of
one project, as app.verify.reaudit runs it, writing nothing to the database or Storage. Records per
attempt: the raw and hosted-ladder verdicts, failed checks, the description, tokens, seconds, models.

    PYTHONPATH=. uv run python measure.py <project-id> <out.json>   (cwd: services/api)
The vision model and its thinking toggle come from NEBIUS_MODEL_VISION / NEBIUS_VISION_THINKING.
"""

import asyncio
import dataclasses
import io
import json
import os
import sys
import time
import uuid

import httpx2
from PIL import Image
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storage import SupabaseStore
from app.verify.audit import apply_ladder, audit_frame
from app.verify.model import Check, RenderedFrame

HOSTED = frozenset({Check("drawn_sex"), Check("no_character")})
CONCURRENCY = 4


def dump(value: object) -> object:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[no-any-return]
    if dataclasses.is_dataclass(value):
        return json.loads(json.dumps(dataclasses.asdict(value), default=str))  # type: ignore[arg-type]
    return str(value)


async def main(project_id: uuid.UUID, out_path: str) -> None:
    s = Settings()
    engine = make_engine(s)
    sessions = make_sessions(engine)
    model = NebiusChatModel.from_settings(s)
    async with sessions() as session:
        project = await session.get(ProjectRow, project_id)
        assert project is not None and project.plan is not None
        rows = list(
            await session.scalars(
                select(FrameAuditRow)
                .where(FrameAuditRow.project_id == project_id)
                .order_by(
                    FrameAuditRow.target,
                    FrameAuditRow.scene_index,
                    FrameAuditRow.shot_number,
                    FrameAuditRow.attempt,
                )
            )
        )
    rows = rows[: int(os.environ.get("LIMIT", "0")) or None]
    screenplay = load_screenplay(project.screenplay)  # type: ignore[arg-type]
    extraction = load_extraction(project.extraction)
    shots = {(x.scene_index, x.number): x for x in load_plan(project.plan).shots}
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(
            url=s.supabase_url,
            secret_key=s.supabase_secret_key,
            bucket=s.supabase_storage_bucket,
            client=client,
        )

        async def one(row: FrameAuditRow) -> dict[str, object]:
            key = (row.scene_index, row.shot_number)
            rec: dict[str, object] = {
                "target": row.target, "scene": row.scene_index, "shot": row.shot_number,
                "attempt": row.attempt, "asset": row.frame_asset, "stored": row.verdict,
            }
            async with sem:
                png = await store.get(row.frame_asset)
                with Image.open(io.BytesIO(png)) as image:
                    width, height = image.size
                frame = RenderedFrame(key, row.attempt, row.seed, png, width, height, "")
                started = time.monotonic()
                try:
                    audit = await audit_frame(model, frame, shots[key], screenplay, extraction)
                except Exception as exc:  # recorded, never hidden
                    rec.update(secs=round(time.monotonic() - started, 2), error=f"{type(exc).__name__}: {exc}"[:400])
                    return rec
                rec["secs"] = round(time.monotonic() - started, 2)
            hosted = apply_ladder(audit, HOSTED)
            rec.update(
                raw=audit.verdict.value,
                hosted=hosted.verdict.value,
                failed=[[c.check.value, c.severity.value] for c in audit.checks if not c.ok],
                usage=dump(audit.usage),
                models=list(audit.models),
                description=dump(audit.description),
                judgement=dump(audit.judgement),
                seen=[dump(x) for x in audit.seen],
                found=[dump(x) for x in audit.found],
            )
            return rec

        records = await asyncio.gather(*(one(r) for r in rows))
    await model.aclose()
    await engine.dispose()
    meta = {
        "project": str(project_id), "vision_model": s.nebius_model_vision,
        "vision_thinking": s.nebius_vision_thinking, "concurrency": CONCURRENCY,
        "attempts": len(records),
    }
    with open(out_path, "w") as f:
        json.dump({"meta": meta, "records": records}, f, indent=1)
    print(json.dumps(meta))


if __name__ == "__main__":
    asyncio.run(main(uuid.UUID(sys.argv[1]), sys.argv[2]))
