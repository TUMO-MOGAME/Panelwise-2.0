"""Extraction and shot-plan numbers on the samples, on the real account (docs/design/eval.md).

    cd services/api && uv run python -m tools.evaluate [--runs N] [--out PATH] [sample ...]

Runs extract + plan_shots over each sample (T031's three by default) N times (default 5), re-checks
in code that every kept quote and every shot cites verbatim script text, writes every run to
eval/results/extraction-<date>.json, and prints the table eval/README.md carries. Exits 1 if
anything ungrounded was kept. Only self-written samples: never a copyrighted script.
"""

import asyncio
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from app.core.config import Settings
from app.grounding import extract, normalize_for_grounding
from app.grounding.model import Extraction
from app.llm import LLMError, NebiusChatModel
from app.script import Screenplay, ScriptParseError, Span, parse_pdf
from app.shots import Shot, ShotPlan, plan_shots
from tools.build_samples import OPTIONS, SAMPLES

EVAL = SAMPLES.parent / "eval"
# The T031 three, the set eval/README.md's numbers are over; a later sample is run by naming it.
DEFAULT_SAMPLES = ["lost-property", "sipho-and-siphokazi", "the-red-kite"]


@dataclass(frozen=True)
class EvalRun:
    """One extract + plan_shots over one sample. A failed run keeps its error and zeroes."""

    sample: str
    run: int
    error: str | None
    faithfulness: float
    entities_grounded: int
    entities_proposed: int
    quotes_located: int
    quotes_proposed: int
    recall: float
    cues_found: int
    cues_total: int
    shots: int
    partitioned: bool
    ungrounded_kept: int
    names_dropped: int
    ranges_repaired: int
    tokens_in: int
    tokens_out: int
    seconds: float


@dataclass(frozen=True)
class Stat:
    mean: float
    min: float
    max: float


@dataclass(frozen=True)
class SampleSummary:
    sample: str
    runs: int
    failed: int
    faithfulness: Stat | None  # None when every run failed
    recall: Stat | None
    shots: Stat | None
    always_partitioned: bool
    ungrounded_kept: int


@dataclass(frozen=True)
class EvalReport:
    date: str
    models: tuple[str, ...]
    command: str
    runs: tuple[EvalRun, ...]


def _lines(screenplay: Screenplay, span: Span) -> str:
    lines = screenplay.text.split("\n")
    return normalize_for_grounding("\n".join(lines[span.line_start - 1 : span.line_end]))


def _cites(screenplay: Screenplay, shot: Shot) -> bool:
    """The shot cites exactly what it covers: its elements' text, from the first one's start to
    the last one's end -- or, with no elements (a heading-only scene), the heading line."""
    scene = screenplay.scenes[shot.scene_index]
    if not shot.elements:
        heading = Span(scene.span.page, scene.span.line_start, scene.span.line_start)
        return shot.span == heading and shot.source == scene.heading
    covered = [scene.elements[i] for i in shot.elements]
    span = Span(covered[0].span.page, covered[0].span.line_start, covered[-1].span.line_end)
    return (
        shot.span == span
        and shot.source == "\n".join(e.text for e in covered)
        and all(normalize_for_grounding(e.text) == _lines(screenplay, e.span) for e in covered)
    )


