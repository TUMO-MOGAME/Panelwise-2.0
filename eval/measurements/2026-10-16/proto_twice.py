"""(c) prototype on stored drawings (Token Factory only; no fal, no write): one vision question per
stored storyboard attempt (newest run per title) whose description has two or more people: is the
picture one scene or several panels, and is any numbered person the same person as another? Prints
every answer; saves /work/twice.json. `--count` only counts the candidates."""

import asyncio
import base64
import json
import sys

import httpx2
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import FrameAuditRow
from app.llm import NebiusChatModel, Tier, structured_chat
from app.projects.model import ProjectRow
from app.storage import SupabaseStore

PROMPT = (
    "You look at one storyboard drawing and a numbered list of the people a describer saw in it. "
    "Answer two things from the drawing alone. First, panels: 1 when it is one single picture, or "
    "the number of separate panels when it is laid out as a strip or grid of pictures side by side. "
    "Second, copies: the pairs of numbered people who are plainly the same person drawn more than "
    "once (the same face, hair, build and clothes, for example one person shown at two moments, or "
    "twice in one room), as [a, b] pairs; an empty list when everyone is a different person. People "
    "who merely look alike in a sketchy style (two men in suits, two children) are not copies unless "
    "their face, hair and clothes match. Give a short reason."
)


class Copies(BaseModel):
    panels: int
    copies: list[list[int]]
    reason: str


async def main() -> None:
    settings = Settings()
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
            FrameAuditRow.target == "storyboard", FrameAuditRow.description.is_not(None),
        ))).scalars().all()
    title = {p.id: p.title.split(" (")[0] for p in newest.values()}
    cands = [a for a in audits if len((a.description or {}).get("people", [])) >= 2]
    print(f"{len(audits)} described attempts; {len(cands)} with two or more people", flush=True)
    if "--count" in sys.argv:
        return
    model = NebiusChatModel.from_settings(settings)
    gate = asyncio.Semaphore(3)
    out = []
    async with httpx2.AsyncClient(timeout=120) as client:
        store = SupabaseStore(url=settings.supabase_url, secret_key=settings.supabase_secret_key,
                              bucket=settings.supabase_storage_bucket, client=client)

        async def one(a) -> None:
            people = a.description["people"]
            text = "People in the drawing:\n" + "\n".join(
                f"[{i}] {p['position']}: {p['appearance']}" for i, p in enumerate(people))
            async with gate:
                image = f"data:image/png;base64,{base64.b64encode(await store.get(a.frame_asset)).decode()}"
                messages = [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": [{"type": "text", "text": text},
                                                 {"type": "image_url", "image_url": {"url": image}}]},
                ]
                try:
                    r = await structured_chat(model, messages, Copies, Tier.VISION, max_tokens=4096)
                    ans = r.value.model_dump()
                    tokens = r.chat.usage.prompt_tokens + r.chat.usage.completion_tokens
                except Exception as exc:
                    ans, tokens = {"error": type(exc).__name__}, 0
            out.append({"title": title[a.project_id], "shot": f"{a.scene_index + 1}.{a.shot_number}",
                        "attempt": a.attempt, "verdict": a.verdict, "asset": a.frame_asset,
                        "people": [f"{p['position']}: {p['appearance']}" for p in people],
                        "answer": ans, "tokens": tokens})

        await asyncio.gather(*(one(a) for a in cands))
    out.sort(key=lambda r: (r["title"], r["shot"], r["attempt"]))
    for r in out:
        a = r["answer"]
        flag = "ERR " if "error" in a else ("SPLIT" if a["panels"] > 1 else "") + ("COPY" if a["copies"] else "")
        if flag:
            print(f"{flag:9} {r['title'][:18]:18} {r['shot']:5} a{r['attempt']} {r['verdict']:5} "
                  f"{a.get('panels')} {a.get('copies')} {a.get('reason', '')[:110]}")
    ok = [r for r in out if "error" not in r["answer"]]
    print(f"asked {len(out)}, answered {len(ok)}; split {sum(r['answer']['panels'] > 1 for r in ok)}, "
          f"copies {sum(bool(r['answer']['copies']) for r in ok)}; tokens {sum(r['tokens'] for r in out)}")
    json.dump(out, open("/work/twice.json", "w"), indent=1)
    await engine.dispose()


asyncio.run(main())
