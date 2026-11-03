"""The re-check: today's code checks run again on what the audit already saw and judged
(docs/design/verify.md §6, T083).

    python -m app.verify.recheck <project-id> [--target storyboard|comic]

It reads each stored audit's description and judgement and runs today's `run_checks` on them:
no model call, no Storage, no write. So a change to the checks alone is measured for free, on
the very audits it changes. A change to what the describer or the judge is asked needs reaudit.
The rule ladder (T094) applies as it does live: `AUDIT_WITHHOLD_CHECKS` names the hard checks
that withhold, so measure a rule's way back by naming it there.
"""

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, withholding
from app.db import make_engine, make_sessions
from app.frames.model import AuditTarget, FrameAuditRow
from app.llm import Usage
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.verify.audit import apply_ladder, run_checks, shot_ages, shot_sexes
from app.verify.model import (
    Audit,
    Check,
    FrameLayout,
    PersonFound,
    PersonSeen,
    Severity,
    Verdict,
)
from app.verify.reaudit import Reaudit, line, summary
from app.verify.schema import FrameDescription, Judgement


async def recheck(
    sessions: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    *,
    target: AuditTarget | None = None,
    withholding: frozenset[Check] | None = None,
) -> tuple[list[Reaudit], int]:
    """Every stored audit of the project (one target, or both) in reaudit's order, checked again
    with today's code, and how many were skipped: no description or judgement (an ERROR), or
    one stored before today's schema. `withholding` is the rule ladder (T094), applied as the
    loop applies it before it logs; None keeps every hard check."""
    # Imported here, as audit_frame does: app.storyboard's renderer modules import app.verify.
    from app.storyboard.prompt import character_sex, introduced_years, visible_characters

    async with sessions() as session:
        project = await session.get(ProjectRow, project_id)
        if (
            project is None
            or project.plan is None
            or project.screenplay is None
            or project.extraction is None
        ):
            raise ValueError("no such project" if project is None else "no shot plan yet")
        query = (
            select(FrameAuditRow)
            .where(FrameAuditRow.project_id == project_id)
            .order_by(
                FrameAuditRow.target,
                FrameAuditRow.scene_index,
                FrameAuditRow.shot_number,
                FrameAuditRow.attempt,
            )
        )
        if target is not None:
            query = query.where(FrameAuditRow.target == target.value)
        rows = list(await session.scalars(query))
    screenplay = load_screenplay(project.screenplay)
    extraction = load_extraction(project.extraction)
    shots = {(s.scene_index, s.number): s for s in load_plan(project.plan).shots}

    out: list[Reaudit] = []
    skipped = 0
    for row in rows:
        key = (row.scene_index, row.shot_number)
        shot = shots.get(key)
        if shot is None or row.description is None or row.judgement is None:
            skipped += 1
            continue
        try:
            description = FrameDescription.model_validate(row.description)
            judgement = Judgement.model_validate(row.judgement)
        except ValidationError:
            skipped += 1
            continue
        checks, verdict, _ = run_checks(
            shot,
            screenplay.scenes[shot.scene_index],
            description,
            judgement,
            extraction,
            on_screen=visible_characters(shot, screenplay, extraction),
            ages=shot_ages(shot, screenplay, introduced_years),
            # T095: the stored answers; a row before 0007 has none, so no DRAWN_SEX.
            seen=tuple(
                PersonSeen(int(s["person"]), str(s["character"]), str(s["sex"]))
                for s in row.seen or ()
            ),
            sexes=shot_sexes(shot, screenplay, extraction, character_sex),
            # T099: the stored answers; a row before 0008 has none, so the judge alone.
            found=tuple(
                PersonFound(
                    str(f["character"]),
                    None if f["person"] is None else int(f["person"]),
                    str(f["reason"]),
                )
                for f in row.found or ()
            ),
            # T104: the stored answer; a row before 0009, or not asked, has none: SPLIT_PANELS
            # and the layout's copies pass (T124's described-alike pairs need only the description).
            layout=None
            if row.layout is None
            else FrameLayout(
                int(row.layout["panels"]),
                tuple((int(a), int(b)) for a, b in row.layout["copies"]),
                str(row.layout["reason"]),
            ),
        )
        laddered = apply_ladder(
            Audit(
                key,
                row.attempt,
                row.seed,
                description,
                judgement,
                checks,
                verdict,
                {},
                (),
                Usage(0, 0, 0),
            ),
            withholding,
        )
        checks, verdict = laddered.checks, laddered.verdict
        hard = tuple(c.check for c in checks if not c.ok and c.severity is Severity.HARD)
        out.append(Reaudit(key, row.attempt, row.target, Verdict(row.verdict), verdict, hard))
    return out, skipped


def accepted_shots(rows: Sequence[Reaudit]) -> tuple[int, int]:
    """Shots (per target) with an attempt `pass` or `warn`, before and after (pure)."""
    accepted = (Verdict.PASS, Verdict.WARN)
    before = {(r.target, r.shot) for r in rows if r.before in accepted}
    after = {(r.target, r.shot) for r in rows if r.after in accepted}
    return len(before), len(after)


async def _main(project_id: uuid.UUID, target: AuditTarget | None) -> int:
    settings = Settings()
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    try:
        rows, skipped = await recheck(
            sessions, project_id, target=target, withholding=withholding(settings)
        )
        async with sessions() as session:
            project = await session.get(ProjectRow, project_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (SQLAlchemyError, OSError) as exc:
        print(f"the database answered {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    assert project is not None
    scenes = load_screenplay(project.screenplay).scenes  # type: ignore[arg-type]
    for r in rows:
        print(line(r, scenes))
    before, after = accepted_shots(rows)
    print()
    print(summary(rows))
    print(f"shots with an accepted attempt: {before} → {after}")
    print(f"skipped: {skipped}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.verify.recheck",
        description="Today's code checks on a project's stored audits; no model, writes nothing.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    parser.add_argument("--target", choices=[t.value for t in AuditTarget])
    args = parser.parse_args()
    target = AuditTarget(args.target) if args.target else None
    sys.exit(asyncio.run(_main(args.project_id, target)))


if __name__ == "__main__":
    main()
