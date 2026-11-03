"""Audit one frame against one shot of a screenplay, on the real account.

    cd services/api && uv run python -m app.verify.run path/to/script.pdf 1.2 path/to/frame.png

`1.2` is scene number 1, shot 2 of the shot plan. Parses, extracts and plans the script, then
prints what the vision model saw, how Nemotron called each person and object, every check and the
verdict. Only public-domain or self-written scripts: never a copyrighted one.
"""

import asyncio
import sys
from pathlib import Path

from app.core.config import Settings
from app.grounding import ExtractionError, extract
from app.llm import LLMError, NebiusChatModel
from app.script import ScriptParseError, parse_pdf
from app.shots import ShotError, plan_shots
from app.verify import Audit, RenderedFrame, audit_frame, seed_for


def report(audit: Audit) -> str:
    out: list[str] = []
    d, j = audit.description, audit.judgement
    if d is not None:
        out.append(f"seen         {d.setting}, {d.light}, {d.shot_size}, text: {d.has_text}")
        out += [f"  person {i}   {p.position}: {p.appearance}" for i, p in enumerate(d.people)]
        out += [
            f"  object {i}   {o.name} ({o.category}{', held' if o.held else ''})"
            for i, o in enumerate(d.objects)
        ]
    if j is not None:
        out += [f"  person {c.person}   -> {c.character} support={c.support!r}" for c in j.people]
        out += [f"  object {c.object}   -> {c.kind} support={c.support!r}" for c in j.objects]
    out += [
        f"{'ok  ' if c.ok else 'FAIL'} {c.severity:<4} {c.check:<18} {c.detail}"
        for c in audit.checks
    ]
    u = audit.usage
    out += [
        f"verdict      {audit.verdict}  positions {dict(audit.positions)}",
        f"models       {', '.join(audit.models)}  tokens in={u.prompt_tokens} "
        f"out={u.completion_tokens} reasoning={u.reasoning_tokens}",
    ]
    return "\n".join(out)


async def main(argv: list[str]) -> int:
    if len(argv) != 3 or "." not in argv[1]:
        print(__doc__)
        return 2
    scene_number, _, shot_number = argv[1].partition(".")
    try:
        screenplay = parse_pdf(await asyncio.to_thread(Path(argv[0]).read_bytes))
        png = await asyncio.to_thread(Path(argv[2]).read_bytes)
        model = NebiusChatModel.from_settings(Settings())
    except (OSError, ScriptParseError, LLMError) as exc:
        print(f"FAIL  {exc}")
        return 1
    try:
        extraction = await extract(model, screenplay)
        plan = await plan_shots(model, screenplay, extraction)
        shot = next(
            (
                s
                for s in plan.shots
                if screenplay.scenes[s.scene_index].number == scene_number
                and str(s.number) == shot_number
            ),
            None,
        )
        if shot is None:
            print(f"FAIL  no shot {argv[1]} in the plan ({len(plan.shots)} shots)")
            return 1
        print(
            f"shot         {argv[1]} {shot.framing} [{', '.join(shot.characters)}] "
            f"[{', '.join(shot.props)}] {shot.time_of_day}"
        )
        print(f"             “{shot.source}”")
        frame = RenderedFrame(
            (shot.scene_index, shot.number), 1, seed_for(shot, 1), png, 0, 0, "(from file)"
        )
        audit = await audit_frame(model, frame, shot, screenplay, extraction)
    except (ExtractionError, ShotError) as exc:
        print(f"FAIL  {exc}")
        return 1
    finally:
        await model.aclose()
    print(report(audit))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
