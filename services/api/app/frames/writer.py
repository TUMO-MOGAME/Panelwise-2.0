"""The two hooks that write a frame's progress (verify.md §6 `FrameWriter`; T021).

`log` keeps every audited attempt in `frame_audits`; `on_frame` moves the shot's `frames` row
through verify.md §5. Each write is its own short transaction, so a frame's state is visible to the
web while its job still runs. The only path that writes a `frames` row's state, besides the restart
sweep.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import ACCEPTED, AuditTarget, FrameAuditRow, FrameRow
from app.verify.model import Audit, Check, FrameState, RecordingRenderer, Severity, Verdict

_CHECK_ORDER = {check.value: i for i, check in enumerate(Check)}


def _jsonable(model: Any) -> dict[str, Any] | None:
    return None if model is None else model.model_dump(mode="json")


def withheld_check(row: FrameAuditRow | None) -> str | None:
    """The reason a frame was withheld, from its last audit: `audit_error` for an audit that
    couldn't run, else its first failed hard check in `Check` order (web.md §6)."""
    if row is None:
        return None
    if row.verdict == Verdict.ERROR:
        return "audit_error"
    failed = [c["check"] for c in row.checks if c["severity"] == Severity.HARD and not c["ok"]]
    return min(failed, key=_CHECK_ORDER.__getitem__) if failed else None


class FrameWriter:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        project_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        target: AuditTarget = AuditTarget.STORYBOARD,
    ) -> None:
        self.sessions = sessions
        self.project_id = project_id
        self.job_id = job_id
        self.target = target  # a comic panel's attempts are logged as COMIC (T064)

    async def log(self, audit: Audit, frame_asset: str) -> None:
        scene_index, shot_number = audit.shot
        async with self.sessions() as session:
            session.add(
                FrameAuditRow(
                    project_id=self.project_id,
                    job_id=self.job_id,
                    target=self.target.value,
                    scene_index=scene_index,
                    shot_number=shot_number,
                    attempt=audit.attempt,
                    seed=audit.seed,
                    frame_asset=frame_asset,
                    description=_jsonable(audit.description),
                    judgement=_jsonable(audit.judgement),
                    checks=[
                        {
                            "check": c.check.value,
                            "severity": c.severity.value,
                            "ok": c.ok,
                            "detail": c.detail,
                        }
                        for c in audit.checks
                    ],
                    positions={name: p.value for name, p in audit.positions.items()},
                    seen=[
                        {"person": s.person, "character": s.character, "sex": s.sex}
                        for s in audit.seen
                    ],
                    found=[
                        {"character": f.character, "person": f.person, "reason": f.reason}
                        for f in audit.found
                    ],
                    layout=None
                    if audit.layout is None
                    else {
                        "panels": audit.layout.panels,
                        "copies": [list(pair) for pair in audit.layout.copies],
                        "reason": audit.layout.reason,
                    },
                    heads=[
                        {"person": h.person, "character": h.character, "box": list(h.box)}
                        for h in audit.heads
                    ]
                    or None,
                    verdict=audit.verdict.value,
                    models=list(audit.models),
                    prompt_tokens=audit.usage.prompt_tokens,
                    completion_tokens=audit.usage.completion_tokens,
                )
            )
            await session.commit()

    async def on_frame(
        self, shot: tuple[int, int], state: FrameState, attempt: int, asset: str | None
    ) -> None:
        if self.target is not AuditTarget.STORYBOARD:
            raise ValueError("a comic panel has no frames row: only a storyboard writer moves one")
        scene_index, shot_number = shot
        async with self.sessions() as session:
            reason = None
            if state is FrameState.WITHHELD:
                last = await session.scalar(
                    select(FrameAuditRow)
                    .where(
                        FrameAuditRow.project_id == self.project_id,
                        FrameAuditRow.target == AuditTarget.STORYBOARD.value,
                        FrameAuditRow.scene_index == scene_index,
                        FrameAuditRow.shot_number == shot_number,
                    )
                    .order_by(FrameAuditRow.attempt.desc(), FrameAuditRow.created_at.desc())
                    .limit(1)
                )
                reason = withheld_check(last)
            values = {
                "state": state.value,
                "attempt": attempt,
                "job_id": self.job_id,
                # Only an accepted frame references its image (web.md §3); nothing else ever does.
                "asset": asset if state.value in ACCEPTED else None,
                "withheld_check": reason,
                "failure": "render" if state is FrameState.FAILED else None,
            }
            key = {
                "project_id": self.project_id,
                "scene_index": scene_index,
                "shot_number": shot_number,
            }
            await session.execute(
                insert(FrameRow)
                .values(**key, **values)
                .on_conflict_do_update(index_elements=list(key), set_=values)
            )
            await session.commit()


def frame_hooks(
    writer: FrameWriter, renderer: RecordingRenderer, shot: tuple[int, int]
) -> tuple[Callable[[Audit], Awaitable[None]], Callable[[FrameState, int], Awaitable[None]]]:
    """`(log, on_state)` for `render_until_accepted` (verify.md §6): each audit is logged with its
    attempt's Storage path, and only an accepted state passes the image on to the `frames` row. The
    one adapter, shared by the retry and T026's `build_storyboard`."""

    async def log(audit: Audit) -> None:
        await writer.log(audit, renderer.record(shot, audit.attempt).asset)

    async def on_state(state: FrameState, attempt: int) -> None:
        accepted = state in (FrameState.PASSED, FrameState.WARNED)
        await writer.on_frame(
            shot, state, attempt, renderer.record(shot, attempt).asset if accepted else None
        )

    return log, on_state
