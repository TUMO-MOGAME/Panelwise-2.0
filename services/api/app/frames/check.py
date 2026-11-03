"""The architecture check (verify.md §6, T062): the render → audit → re-render loop end to end with
no image model.

A `SketchRenderer` draws a plain pencil test image from the seed instead of rendering the shot, so
the real audit sees a frame that is not the shot and most frames take the path a wrong frame takes:
re-rendered, then withheld. It runs on a throwaway copy of a planned project, never the project
itself, and only against the dev bucket. A sketch the audit passes is a test artefact, not evidence
of grounding.

    uv run python -m app.frames.check <project-id> [--shots N]
"""

import argparse
import asyncio
import hashlib
import io
import logging
import random
import sys
import uuid
from dataclasses import dataclass

import httpx2
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.attempt import RENDER_FAILED
from app.frames.model import FrameRow
from app.frames.repo import audits_of, frames_of
from app.frames.writer import FrameWriter, frame_hooks
from app.jobs import JobKind, JobRow, JobState
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import fail_job
from app.projects.model import ProjectRow
from app.projects.pipeline import Stage
from app.shots import Shot
from app.storage import AssetStore, SupabaseStore
from app.verify.loop import render_until_accepted
from app.verify.model import FrameState, RenderedFrame

log = logging.getLogger(__name__)

DEV_BUCKET = "panelwise-dev"
WIDTH, HEIGHT = 1280, 720  # the storyboard's frame (storyboard.md §6)
PAPER, PENCIL, FAINT = (250, 250, 247), (86, 97, 109), (138, 149, 159)


class CheckRefused(RuntimeError):
    """The check will not run here: the wrong bucket, or a project with nothing to draw."""


def sketch(seed: int, width: int, height: int) -> bytes:
    """A pencil test image, the same bytes for the same seed and size: a horizon, one to three
    figures and a box. PNG with no metadata."""
    rng = random.Random(seed)
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    line = max(1, round(width / 480))
    horizon = round(height * rng.uniform(0.6, 0.78))
    draw.line([(0, horizon), (width, horizon)], fill=FAINT, width=line)
    bx = rng.uniform(0.55, 0.8) * width
    bw, bh = width * rng.uniform(0.1, 0.2), height * rng.uniform(0.25, 0.45)
    draw.rectangle([bx, horizon - bh, bx + bw, horizon], outline=PENCIL, width=line * 2)
    for _ in range(rng.randint(1, 3)):
        x = rng.uniform(0.1, 0.5) * width
        scale = height * rng.uniform(0.18, 0.3)
        head = scale * 0.16
        top = horizon - scale
        draw.ellipse([x - head, top - 2 * head, x + head, top], outline=PENCIL, width=line * 2)
        draw.polygon(
            [
                (x - head * 1.2, top + 2),
                (x + head * 1.2, top + 2),
                (x + head * 1.5, horizon),
                (x - head * 1.5, horizon),
            ],
            outline=PENCIL,
            width=line * 2,
        )
    out = io.BytesIO()
    image.save(out, format="PNG")  # Pillow writes no text chunks unless asked
    return out.getvalue()


@dataclass(frozen=True)
class SketchRecord:
    asset: str


class SketchRenderer:
    """A `RecordingRenderer` (verify.md §6): draws `sketch(seed)`, stores it by content hash and
    records it before returning, so the frame hooks can find each attempt's path."""

    def __init__(self, store: AssetStore) -> None:
        self.store = store
        self.records: dict[tuple[tuple[int, int], int], SketchRecord] = {}

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        png = sketch(seed, width, height)
        path = f"frames/{hashlib.sha256(png).hexdigest()}.png"
        await self.store.put(path, png, "image/png")  # a content address: put is idempotent
        key = (shot.scene_index, shot.number)
        self.records[(key, attempt)] = SketchRecord(path)
        return RenderedFrame(key, attempt, seed, png, width, height, "architecture check sketch")

    def record(self, shot: tuple[int, int], attempt: int) -> SketchRecord:
        return self.records[(shot, attempt)]


