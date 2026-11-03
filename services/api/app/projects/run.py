"""Run the pipeline core on a screenplay PDF on the real account, as a job would.

    cd services/api && uv run python -m app.projects.run path/to/script.pdf

Prints each stage as it begins with the job's progress and the seconds since the start, then a
summary of what each stage made, or the stage that failed with the copy the user would read and
the detail behind it. Only public-domain or self-written scripts: never a copyrighted one.
"""

import asyncio
import sys
import time
from pathlib import Path

from app.core.config import Settings
from app.llm import LLMError, NebiusChatModel
from app.projects.pipeline import (
    BANDS,
    PipelineError,
    PipelineResult,
    Stage,
    StageResult,
    run_pipeline,
)


def summary(result: PipelineResult) -> str:
    s, e, p = result.screenplay, result.extraction, result.plan
    kinds = [str(entity.kind) for entity in e.entities]
    r = e.report
    covered = all(
        [i for shot in p.shots if shot.scene_index == scene.index for i in shot.elements]
        == list(range(len(scene.elements)))
        for scene in s.scenes
    )
    return "\n".join(
        [
            f"script       {s.page_count} pages (starting at lines "
            f"{', '.join(map(str, s.page_starts))}), {len(s.scenes)} scenes, "
            f"{sum(len(scene.elements) for scene in s.scenes)} elements",
            f"entities     {kinds.count('character')} characters, {kinds.count('prop')} props, "
            f"{kinds.count('location')} locations",
            f"faithfulness {r.faithfulness:.3f}  ({r.entities_grounded}/{r.entities_proposed} "
            f"entities, {r.quotes_located}/{r.quotes_proposed} quotes)",
            f"recall       {r.recall:.3f}  ({r.cues_found_by_model}/{r.cues_total} speakers)",
            f"shots        {len(p.shots)}; every element in exactly one shot: "
            f"{'yes' if covered else 'NO'}",
            f"models       {', '.join(dict.fromkeys((*e.models, *p.models)))}",
            f"tokens       extraction in={e.usage.prompt_tokens} out={e.usage.completion_tokens}; "
            f"planning in={p.usage.prompt_tokens} out={p.usage.completion_tokens}",
        ]
    )


async def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        pdf = await asyncio.to_thread(Path(argv[0]).read_bytes)
        model = NebiusChatModel.from_settings(Settings())
    except (OSError, LLMError) as exc:
        print(f"FAIL  {exc}")
        return 1

    start = time.monotonic()

    async def on_advance(stage: Stage, progress: int, finished: StageResult | None) -> None:
        made = f"  (after {type(finished).__name__})" if finished is not None else ""
        print(f"{time.monotonic() - start:7.1f}s  {stage:<10} {progress:>3}%{made}", flush=True)

    try:
        result = await run_pipeline(pdf, model, on_advance=on_advance)
    except PipelineError as exc:
        print(f"FAIL  at {exc.stage}: {exc.message}")
        print(f"      detail: {exc.__cause__!r}")
        return 1
    finally:
        await model.aclose()
    done = BANDS[Stage.PLANNING][1]
    print(f"{time.monotonic() - start:7.1f}s  {'done':<10} {done:>3}%  (after ShotPlan)")
    print()
    print(summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
