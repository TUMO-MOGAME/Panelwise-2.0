"""tools.evaluate -- docs/design/eval.md §9. Pure: no model is called here."""

import dataclasses
import re
from pathlib import Path

import pytest

from app.grounding import Entity, EntityKind, Extraction, GroundingReport, Quote, Source
from app.llm import Usage
from app.script import Screenplay, Span, parse_pdf, parse_text
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from tools.build_samples import SAMPLES
from tools.evaluate import (
    EVAL,
    EvalReport,
    EvalRun,
    Stat,
    _parse_args,  # pyright: ignore[reportPrivateUsage]
    check_run,
    from_json,
    summarise,
    table,
    to_json,
)

NO_USAGE = Usage(0, 0, 0)


@pytest.fixture(scope="module")
def kite() -> Screenplay:
    return parse_pdf((SAMPLES / "the-red-kite.pdf").read_bytes())


def extraction_of(screenplay: Screenplay) -> Extraction:
    """One prop per scene with elements, quoting its first element exactly where it is."""
    entities = tuple(
        Entity(
            EntityKind.PROP,
            f"THING {s.index}",
            (Quote(s.elements[0].text, s.index, s.elements[0].span),),
            (s.index,),
            Source.MODEL,
        )
        for s in screenplay.scenes
        if s.elements
    )
    n = len(entities)
    report = GroundingReport(n + 1, n, n / (n + 1), n + 2, n, (), 3, 2, 2 / 3)
    return Extraction(entities, report, ("lightning",), Usage(100, 20, 0))


def plan_of(screenplay: Screenplay) -> ShotPlan:
    """One shot per scene element, as the planner builds them (source = the element text)."""
    shots = tuple(
        Shot(s.index, i + 1, Framing.WIDE, Movement.STATIC, (i,), (), (), None, "", e.span, e.text)
        for s in screenplay.scenes
        for i, e in enumerate(s.elements)
    )
    report = PlanReport(len(screenplay.scenes), len(shots), 1, 2, 3)
    return ShotPlan(shots, report, ("lightning",), Usage(300, 40, 5))


