"""Free replay: every stored extraction's model characters and props become proposals again, run
through ground() as it is and with a prototype fold (a bare name into the one titled spelling,
among the model's names and the script's cues, whose words are it plus title words only). Prints
every character that changes, and anything else that differs."""

import asyncio
from dataclasses import replace

from sqlalchemy import select

import app.grounding.filter as F
from app.characters.redact import TITLE_WORDS
from app.characters.sex import SEX_TITLES
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.grounding import EntityKind
from app.grounding.model import Source
from app.grounding.schema import ProposedEntity
from app.projects.codec import load_extraction, load_screenplay
from app.projects.model import ProjectRow
from app.script import Dialogue, normalise

TITLES = TITLE_WORDS | frozenset(SEX_TITLES)
_original = F._characters


def fold(kept, screenplay):
    cues = [e.cue for sc in screenplay.scenes for e in sc.elements if isinstance(e, Dialogue)]
    chars = [k for k in kept if k.kind is EntityKind.CHARACTER]
    spellings: dict[str, str] = {}
    for name in [k.name for k in chars] + cues:
        words = normalise(name).split()
        if words and set(words) & TITLES and set(words) - TITLES:
            spellings.setdefault(normalise(name), name.strip())
    out = list(kept)
    for k in chars:
        words = set(normalise(k.name).split())
        if not words or words & TITLES:
            continue
        cands = [s for key, s in spellings.items() if set(key.split()) - TITLES == words]
        if len(cands) != 1:
            if cands:
                print(f"    ambiguous {k.name!r}: {cands}")
            continue
        target = cands[0]
        i = out.index(k)
        into = next((j for j, o in enumerate(out) if o.kind is EntityKind.CHARACTER
                     and normalise(o.name) == normalise(target)), None)
        if into is None:
            out[i] = replace(k, name=target, other_names=(*k.other_names, k.name))
        else:
            o = out[into]
            seen = {(q.text, q.span) for q in o.quotes}
            out[into] = replace(o, quotes=[*o.quotes, *(q for q in k.quotes if (q.text, q.span) not in seen)],
                                other_names=(*o.other_names, k.name, *k.other_names))
            out.pop(i)
        print(f"    fold {k.name!r} -> {target!r} ({'merge' if into is not None else 'rename'})")
    return out


def folded(kept, screenplay):
    return _original(fold(kept, screenplay), screenplay)


def proposals(ex):
    return [
        ProposedEntity(name=e.name, kind=e.kind.value, quotes=[q.text for q in e.quotes],
                       species=e.species, other_names=list(e.other_names))
        for e in ex.entities
        if e.source is Source.MODEL and e.kind in (EntityKind.CHARACTER, EntityKind.PROP)
    ]


def summary(entities):
    return {(e.kind.value, e.name): (e.source.value, e.sex and e.sex.value, e.scenes, len(e.quotes))
            for e in entities}


async def main() -> None:
    engine = make_engine(Settings())
    async with make_sessions(engine)() as s:
        rows = (await s.execute(select(ProjectRow).order_by(ProjectRow.created_at))).scalars().all()
    n = changed = 0
    for p in rows:
        if p.extraction is None or p.screenplay is None:
            continue
        n += 1
        sp, props = load_screenplay(p.screenplay), proposals(load_extraction(p.extraction))
        print(f"{p.created_at:%m-%d %H:%M} {p.title}")
        F._characters = _original
        before, rb = F.ground(props, sp)
        F._characters = folded
        after, ra = F.ground(props, sp)
        a, b = summary(before), summary(after)
        diff = {k: (a.get(k), b.get(k)) for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
        if diff or (rb.recall, rb.cues_found_by_model) != (ra.recall, ra.cues_found_by_model):
            changed += 1
            for k, (x, y) in sorted(diff.items()):
                print(f"    {k}: {x} -> {y}")
            print(f"    recall {rb.cues_found_by_model}/{rb.cues_total} -> {ra.cues_found_by_model}/{ra.cues_total}")
    print(f"{n} extractions replayed, {changed} changed")
    await engine.dispose()


asyncio.run(main())
