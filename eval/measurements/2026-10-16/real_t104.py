"""Free: T104's real code (frame_layout + run_checks, the branch's app/ mounted) on the 330 stored
layout answers in /work/twice.json (the same prompt, verbatim), with each audit's stored
description and judgement and today's presence answers absent (found: the row's own, if any).
Prints every frame that fails SPLIT_PANELS or DRAWN_TWICE, and the counts."""

import asyncio
import json

from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storyboard.prompt import introduced_years, visible_characters
from app.verify.audit import frame_layout, run_checks, shot_ages
from app.verify.model import Check, PersonFound
from app.verify.schema import FrameDescription, Judgement, Layout


async def main() -> None:
    rows = [r for r in json.load(open("/work/twice.json")) if "error" not in r["answer"]]
    engine = make_engine(Settings())
    split = twice = 0
    async with make_sessions(engine)() as s:
        for r in rows:
            a = (await s.execute(select(FrameAuditRow.project_id, FrameAuditRow.scene_index, FrameAuditRow.shot_number, FrameAuditRow.description, FrameAuditRow.judgement, FrameAuditRow.found).where(FrameAuditRow.frame_asset == r["asset"]))).first()
            p = await s.get(ProjectRow, a.project_id)
            sp, ex = load_screenplay(p.screenplay), load_extraction(p.extraction)
            shot = next(x for x in load_plan(p.plan).shots if x.scene_index == a.scene_index and x.number == a.shot_number)
            desc = FrameDescription.model_validate(a.description)
            layout = frame_layout(Layout.model_validate(r["answer"]), len(desc.people))
            found = tuple(PersonFound(str(f["character"]), f["person"], str(f["reason"])) for f in a.found or ())
            checks, _, _ = run_checks(
                shot, sp.scenes[a.scene_index], desc, Judgement.model_validate(a.judgement), ex,
                on_screen=visible_characters(shot, sp, ex), ages=shot_ages(shot, sp, introduced_years),
                found=found, layout=layout,
            )
            by = {c.check: c for c in checks}
            if not by[Check.SPLIT_PANELS].ok or not by[Check.DRAWN_TWICE].ok:
                split += not by[Check.SPLIT_PANELS].ok
                twice += not by[Check.DRAWN_TWICE].ok
                fails = [c.check.value for c in (by[Check.SPLIT_PANELS], by[Check.DRAWN_TWICE]) if not c.ok]
                print(f"{r['title'][:18]:18} {r['shot']:5} a{r['attempt']} {fails}")
    print(f"answers {len(rows)}: SPLIT_PANELS fails {split}, DRAWN_TWICE fails {twice}")
    await engine.dispose()


asyncio.run(main())