def run_of(sample: str, run: int, **kw: object) -> EvalRun:
    base = EvalRun(
        sample=sample,
        run=run,
        error=None,
        faithfulness=1.0,
        entities_grounded=4,
        entities_proposed=4,
        quotes_located=10,
        quotes_proposed=10,
        recall=1.0,
        cues_found=3,
        cues_total=3,
        shots=20,
        partitioned=True,
        ungrounded_kept=0,
        names_dropped=0,
        ranges_repaired=0,
        tokens_in=1000,
        tokens_out=200,
        seconds=5.0,
    )
    return dataclasses.replace(base, **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- check_run


def test_check_run_reads_every_number_off_the_extraction_and_plan(kite: Screenplay) -> None:
    extraction, plan = extraction_of(kite), plan_of(kite)
    run = check_run(kite, extraction, plan, sample="the-red-kite", run=2, seconds=1.5)
    n = len(kite.scenes)
    assert run == EvalRun(
        sample="the-red-kite",
        run=2,
        error=None,
        faithfulness=n / (n + 1),
        entities_grounded=n,
        entities_proposed=n + 1,
        quotes_located=n,
        quotes_proposed=n + 2,
        recall=2 / 3,
        cues_found=2,
        cues_total=3,
        shots=len(plan.shots),
        partitioned=True,
        ungrounded_kept=0,
        names_dropped=5,
        ranges_repaired=1,
        tokens_in=400,
        tokens_out=60,
        seconds=1.5,
    )


def test_a_quote_moved_to_another_span_is_ungrounded(kite: Screenplay) -> None:
    extraction = extraction_of(kite)
    first, second, *rest = extraction.entities
    moved = Quote(first.quotes[0].text, second.quotes[0].scene_index, second.quotes[0].span)
    bad = dataclasses.replace(
        extraction, entities=(dataclasses.replace(first, quotes=(moved,)), second, *rest)
    )
    run = check_run(kite, bad, plan_of(kite), sample="s", run=1, seconds=0)
    assert run.ungrounded_kept == 1


def test_an_edited_shot_source_is_ungrounded(kite: Screenplay) -> None:
    plan = plan_of(kite)
    first, *rest = plan.shots
    edited = dataclasses.replace(first, source=first.source + " A dragon lands.")
    bad = dataclasses.replace(plan, shots=(edited, *rest))
    run = check_run(kite, extraction_of(kite), bad, sample="s", run=1, seconds=0)
    assert run.ungrounded_kept == 1


def test_a_shot_citing_the_wrong_span_is_ungrounded(kite: Screenplay) -> None:
    plan = plan_of(kite)
    first, second, *rest = plan.shots
    swapped = dataclasses.replace(first, span=second.span)
    bad = dataclasses.replace(plan, shots=(swapped, second, *rest))
    run = check_run(kite, extraction_of(kite), bad, sample="s", run=1, seconds=0)
    assert run.ungrounded_kept == 1


def test_a_heading_only_scene_shot_cites_its_heading() -> None:
    # planner.py: a scene with no elements gets one establishing shot citing the heading.
    screenplay = parse_text(
        "INT. ROOM - DAY\n\nShe waits.\n\nEXT. ROOF - NIGHT\n\nINT. ROOM - DAY\n\nShe sleeps."
    )
    plan = plan_of(screenplay)
    empty = screenplay.scenes[1]
    heading = Span(empty.span.page, empty.span.line_start, empty.span.line_start)
    establishing = Shot(
        1, 1, Framing.WIDE, Movement.STATIC, (), (), (), "NIGHT", "", heading, empty.heading
    )
    shots = (*plan.shots[:1], establishing, *plan.shots[1:])
    good = dataclasses.replace(plan, shots=shots)
    run = check_run(screenplay, extraction_of(screenplay), good, sample="s", run=1, seconds=0)
    assert (run.ungrounded_kept, run.partitioned) == (0, True)
    wrong = dataclasses.replace(establishing, source="EXT. ROOF - NIGHT. A kite.")
    bad = dataclasses.replace(plan, shots=(*plan.shots[:1], wrong, *plan.shots[1:]))
    run = check_run(screenplay, extraction_of(screenplay), bad, sample="s", run=1, seconds=0)
    assert run.ungrounded_kept == 1


def test_a_plan_that_skips_an_element_is_not_partitioned(kite: Screenplay) -> None:
    plan = plan_of(kite)
    bad = dataclasses.replace(plan, shots=plan.shots[1:])
    run = check_run(kite, extraction_of(kite), bad, sample="s", run=1, seconds=0)
    assert not run.partitioned


# ------------------------------------------------------------------- summarise, table


def test_summarise_gives_mean_min_max_and_counts_a_failed_run_without_its_numbers() -> None:
    runs = [
        run_of("a", 1, faithfulness=0.5, recall=1.0, shots=10),
        run_of("a", 2, faithfulness=1.0, recall=0.5, shots=14, partitioned=False),
        run_of("a", 3, error="ExtractionError: chunk 2", faithfulness=0.0, shots=0),
        run_of("b", 1, ungrounded_kept=2),
    ]
    a, b = summarise(runs)
    assert (a.sample, a.runs, a.failed) == ("a", 3, 1)
    assert a.faithfulness == Stat(0.75, 0.5, 1.0)
    assert a.recall == Stat(0.75, 0.5, 1.0)
    assert a.shots == Stat(12.0, 10.0, 14.0)
    assert not a.always_partitioned
    assert (b.sample, b.runs, b.failed, b.ungrounded_kept) == ("b", 1, 0, 2)
    assert b.always_partitioned


def test_a_sample_whose_every_run_failed_has_no_stats() -> None:
    (only,) = summarise([run_of("a", 1, error="LLMError: 503")])
    assert (only.runs, only.failed, only.faithfulness, only.always_partitioned) == (
        1,
        1,
        None,
        False,
    )


def test_the_pooled_row_is_a_micro_average_not_a_mean_of_means() -> None:
    report = EvalReport(
        date="2026-10-01",
        models=("lightning",),
        command="uv run python -m tools.evaluate --runs 2",
        runs=(
            run_of("a", 1, entities_grounded=1, entities_proposed=2, cues_found=0, cues_total=1),
            run_of("b", 1, entities_grounded=9, entities_proposed=9, cues_found=4, cues_total=4),
            run_of("b", 2, error="LLMError: 503"),
        ),
    )
    pooled = table(report).splitlines()[-1]
    assert pooled.startswith("| **All** |")
    assert "0.909 (10/11)" in pooled  # not (0.5 + 1.0) / 2
    assert "0.800 (4/5)" in pooled
    assert "3 (1)" in pooled


def test_table_has_one_row_per_sample_then_the_pooled_row() -> None:
    report = EvalReport("2026-10-01", ("lightning",), "cmd", (run_of("a", 1), run_of("b", 1)))
    rows = [r for r in table(report).splitlines() if r.startswith("| ")]
    assert [r.split("|")[1].strip() for r in rows[2:]] == ["`a`", "`b`", "**All**"]


def test_json_round_trips() -> None:
    report = EvalReport(
        "2026-10-01", ("a", "b"), "cmd", (run_of("a", 1), run_of("a", 2, error="x"))
    )
    assert from_json(to_json(report)) == report


# ------------------------------------------------------------- the committed numbers


def newest_result() -> Path:
    results = sorted(
        (EVAL / "results").glob("extraction-*.json"),
        key=lambda p: [int(n) for n in re.findall(r"\d+", p.stem)],
    )
    assert results, "no committed eval/results/extraction-*.json"
    return results[-1]


def test_the_readme_table_is_the_newest_committed_result() -> None:
    readme = (EVAL / "README.md").read_text(encoding="utf-8")
    report = from_json(newest_result().read_text(encoding="utf-8"))
    assert table(report) in readme
    assert newest_result().name in readme
    assert all(r.ungrounded_kept == 0 for r in report.runs)


@pytest.mark.parametrize(
    "argv",
    [
        ["--runs"],
        ["--runs", "abc"],
        ["--runs", "2.5"],
        ["--runs", "0"],
        ["--out"],
        ["--out", "--runs", "2"],
        ["--out", "results/"],
        ["--out", "."],
        ["--runs", "\u00b2"],
        ["nonsense"],
    ],
)
def test_malformed_arguments_give_usage_before_any_paid_call(argv: list[str]) -> None:
    assert _parse_args(argv) is None


def test_arguments_parse() -> None:
    assert _parse_args([]) == (5, None, ["lost-property", "sipho-and-siphokazi", "the-red-kite"])
    assert _parse_args(["--runs", "2", "--out", "x.json", "the-red-kite"]) == (
        2,
        Path("x.json"),
        ["the-red-kite"],
    )
