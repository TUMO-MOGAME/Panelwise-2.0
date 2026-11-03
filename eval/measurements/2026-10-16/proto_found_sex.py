"""(a) measured on stored data (Token Factory only; no fal, no write): every stored storyboard audit,
newest project per title, where audit_frame would run the presence agent (a well-formed judgement
matching none of the drawn characters). Runs the presence agent as main does, then the sex agent on
every found person whose character the script sexes, and prints each answer with the frame's asset,
so the frames can be pulled and looked at. Also saves the rows to /tmp/found_sex.json."""

import asyncio
import base64
import json

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storage import SupabaseStore
from app.storyboard.prompt import character_sex, introduced_years, visible_characters
from app.verify.audit import (
    _calls_each_once,
    _find_characters,
    check_person,
    matched_people,
    present_characters,
    shot_ages,
    shot_sexes,
)
from app.verify.schema import FrameDescription, Judgement


async def main() -> None:
    settings = Settings()
    model = NebiusChatModel.from_settings(settings)
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    async with sessions() as s:
        projects = (await s.execute(select(ProjectRow).order_by(ProjectRow.created_at.desc()))).scalars().all()
        newest: dict[str, ProjectRow] = {}
        for p in projects:
            if p.plan is not None:
                newest.setdefault(p.title.split(" (")[0], p)
        audits = (
            await s.execute(
                select(FrameAuditRow).where(
                    FrameAuditRow.project_id.in_([p.id for p in newest.values()]),
                    FrameAuditRow.target == "storyboard",
                    FrameAuditRow.judgement.is_not(None),
                )
            )
        ).scalars().all()
    by_id = {p.id: p for p in newest.values()}
    loaded = {
        p.id: (load_screenplay(p.screenplay), load_extraction(p.extraction), load_plan(p.plan))
        for p in newest.values()
    }
    candidates = []
    for a in audits:
        sp, ex, plan = loaded[a.project_id]
        shot = next(x for x in plan.shots if x.scene_index == a.scene_index and x.number == a.shot_number)
        desc = FrameDescription.model_validate(a.description)
        judg = Judgement.model_validate(a.judgement)
        on_screen = visible_characters(shot, sp, ex)
        ages = shot_ages(shot, sp, introduced_years)
        matched = matched_people(shot, desc, judg, ex, ages)
        well = _calls_each_once([c.person for c in judg.people], len(desc.people)) and _calls_each_once(
            [c.object for c in judg.objects], len(desc.objects)
        )
        if well and on_screen and not set(on_screen) & set(matched.values()):
            candidates.append((a, shot, desc, judg, on_screen, ages, matched))
    print(f"{len(audits)} audits in {len(newest)} runs; presence agent would run on {len(candidates)}")

    gate = asyncio.Semaphore(3)
    out = []
    async with httpx2.AsyncClient(timeout=60) as client:
        store = SupabaseStore(
            url=settings.supabase_url, secret_key=settings.supabase_secret_key,
            bucket=settings.supabase_storage_bucket, client=client,
        )

        async def one(c) -> None:
            a, shot, desc, judg, on_screen, ages, matched = c
            sp, ex, _ = loaded[a.project_id]
            sexes = shot_sexes(shot, sp, ex, character_sex)
            chats: list = []
            async with gate:
                image = f"data:image/png;base64,{base64.b64encode(await store.get(a.frame_asset)).decode()}"
                found = await _find_characters(model, image, on_screen, shot, sp, ex, desc, chats)
                present = present_characters(on_screen, found, matched, desc, ages)
                asks = []
                for f in found:
                    if f.character in present and f.person is not None and f.character in sexes:
                        try:
                            check, _ = await check_person(model, image, desc, f.person)
                        except Exception as exc:  # the audit logs and skips a failed question
                            print(f"sex agent failed on {f.character}: {type(exc).__name__}", flush=True)
                            asks.append((f.character, f.person, sexes[f.character], "failed"))
                            continue
                        asks.append((f.character, f.person, sexes[f.character], check.sex))
            row = {
                "title": by_id[a.project_id].title.split(" (")[0],
                "shot": f"{a.scene_index + 1}.{a.shot_number}",
                "attempt": a.attempt,
                "asset": a.frame_asset,
                "on_screen": list(on_screen),
                "sexes": sexes,
                "found": [[f.character, f.person] for f in found],
                "present": sorted(present),
                "asks": asks,
                "people": [f"{p.position}: {p.appearance}" for p in desc.people],
            }
            out.append(row)

        await asyncio.gather(*(one(c) for c in candidates))
    out.sort(key=lambda r: (r["title"], r["shot"], r["attempt"]))
    for r in out:
        flags = [x for x in r["asks"] if x[3] in ("male", "female") and x[3] != x[2]]
        tag = "FLAG" if flags else ("asked" if r["asks"] else "-")
        print(
            f"{tag:5} {r['title'][:16]:16} {r['shot']:5} a{r['attempt']} present={r['present']} "
            f"asks={[(c, p, w, g) for c, p, w, g in r['asks']]}"
        )
    asked = sum(len(r["asks"]) for r in out)
    flagged = sum(1 for r in out for x in r["asks"] if x[3] in ("male", "female") and x[3] != x[2])
    print(f"frames {len(out)}; found-and-present with a script sex asked: {asked}; flagged {flagged}")
    json.dump(out, open("/work/found_sex.json", "w"), indent=1)
    await engine.dispose()


asyncio.run(main())