def check_run(
    screenplay: Screenplay,
    extraction: Extraction,
    plan: ShotPlan,
    *,
    sample: str,
    run: int,
    seconds: float,
) -> EvalRun:
    """The run's numbers, with Non-negotiable I re-checked here rather than taken from the
    filter: a kept quote must sit inside its span's lines, and a shot must cite exactly the
    elements it covers, by span and by text (eval.md §3)."""
    ungrounded = sum(
        normalize_for_grounding(q.text) not in _lines(screenplay, q.span)
        for e in extraction.entities
        for q in e.quotes
    )
    ungrounded += sum(not _cites(screenplay, shot) for shot in plan.shots)
    partitioned = all(
        [i for s in plan.shots if s.scene_index == sc.index for i in s.elements]
        == list(range(len(sc.elements)))
        for sc in screenplay.scenes
    )
    g, p = extraction.report, plan.report
    return EvalRun(
        sample=sample,
        run=run,
        error=None,
        faithfulness=g.faithfulness,
        entities_grounded=g.entities_grounded,
        entities_proposed=g.entities_proposed,
        quotes_located=g.quotes_located,
        quotes_proposed=g.quotes_proposed,
        recall=g.recall,
        cues_found=g.cues_found_by_model,
        cues_total=g.cues_total,
        shots=len(plan.shots),
        partitioned=partitioned,
        ungrounded_kept=ungrounded,
        names_dropped=p.characters_dropped + p.props_dropped,
        ranges_repaired=p.ranges_repaired,
        tokens_in=extraction.usage.prompt_tokens + plan.usage.prompt_tokens,
        tokens_out=extraction.usage.completion_tokens + plan.usage.completion_tokens,
        seconds=seconds,
    )


def failed_run(sample: str, run: int, error: str, seconds: float) -> EvalRun:
    return EvalRun(sample, run, error, 0.0, 0, 0, 0, 0, 0.0, 0, 0, 0, False, 0, 0, 0, 0, 0, seconds)


def _stat(values: Sequence[float]) -> Stat | None:
    if not values:
        return None
    return Stat(sum(values) / len(values), min(values), max(values))


def summarise(runs: Sequence[EvalRun]) -> list[SampleSummary]:
    """One summary per sample, in first-seen order. Stats are over the runs that didn't fail;
    failed runs are counted."""
    samples = list(dict.fromkeys(r.sample for r in runs))
    out: list[SampleSummary] = []
    for sample in samples:
        mine = [r for r in runs if r.sample == sample]
        ok = [r for r in mine if r.error is None]
        out.append(
            SampleSummary(
                sample=sample,
                runs=len(mine),
                failed=len(mine) - len(ok),
                faithfulness=_stat([r.faithfulness for r in ok]),
                recall=_stat([r.recall for r in ok]),
                shots=_stat([float(r.shots) for r in ok]),
                always_partitioned=bool(ok) and all(r.partitioned for r in ok),
                ungrounded_kept=sum(r.ungrounded_kept for r in mine),
            )
        )
    return out


def _ratio(stat: Stat | None, digits: int = 3) -> str:
    if stat is None:
        return "—"
    return f"{stat.mean:.{digits}f} ({stat.min:.{digits}f}\u2013{stat.max:.{digits}f})"


def _micro(part: int, whole: int) -> str:
    return f"{part / whole:.3f} ({part}/{whole})" if whole else "—"


HEADER = (
    "| Sample | Runs (failed) | Faithfulness mean (min\u2013max) | Recall mean (min\u2013max) "
    "| Shots mean (min\u2013max) | Every element once | Ungrounded kept |\n"
    "| --- | --- | --- | --- | --- | --- | --- |"
)


def table(report: EvalReport) -> str:
    """eval/README.md's table: a row per sample, then all runs pooled (micro averages)."""
    rows = [HEADER]
    for s in summarise(report.runs):
        once = "yes, every run" if s.always_partitioned else "**no**"
        rows.append(
            f"| `{s.sample}` | {s.runs} ({s.failed}) | {_ratio(s.faithfulness)} "
            f"| {_ratio(s.recall)} | {_ratio(s.shots, 1)} | {once} | {s.ungrounded_kept} |"
        )
    ok = [r for r in report.runs if r.error is None]
    failed = len(report.runs) - len(ok)
    pooled_once = "yes, every run" if ok and all(r.partitioned for r in ok) else "**no**"
    rows.append(
        f"| **All** | {len(report.runs)} ({failed}) "
        f"| {_micro(sum(r.entities_grounded for r in ok), sum(r.entities_proposed for r in ok))} "
        f"| {_micro(sum(r.cues_found for r in ok), sum(r.cues_total for r in ok))} "
        f"| {sum(r.shots for r in ok)} in all | {pooled_once} "
        f"| {sum(r.ungrounded_kept for r in report.runs)} |"
    )
    return "\n".join(rows)