async def run_check(
    sessions: async_sessionmaker[AsyncSession],
    store: AssetStore,
    model: NebiusChatModel,
    project_id: uuid.UUID,
    *,
    bucket: str,
    shots: int = 3,
) -> uuid.UUID:
    """Copies the project, runs the loop with the real audit on the copy's first `shots` shots in
    plan order under one frame_attempt job, and returns the copy's id."""
    if bucket != DEV_BUCKET:
        raise CheckRefused(
            f"the architecture check runs only against {DEV_BUCKET!r}, not {bucket!r}"
        )
    if shots < 1:
        raise CheckRefused(f"--shots must be at least 1, not {shots}")
    async with sessions() as session, session.begin():
        source = await session.get(ProjectRow, project_id)
        if source is None or None in (source.screenplay, source.extraction, source.plan):
            raise CheckRefused("that project has no plan to draw")
        copy = ProjectRow(
            id=uuid.uuid4(),
            owner=source.owner,
            title=f"{source.title} (architecture check)",
            pdf_path=source.pdf_path,  # the same Storage object: nothing is re-uploaded
            screenplay=source.screenplay,
            extraction=source.extraction,
            plan=source.plan,
        )
        session.add(copy)
        await session.flush()
        # A done storyboard job, so the list shows the copy as planned; then the check's own job.
        session.add(
            JobRow(
                id=uuid.uuid4(),
                project_id=copy.id,
                kind=JobKind.STORYBOARD,
                state=JobState.DONE,
                stage=Stage.PLANNING,
                progress=60,
            )
        )
        job = JobRow(
            id=uuid.uuid4(),
            project_id=copy.id,
            kind=JobKind.FRAME_ATTEMPT,
            state=JobState.RUNNING,
            stage=Stage.RENDERING,
            progress=60,
        )
        session.add(job)
        screenplay = load_screenplay(copy.screenplay)
        extraction = load_extraction(copy.extraction)
        plan = load_plan(copy.plan)

    renderer = SketchRenderer(store)
    writer = FrameWriter(sessions, copy.id, job.id)
    key = (0, 0)  # the frame in hand, for a failure
    try:
        for shot in plan.shots[:shots]:
            key = (shot.scene_index, shot.number)
            log_audit, on_state = frame_hooks(writer, renderer, key)
            await render_until_accepted(
                model,
                renderer,
                shot,
                screenplay,
                extraction,
                width=WIDTH,
                height=HEIGHT,
                log=log_audit,
                on_state=on_state,
            )
    except Exception:
        # The loop fails the frame itself on a renderer error; an audit or database error leaves
        # it mid-flight, so fail it here too (idempotent), as the retry does (attempt.py).
        try:
            async with sessions() as session:
                frame = await session.get(FrameRow, (copy.id, *key))
            if frame is not None:
                await writer.on_frame(key, FrameState.FAILED, frame.attempt, None)
        except Exception:
            log.exception("frame %s could not be marked failed", key)
        await fail_job(sessions, job.id, RENDER_FAILED, Stage.RENDERING)
        raise
    async with sessions() as session, session.begin():
        found = await session.get(JobRow, job.id)
        if found is not None:
            found.state, found.progress = JobState.DONE, 100
    return copy.id


async def _main(project_id: uuid.UUID, shots: int) -> int:
    settings = Settings()
    if not (settings.supabase_url and settings.supabase_secret_key):
        print("SUPABASE_URL and SUPABASE_SECRET_KEY are needed (the dev bucket).", file=sys.stderr)
        return 2
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    try:
        async with httpx2.AsyncClient(timeout=60) as client:
            store = SupabaseStore(
                url=settings.supabase_url,
                secret_key=settings.supabase_secret_key,
                bucket=settings.supabase_storage_bucket,
                client=client,
            )
            model = NebiusChatModel.from_settings(settings)
            try:
                copy_id = await run_check(
                    sessions,
                    store,
                    model,
                    project_id,
                    bucket=settings.supabase_storage_bucket,
                    shots=shots,
                )
            except CheckRefused as exc:
                print(f"refused: {exc}", file=sys.stderr)
                return 2
            async with sessions() as session:
                frames = await frames_of(session, copy_id)
                audits = await audits_of(session, copy_id)
    finally:
        await engine.dispose()
    print(f"copy: {copy_id}")
    for frame in frames:
        tried = audits.get((frame.scene_index, frame.shot_number), [])
        verdicts = ", ".join(f"{a.attempt}:{a.verdict}" for a in tried)
        why = f" ({frame.withheld_check})" if frame.withheld_check else ""
        print(
            f"shot {frame.scene_index}.{frame.shot_number}: {frame.state}{why} after [{verdicts}]"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.frames.check",
        description="The architecture check: the frame loop end to end with no image model.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    parser.add_argument("--shots", type=int, default=3)
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.project_id, args.shots)))


if __name__ == "__main__":
    main()
