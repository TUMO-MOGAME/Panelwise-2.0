"""Free: every stored extraction (all projects, not only the newest per title). Character pairs
where one name's words are a subset of another's, split by what the longer adds (titles only,
other name words, person words), with each side's source, sex, and how many shots cast each."""

import asyncio

from sqlalchemy import select

from app.characters.redact import NAME_STOP_WORDS, TITLE_WORDS
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.grounding import EntityKind
from app.projects.codec import load_extraction, load_plan
from app.projects.model import ProjectRow
from app.script import normalise


async def main() -> None:
    engine = make_engine(Settings())
    async with make_sessions(engine)() as s:
        rows = (await s.execute(select(ProjectRow).order_by(ProjectRow.created_at))).scalars().all()
    total = 0
    for p in rows:
        if p.extraction is None:
            continue
        total += 1
        ex = load_extraction(p.extraction)
        chars = [e for e in ex.entities if e.kind is EntityKind.CHARACTER]
        shots = load_plan(p.plan).shots if p.plan is not None else ()
        words = {c.name: set(normalise(c.name).split()) for c in chars}
        out = []
        for a in chars:
            for b in chars:
                if a is b:
                    continue
                wa, wb = words[a.name], words[b.name]
                core = wa - NAME_STOP_WORDS
                if not core or not wa < wb:
                    continue
                extra = wb - wa
                kind = (
                    "titles" if extra <= TITLE_WORDS
                    else "stop" if extra <= NAME_STOP_WORDS
                    else "name"
                )
                cast = lambda n: sum(n in sh.characters for sh in shots)
                out.append(
                    f"  {a.name!r}({a.source.value},{a.sex and a.sex.value},{cast(a.name)} shots)"
                    f" < {b.name!r}({b.source.value},{b.sex and b.sex.value},{cast(b.name)} shots)"
                    f" adds {sorted(extra)} [{kind}]"
                )
        if out:
            print(f"{p.created_at:%m-%d %H:%M} {p.title}")
            print("\n".join(out))
    print(f"{total} extractions read")
    await engine.dispose()


asyncio.run(main())