def to_json(report: EvalReport) -> str:
    return json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n"


def from_json(text: str) -> EvalReport:
    data = json.loads(text)
    return EvalReport(
        date=data["date"],
        models=tuple(data["models"]),
        command=data["command"],
        runs=tuple(EvalRun(**r) for r in data["runs"]),
    )


def result_path(day: str) -> Path:
    """eval/results/extraction-<day>.json, or -2, -3 ... : a result is never overwritten."""
    base = EVAL / "results" / f"extraction-{day}"
    path, n = base.with_suffix(".json"), 1
    while path.exists():
        n += 1
        path = base.parent / f"{base.name}-{n}.json"
    return path


async def _one(model: NebiusChatModel, screenplay: Screenplay, sample: str, run: int) -> EvalRun:
    start = time.monotonic()
    try:
        extraction = await extract(model, screenplay)
        plan = await plan_shots(model, screenplay, extraction)
    except Exception as exc:
        return failed_run(sample, run, f"{type(exc).__name__}: {exc}", time.monotonic() - start)
    seconds = round(time.monotonic() - start, 1)
    return check_run(screenplay, extraction, plan, sample=sample, run=run, seconds=seconds)


def _parse_args(argv: list[str]) -> tuple[int, Path | None, list[str]] | None:
    """(runs, out, samples), or None for anything malformed: usage, before any paid call."""
    runs, out, samples = 5, None, list[str]()
    args = iter(argv)
    for arg in args:
        if arg == "--runs":
            value = next(args, "")
            if not (value.isascii() and value.isdigit()):
                return None
            runs = int(value)
        elif arg == "--out":
            value = next(args, "")
            if (
                not value
                or value.startswith("--")
                or value.endswith(("/", "\\"))
                or Path(value).is_dir()
            ):
                return None
            out = Path(value)
        elif arg in OPTIONS:
            samples.append(arg)
        else:
            return None
    return (runs, out, samples or DEFAULT_SAMPLES) if runs > 0 else None


def _save(path: Path, report: EvalReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(report), encoding="utf-8")


async def main(argv: list[str]) -> int:
    parsed = _parse_args(argv)
    if parsed is None:
        print(__doc__)
        return 2
    runs, out, samples = parsed
    try:
        screenplays = {s: parse_pdf((SAMPLES / f"{s}.pdf").read_bytes()) for s in samples}
        settings = Settings()
        model = NebiusChatModel.from_settings(settings)
    except (OSError, ScriptParseError, LLMError) as exc:
        print(f"FAIL  {exc}")
        return 1
    day = date.today().isoformat()
    path = out or result_path(day)
    command = " ".join(["uv run python -m tools.evaluate", *argv])
    report = EvalReport(day, (settings.nebius_model_fast,), command, ())
    try:
        for sample in samples:  # sequential: no rate-limit surprises
            for n in range(1, runs + 1):
                result = await _one(model, screenplays[sample], sample, n)
                print(
                    f"{sample} run {n}: "
                    + (
                        result.error
                        or f"faithfulness {result.faithfulness:.3f}, recall "
                        f"{result.recall:.3f}, {result.shots} shots, {result.seconds} s"
                    ),
                    flush=True,
                )
                # Saved after every run, so an interrupted eval keeps what it has paid for.
                report = replace(report, runs=(*report.runs, result))
                _save(path, report)
    finally:
        await model.aclose()
    print(f"\nwrote {path}\n\n{table(report)}")
    return 1 if any(r.ungrounded_kept for r in report.runs) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
