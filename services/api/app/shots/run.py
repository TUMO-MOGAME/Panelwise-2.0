"""Parse a screenplay PDF, extract its entities and plan its shots on the real account.

    cd services/api && uv run python -m app.shots.run path/to/script.pdf

Prints every shot with its framing, what's in frame, the page and lines it covers and the verbatim
text it cites, then checks that every scene element is in exactly one shot. Only public-domain or
self-written scripts: never a copyrighted one.
"""

import asyncio
import sys
from pathlib import Path

from app.core.config import Settings
from app.grounding import ExtractionError, extract
from app.llm import LLMError, NebiusChatModel, Usage
from app.script import Screenplay, ScriptParseError, parse_pdf
from app.shots import ShotError, ShotPlan, plan_shots


def report(plan: ShotPlan, screenplay: Screenplay, extraction_usage: Usage) -> tuple[str, bool]:
    out: list[str] = []
    for s in plan.shots:
        scene = screenplay.scenes[s.scene_index]
        cast = ", ".join((*s.characters, *s.props)) or "-"
        out.append(
            f"{scene.number}.{s.number:<3} {s.framing:<16} {s.movement:<9} p.{s.span.page} "
            f"l.{s.span.line_start}-{s.span.line_end:<5} [{cast}]"
        )
        out += [f"        “{line}”" for line in s.source.splitlines()]
    partitioned = all(
        [i for s in plan.shots if s.scene_index == sc.index for i in s.elements]
        == list(range(len(sc.elements)))
        for sc in screenplay.scenes
    )
    r = plan.report
    u = plan.usage
    out += [
        "",
        f"shots        {r.shots} over {r.scenes} scenes; every element in exactly one shot: "
        f"{'yes' if partitioned else 'NO'}",
        f"repaired     {r.ranges_repaired} ranges; dropped {r.characters_dropped} character and "
        f"{r.props_dropped} prop names not in the scene",
        f"added        {r.characters_added} characters an action line names (T092)",
        f"model        {', '.join(plan.models)}  planning tokens in={u.prompt_tokens} "
        f"out={u.completion_tokens} reasoning={u.reasoning_tokens} (extraction in="
        f"{extraction_usage.prompt_tokens} out={extraction_usage.completion_tokens})",
    ]
    return "\n".join(out), partitioned


async def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        screenplay = parse_pdf(await asyncio.to_thread(Path(argv[0]).read_bytes))
        model = NebiusChatModel.from_settings(Settings())
    except (OSError, ScriptParseError, LLMError) as exc:
        print(f"FAIL  {exc}")
        return 1
    try:
        extraction = await extract(model, screenplay)
        plan = await plan_shots(model, screenplay, extraction)
    except (ExtractionError, ShotError) as exc:
        print(f"FAIL  {exc}")
        return 1
    finally:
        await model.aclose()
    text, partitioned = report(plan, screenplay, extraction.usage)
    print(text)
    return 0 if partitioned else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
