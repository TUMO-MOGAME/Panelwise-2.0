"""Parse a screenplay PDF and extract its grounded entities on the real account.

    cd services/api && uv run python -m app.grounding.run path/to/script.pdf

Prints every entity with the page and lines its first quote came from, then faithfulness,
recall, what was dropped and why, the model that answered and the tokens spent. The Phase 1
checkpoint. Only public-domain or self-written scripts: never a copyrighted one.
"""

import asyncio
import sys
from pathlib import Path

from app.core.config import Settings
from app.grounding import Extraction, ExtractionError, extract
from app.llm import LLMError, NebiusChatModel
from app.script import ScriptParseError, parse_pdf


def report(result: Extraction, numbers: list[str]) -> str:
    out: list[str] = []
    for e in result.entities:
        q = e.quotes[0]
        where = f"p.{q.span.page} l.{q.span.line_start}-{q.span.line_end}"
        scenes = ",".join(numbers[i] for i in e.scenes)
        extra = (f"  [species: {e.species}]" if e.species else "") + (
            f"  [also: {', '.join(e.other_names)}]" if e.other_names else ""
        )
        out.append(
            f"{e.kind:<9} {e.name:<24} {e.source:<7} scenes {scenes:<10} {where:<12} “{q.text}”"
            + extra
        )
    r = result.report
    out += [
        "",
        f"faithfulness {r.faithfulness:.3f}  ({r.entities_grounded}/{r.entities_proposed} "
        f"entities fully grounded; {r.quotes_located}/{r.quotes_proposed} quotes located)",
        f"recall       {r.recall:.3f}  ({r.cues_found_by_model}/{r.cues_total} speaking "
        "characters found by the model)",
    ]
    out += [f"dropped      {d.kind} {d.name!r}: {d.reason}" for d in r.dropped]
    u = result.usage
    out.append(
        f"model        {', '.join(result.models)}  tokens in={u.prompt_tokens} "
        f"out={u.completion_tokens} reasoning={u.reasoning_tokens}"
    )
    return "\n".join(out)


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
        result = await extract(model, screenplay)
    except ExtractionError as exc:
        print(f"FAIL  {exc}")
        return 1
    finally:
        await model.aclose()
    print(report(result, [s.number for s in screenplay.scenes]))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
