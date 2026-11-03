"""The re-audit: today's audit run again on drawings already made (docs/design/verify.md §6, T071).

    python -m app.verify.reaudit <project-id> [--target storyboard|comic] [--limit N]

It writes nothing, no row and no Storage object, and draws nothing: the only spend is the audit's
Token Factory calls per logged attempt (the describer, the judge and the agents' questions). So a
change to the audit is measured on the very
drawings the old audit judged.
"""

import argparse
import asyncio
import io
import logging
import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import httpx2
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import AuditTarget, FrameAuditRow
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.script import Scene
from app.storage import AssetNotFound, AssetStore, SupabaseStore
from app.verify.audit import audit_frame
from app.verify.model import Check, RenderedFrame, Severity, Verdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reaudit:
    shot: tuple[int, int]
    attempt: int
    target: str
    before: Verdict
    after: Verdict
    failed: tuple[Check, ...]  # the hard checks the new audit failed, in Check order


async def reaudit(
    sessions: async_sessionmaker[AsyncSession],
    store: AssetStore,
    model: NebiusChatModel,
    project_id: uuid.UUID,
    *,
    target: AuditTarget | None = None,
    limit: int | None = None,
) -> list[Reaudit]:
    """Every logged attempt of the project (one target, or both), in (target, scene, shot,
    attempt) order, the first `limit` of them, audited again against its shot. A drawing that is
    gone from Storage is logged and skipped."""
    async with sessions() as session:
        project = await session.get(ProjectRow, project_id)
        if project is None or project.plan is None or project.extraction is None:
            raise ValueError(f"project {project_id} has no plan")
        query = (
            select(FrameAuditRow)
            .where(FrameAuditRow.project_id == project_id)
            .order_by(
                FrameAuditRow.target,
                FrameAuditRow.scene_index,
                FrameAuditRow.shot_number,
                FrameAuditRow.attempt,
            )
            .limit(limit)
        )
        if target is not None:
            query = query.where(FrameAuditRow.target == target.value)
        rows = list(await session.scalars(query))
    screenplay = load_screenplay(project.screenplay)  # type: ignore[arg-type]
    extraction = load_extraction(project.extraction)
    shots = {(s.scene_index, s.number): s for s in load_plan(project.plan).shots}

    out: list[Reaudit] = []
    for row in rows:
        key = (row.scene_index, row.shot_number)
        try:
            png = await store.get(row.frame_asset)
        except AssetNotFound:
            logger.warning(
                "re-audit: %s %s attempt %d: its drawing is gone", row.target, key, row.attempt
            )
            continue
        with Image.open(io.BytesIO(png)) as image:
            width, height = image.size
        frame = RenderedFrame(key, row.attempt, row.seed, png, width, height, "")
        audit = await audit_frame(model, frame, shots[key], screenplay, extraction)
        hard = tuple(c.check for c in audit.checks if not c.ok and c.severity is Severity.HARD)
        out.append(Reaudit(key, row.attempt, row.target, Verdict(row.verdict), audit.verdict, hard))
    return out


def line(row: Reaudit, scenes: Sequence[Scene]) -> str:
    """One re-audited attempt as the CLI prints it: `6.4 a1 comic: fail → pass` (pure)."""
    why = f" ({', '.join(c.value for c in row.failed)})" if row.failed else ""
    shot = f"{scenes[row.shot[0]].number}.{row.shot[1]}"
    return f"{shot} a{row.attempt} {row.target}: {row.before.value} → {row.after.value}{why}"


def _counts(verdicts: Sequence[Verdict]) -> str:
    seen = Counter(verdicts)
    return ", ".join(f"{v.value} {seen[v]}" for v in Verdict)


def summary(rows: Sequence[Reaudit]) -> str:
    """Before → after, and how often each hard check failed after (pure)."""
    checks = Counter(c for r in rows for c in r.failed)
    failed = ", ".join(f"{c.value} {checks[c]}" for c in Check if checks[c]) or "none"
    return "\n".join(
        [
            f"{len(rows)} drawings",
            f"before: {_counts([r.before for r in rows])}",
            f"after:  {_counts([r.after for r in rows])}",
            f"hard checks failed after: {failed}",
        ]
    )


async def _main(project_id: uuid.UUID, target: AuditTarget | None, limit: int | None) -> int:
    settings = Settings()
    if not (settings.supabase_url and settings.supabase_secret_key):
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are needed.", file=sys.stderr)
        return 2
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    model = NebiusChatModel.from_settings(settings)
    try:
        async with httpx2.AsyncClient(timeout=60) as client:
            store = SupabaseStore(
                url=settings.supabase_url,
                secret_key=settings.supabase_secret_key,
                bucket=settings.supabase_storage_bucket,
                client=client,
            )
            rows = await reaudit(sessions, store, model, project_id, target=target, limit=limit)
        async with sessions() as session:
            project = await session.get(ProjectRow, project_id)
    finally:
        await model.aclose()
        await engine.dispose()
    assert project is not None
    scenes = load_screenplay(project.screenplay).scenes  # type: ignore[arg-type]
    for r in rows:
        print(line(r, scenes))
    print()
    print(summary(rows))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.verify.reaudit",
        description="Audit a project's stored drawings again with today's audit; writes nothing.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    parser.add_argument("--target", choices=[t.value for t in AuditTarget])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    target = AuditTarget(args.target) if args.target else None
    sys.exit(asyncio.run(_main(args.project_id, target, args.limit)))


if __name__ == "__main__":
    main()
