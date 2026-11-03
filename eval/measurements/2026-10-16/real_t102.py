"""T102's real code on stored drawings (Token Factory only; no fal, no write): every stored storyboard
attempt (newest run per title) where audit_frame runs the presence agent. Runs audit_frame's tail as
the branch's code does it (the presence agent, then T102's sex questions through _ask_sexes) on the
stored description and judgement, then run_checks, and prints DRAWN_SEX per frame. The lighthouse's
extraction is re-grounded with T101 (main) and its shots' FORTUIN/NAIDOO renamed to the folded
names, so 7.5 is asked as MR. FORTUIN."""

import asyncio
import base64
import json
from dataclasses import replace

import httpx2
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.grounding import EntityKind, ground
from app.grounding.model import Extraction, Source
from app.grounding.schema import ProposedEntity
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storage import SupabaseStore
from app.storyboard.prompt import character_sex, introduced_years, visible_characters
from app.verify.audit import (
    _ask_sexes,
    _calls_each_once,
    _find_characters,
    found_people,
    matched_people,
    run_checks,
    shot_ages,
    shot_sexes,
)
from app.verify.model import Check
from app.verify.schema import FrameDescription, Judgement


def folded(ex: Extraction, sp) -> Extraction:
    proposals = [
        ProposedEntity(name=e.name, kind=e.kind.value, quotes=[q.text for q in e.quotes],
                       species=e.species, other_names=list(e.other_names))
        for e in ex.entities
        if e.source is Source.MODEL and e.kind in (EntityKind.CHARACTER, EntityKind.PROP)
    ]
    entities, report = ground(proposals, sp)
    return replace(ex, entities=entities, report=report)


RENAME = {"FORTUIN": "MR. FORTUIN", "NAIDOO": "MS. NAIDOO"}


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
        audits = (await s.execute(select(FrameAuditRow).where(
            FrameAuditRow.project_id.in_([p.id for p in newest.values()]),
            FrameAuditRow.target == "storyboard", FrameAuditRow.judgement.is_not(None),
        ))).scalars().all()
    title = {p.id: p.title.split(" (")[0] for p in newest.values()}
    loaded = {}
    for p in newest.values():
        sp, ex, plan = load_screenplay(p.screenplay), load_extraction(p.extraction), load_plan(p.plan)
        if title[p.id] == "the-lighthouse-inspector":
            ex = folded(ex, sp)
            plan = replace(plan, shots=tuple(
                replace(sh, characters=tuple(RENAME.get(c, c) for c in sh.characters)) for sh in plan.shots
            ))
        loaded[p.id] = (sp, ex, plan)
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
            [c.object for c in judg.objects], len(desc.objects))
        if well and on_screen and not set(on_screen) & set(matched.values()):
            candidates.append((a, shot, desc, judg, on_screen, ages, matched))
    print(f"{len(audits)} audits in {len(newest)} runs; the presence agent runs on {len(candidates)}", flush=True)

    gate = asyncio.Semaphore(3)
    out = []
    async with httpx2.AsyncClient(timeout=120) as client:
        store = SupabaseStore(url=settings.supabase_url, secret_key=settings.supabase_secret_key,
                              bucket=settings.supabase_storage_bucket, client=client)

        async def one(c) -> None:
            a, shot, desc, judg, on_screen, ages, matched = c
            sp, ex, _ = loaded[a.project_id]
            sexes = shot_sexes(shot, sp, ex, character_sex)
            chats: list = []
            async with gate:
                image = f"data:image/png;base64,{base64.b64encode(await store.get(a.frame_asset)).decode()}"
                found = await _find_characters(model, image, on_screen, shot, sp, ex, desc, chats)
                found_at = found_people(on_screen, found, matched, desc, ages)
                pairs = sorted((person, character) for character, person in found_at.items())
                asked = [p for p in pairs if p[1] in sexes]
                seen = await _ask_sexes(model, image, desc, pairs, sexes, chats)
            checks, verdict, _ = run_checks(shot, sp.scenes[a.scene_index], desc, judg, ex,
                                           on_screen=on_screen, ages=ages, seen=seen, sexes=sexes, found=found)
            drawn = {c.check: c for c in checks}[Check.DRAWN_SEX]
            out.append({
                "title": title[a.project_id], "shot": f"{a.scene_index + 1}.{a.shot_number}",
                "attempt": a.attempt, "asset": a.frame_asset, "asked": asked,
                "seen": [[x.person, x.character, x.sex] for x in seen], "sexes": sexes,
                "drawn_sex_ok": drawn.ok, "detail": drawn.detail,
                "people": [f"{p.position}: {p.appearance}" for p in desc.people],
            })

        await asyncio.gather(*(one(c) for c in candidates))
    out.sort(key=lambda r: (r["title"], r["shot"], r["attempt"]))
    for r in out:
        if r["asked"]:
            tag = "FAIL" if not r["drawn_sex_ok"] else "pass"
            print(f"{tag} {r['title'][:18]:18} {r['shot']:5} a{r['attempt']} asked={r['asked']} "
                  f"seen={r['seen']} {r['detail'] or ''}")
    asked = sum(len(r["asked"]) for r in out)
    answered = sum(len(r["seen"]) for r in out)
    print(f"frames {len(out)}; pairs asked {asked}, answered {answered} (failed {asked - answered}); "
          f"DRAWN_SEX failed on {sum(not r['drawn_sex_ok'] for r in out)} frames")
    json.dump(out, open("/work/real_t102.json", "w"), indent=1)
    await engine.dispose()


asyncio.run(main())
