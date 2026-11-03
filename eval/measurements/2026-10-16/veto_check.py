"""Free: for each one-picture copy flag in /work/twice.json, whether matched_people accepts the
pair as two different characters (the T104 veto)."""

import asyncio
import json

from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storyboard.prompt import introduced_years
from app.verify.audit import matched_people, shot_ages
from app.verify.schema import FrameDescription, Judgement


async def main() -> None:
    rows = [r for r in json.load(open("/work/twice.json"))
            if "error" not in r["answer"] and r["answer"]["panels"] == 1 and r["answer"]["copies"]]
    engine = make_engine(Settings())
    async with make_sessions(engine)() as s:
        for r in rows:
            a = (await s.execute(select(FrameAuditRow).where(FrameAuditRow.frame_asset == r["asset"]))).scalars().first()
            p = await s.get(ProjectRow, a.project_id)
            sp, ex = load_screenplay(p.screenplay), load_extraction(p.extraction)
            shot = next(x for x in load_plan(p.plan).shots if x.scene_index == a.scene_index and x.number == a.shot_number)
            m = matched_people(shot, FrameDescription.model_validate(a.description),
                               Judgement.model_validate(a.judgement), ex, shot_ages(shot, sp, introduced_years))
            kept = [pr for pr in r["answer"]["copies"]
                    if not (pr[0] in m and pr[1] in m and m[pr[0]] != m[pr[1]])]
            print(f"{r['title'][:18]:18} {r['shot']:5} a{r['attempt']} copies={r['answer']['copies']} "
                  f"accepted={m} -> {'FAIL' if kept else 'vetoed'}")
    await engine.dispose()


asyncio.run(main())
