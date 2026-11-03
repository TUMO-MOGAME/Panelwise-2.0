"""`FrameView` from a `frames` row (web.md §6 *API internals: the reads*; T047). Pure."""

from collections.abc import Sequence

from app.api.v1.schemas import AuditView, FrameView
from app.frames.model import ACCEPTED, FrameAuditRow, FrameRow
from app.script import Screenplay
from app.verify.loop import MAX_RENDERS


def audit_view(row: FrameAuditRow) -> AuditView:
    """One attempt as the web sees it (web.md §6 `AuditView`). Never its Storage path."""
    return AuditView.model_validate(
        {
            "attempt": row.attempt,
            "seed": row.seed,
            "verdict": row.verdict,
            "description": row.description,
            "judgement": row.judgement,
            "checks": row.checks,
            "positions": row.positions,
            "models": row.models,
            "created_at": row.created_at,
        }
    )


def frame_view(
    row: FrameRow,
    screenplay: Screenplay,
    image_url: str | None,
    audits: Sequence[FrameAuditRow] = (),
    *,
    max_renders: int = MAX_RENDERS,
) -> FrameView:
    """`image_url` is honoured only for an accepted frame; every other state shows no image.
    `max_renders` is RENDER_MAX_ATTEMPTS (T071) and never reads below the attempt, so a user's
    extra render is "4 of 4"."""
    accepted = row.state in ACCEPTED and row.asset is not None
    return FrameView.model_validate(
        {
            "shot_id": f"{screenplay.scenes[row.scene_index].number}.{row.shot_number}",
            "state": row.state,
            "attempt": row.attempt,
            "max_renders": max(max_renders, row.attempt),
            "image_url": image_url if accepted else None,
            "withheld_check": row.withheld_check,
            "failure": row.failure,
            "audits": [audit_view(a) for a in sorted(audits, key=lambda a: a.attempt)],
        }
    )
