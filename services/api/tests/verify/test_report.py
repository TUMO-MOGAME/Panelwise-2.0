"""T081: the run report (docs/design/learning.md §3, §6, §9). Pure: hand-built rows, with check
details made by `run_checks` itself so the parsers are tested against the real shapes."""

import dataclasses
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.frames.model import AuditTarget, FrameAuditRow, FrameRow
from app.grounding import Extraction
from app.llm import Usage
from app.projects.codec import dump_extraction, dump_plan, dump_screenplay
from app.projects.model import ProjectRow
from app.script import Screenplay
from app.shots import PlanReport, Shot, ShotPlan
from app.storyboard.styles import PUBLIC_STYLES, StyleRegistry, load_styles
from app.verify import Severity, run_checks
from app.verify.report import (
    NOT_DRAWN,
    build_report,
    object_causes,
    person_causes,
    text_causes,
    to_markdown,
)
from tests.verify.conftest import described, judged, kitchen_shot

PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000081")
T0 = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)


def _label(scene_index: int, number: int) -> str:
    return f"{scene_index + 1}.{number}"


def _checks(screenplay: Screenplay, extraction: Extraction, **kw: Any) -> list[dict[str, Any]]:
    """`run_checks`' output, stored as `FrameWriter` stores it (frames/writer.py)."""
    checks, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(**kw.get("description", {})),
        judged(**kw.get("judgement", {})),
        extraction,
    )
    return [
        {"check": c.check.value, "severity": c.severity.value, "ok": c.ok, "detail": c.detail}
        for c in checks
    ]


def _audit(
    number: int,
    attempt: int,
    verdict: str,
    checks: list[dict[str, Any]],
    *,
    target: AuditTarget = AuditTarget.STORYBOARD,
    minutes: int = 0,
) -> FrameAuditRow:
    return FrameAuditRow(
        project_id=PROJECT,
        job_id=PROJECT,
        target=target.value,
        scene_index=0,
        shot_number=number,
        attempt=attempt,
        seed=attempt,
        frame_asset=f"frames/{number}/{attempt}.png",
        description=None,
        judgement=None,
        checks=checks,
        positions={},
        verdict=verdict,
        models=["describer", "judge"],
        prompt_tokens=100,
        completion_tokens=10,
        created_at=T0 + timedelta(minutes=minutes),
    )


def _frame(number: int, state: str, attempt: int) -> FrameRow:
    return FrameRow(
        project_id=PROJECT,
        scene_index=0,
        shot_number=number,
        state=state,
        attempt=attempt,
        job_id=PROJECT,
    )


def _project(screenplay: Screenplay, extraction: Extraction, shots: list[Shot]) -> ProjectRow:
    plan = ShotPlan(tuple(shots), PlanReport(1, len(shots), 0, 0, 0), (), Usage(0, 0, 0))
    return ProjectRow(
        id=PROJECT,
        owner=PROJECT,
        title="the lighthouse",
        pdf_path="scripts/x.pdf",
        screenplay=dump_screenplay(screenplay),
        extraction=dump_extraction(extraction),
        plan=dump_plan(plan),
    )


@pytest.fixture
def styles() -> StyleRegistry:
    return load_styles(PUBLIC_STYLES, None)


# --- causes ---------------------------------------------------------------------------------


def _vehicle_and_rope(screenplay: Screenplay, extraction: Extraction) -> list[dict[str, Any]]:
    return _checks(
        screenplay,
        extraction,
        description={
            "objects": [
                {"name": "boat masts", "category": "vehicle", "held": False},
                {"name": "rope; coiled", "category": "other", "held": False},
            ]
        },
        judgement={
            "objects": [
                {"object": 0, "kind": "set_dressing", "support": "INT. KITCHEN"},
                {"object": 1, "kind": "unscripted", "support": None},
            ]
        },
    )


def _dog_and_rope(screenplay: Screenplay, extraction: Extraction) -> list[dict[str, Any]]:
    """A hard object failure: since T089 only an animal or a weapon withholds a frame."""
    return _checks(
        screenplay,
        extraction,
        description={
            "objects": [
                {"name": "dog", "category": "animal", "held": False},
                {"name": "rope; coiled", "category": "other", "held": False},
            ]
        },
        judgement={
            "objects": [
                {"object": 0, "kind": "set_dressing", "support": "INT. KITCHEN"},
                {"object": 1, "kind": "unscripted", "support": None},
            ]
        },
    )


def test_object_causes_key_by_category_and_reason(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    rows = [_audit(1, 1, "fail", _vehicle_and_rope(screenplay, extraction))]
    causes = {c.key: c for c in object_causes(rows)}
    assert causes["vehicle · never set dressing"].count == 1
    assert causes["vehicle · never set dressing"].examples == ("boat masts",)
    # a name holding "; " is still one object, not two pieces; unheld, it is background (T083)
    assert causes["other · not in the script"].examples == ("rope; coiled",)
    assert "other" not in causes


def test_person_causes_key_by_the_appearance_noun_phrase(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    def stranger(appearance: str) -> list[dict[str, Any]]:
        return _checks(
            screenplay,
            extraction,
            description={"people": [{"position": "left", "appearance": appearance}]},
            judgement={"people": [{"person": 0, "character": None, "support": None}]},
        )

    rows = [
        _audit(1, 1, "fail", stranger("An old man with white hair, standing")),
        _audit(1, 2, "fail", stranger("an old man in a coat")),
        _audit(1, 3, "fail", stranger("a teenage boy")),
    ]
    causes = person_causes(rows)
    assert [(c.key, c.count) for c in causes] == [("an old man", 2), ("a teenage boy", 1)]
    assert causes[0].examples == ("no shot character, no support",)


def test_text_causes_read_the_string_back_and_list_shots(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    painted = _checks(
        screenplay, extraction, description={"has_text": True, "text": ["JO'S CAFE", "MILK"]}
    )
    rows = [_audit(2, 1, "fail", painted), _audit(1, 1, "fail", painted)]
    causes = {c.key: c for c in text_causes(rows, label=_label)}
    assert causes["JO'S CAFE"].count == 2
    assert causes["JO'S CAFE"].examples == ("1.1", "1.2")  # plan order, each once
    assert causes["MILK"].count == 2


def test_unknown_shapes_count_as_other_and_ok_checks_are_never_read() -> None:
    rows = [
        _audit(
            1,
            1,
            "fail",
            [
                {"check": "unscripted_object", "severity": "hard", "ok": False, "detail": "odd"},
                {"check": "unscripted_object", "severity": "hard", "ok": True, "detail": "x"},
                {
                    "check": "unscripted_person",
                    "severity": "hard",
                    "ok": False,
                    "detail": "person 0 (left, , in a coat): no shot character, no support",
                },
            ],
        )
    ]
    assert [(c.key, c.examples) for c in object_causes(rows)] == [("other", ("odd",))]
    assert [c.key for c in person_causes(rows)] == ["other"]


# --- the report -----------------------------------------------------------------------------


def _five_shots() -> list[Shot]:
    return [dataclasses.replace(kitchen_shot(), number=n) for n in range(1, 6)]


def _run(
    screenplay: Screenplay, extraction: Extraction
) -> tuple[ProjectRow, list[FrameRow], list[FrameAuditRow]]:
    bad = _dog_and_rope(screenplay, extraction)
    good = _checks(screenplay, extraction)
    audits = [
        _audit(1, 1, "fail", bad, minutes=1),
        _audit(1, 2, "fail", bad, minutes=2),
        _audit(1, 3, "fail", bad, minutes=3),
        _audit(2, 1, "error", [], minutes=4),
        _audit(2, 2, "pass", good, minutes=5),
        _audit(3, 1, "warn", good, minutes=6),
        _audit(1, 1, "pass", good, target=AuditTarget.COMIC, minutes=9),
    ]
    frames = [
        _frame(1, "withheld", 3),
        _frame(2, "passed", 2),
        _frame(3, "warned", 1),
        _frame(4, "failed", 1),  # the renderer failed: no audit
    ]  # shot 5 has no frames row
    return _project(screenplay, extraction, _five_shots()), frames, audits


def test_counts_states_and_checks(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
    )
    c = report.counts
    assert (c.shots, c.passed, c.warned, c.withheld, c.failed, c.not_drawn) == (5, 1, 1, 1, 1, 1)
    assert c.shots == c.passed + c.warned + c.withheld + c.failed + c.not_drawn
    assert c.drawings == 6  # the comic audit is another target; the error audit is a drawing
    assert c.first_attempt_accepted == 1
    assert (c.prompt_tokens, c.completion_tokens) == (600, 60)
    assert (report.started, report.finished) == (
        T0 + timedelta(minutes=1),
        T0 + timedelta(minutes=6),
    )

    lines = {s.shot: s for s in report.shots}
    first = lines[f"{screenplay.scenes[0].number}.1"]
    assert (first.state, first.attempts, first.failed) == ("withheld", 3, ("unscripted_object",))
    assert [v.value for v in first.verdicts] == ["fail", "fail", "fail"]
    second = lines[f"{screenplay.scenes[0].number}.2"]
    assert [v.value for v in second.verdicts] == ["error", "pass"]
    fourth = lines[f"{screenplay.scenes[0].number}.4"]
    assert (fourth.state, fourth.attempts, fourth.verdicts, fourth.failed) == ("failed", 0, (), ())
    assert lines[f"{screenplay.scenes[0].number}.5"].state == NOT_DRAWN

    objects = {k.check.value: k for k in report.checks}["unscripted_object"]
    assert (objects.attempts, objects.final) == (3, 1)  # the error audit is in no check


def test_a_comic_takes_states_from_its_last_audit(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.COMIC, styles=styles, max_words=55
    )
    assert [s.state for s in report.shots] == ["passed", NOT_DRAWN, NOT_DRAWN, NOT_DRAWN, NOT_DRAWN]
    assert report.counts.drawings == 1


def test_a_prompt_that_cannot_be_built_shows_its_error(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=1
    )
    shot = report.shots[0]
    assert shot.prompt is None
    assert shot.prompt_error is not None and shot.prompt_error.startswith("PromptError: ")


def test_characters_say_what_the_prompt_gets(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
    )
    nandi = {c.name: c for c in report.characters}["NANDI"]
    assert nandi.age is not None and "60s" in nandi.age
    assert nandi.sex is None
    assert nandi.look == "oilskin coat"


def test_the_markdown_in_order(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    frames[2] = _frame(3, "rendering", 2)  # an unfinished run says so
    text = to_markdown(
        build_report(
            project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
        )
    )
    headings = [line for line in text.splitlines() if line.startswith("#")]
    assert headings == [
        "# Run report: the lighthouse",
        "## Result",
        "## Checks",
        "## Causes",
        "## Characters",
        "## Shots",
    ]
    assert "prompts rebuilt with the code that wrote this report" in text
    assert "The run had not finished: 1 shots still in progress." in text
    unfinished = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
    )
    assert unfinished.counts.not_drawn == 2  # shot 5 (no row) and shot 3 (rendering)
    assert [s.state for s in unfinished.shots][2] == "rendering"
    assert "none from the script" in text
    assert "1 of 5 accepted" in text


def test_the_last_audit_is_the_highest_attempt_whatever_the_row_order(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    bad = _dog_and_rope(screenplay, extraction)
    good = _checks(screenplay, extraction)
    audits = [_audit(1, 2, "pass", good, minutes=2), _audit(1, 1, "fail", bad, minutes=1)]
    project = _project(screenplay, extraction, _five_shots()[:1])
    report = build_report(
        project,
        [_frame(1, "passed", 2)],
        audits,
        target=AuditTarget.STORYBOARD,
        styles=styles,
        max_words=55,
    )
    shot = report.shots[0]
    assert [v.value for v in shot.verdicts] == ["fail", "pass"]
    assert shot.failed == ()
    objects = {k.check.value: k for k in report.checks}["unscripted_object"]
    assert (objects.attempts, objects.final) == (1, 0)
    assert report.counts.first_attempt_accepted == 0


def test_a_comic_state_is_its_last_audit_verdict(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    bad = _dog_and_rope(screenplay, extraction)
    good = _checks(screenplay, extraction)
    comic = AuditTarget.COMIC
    audits = [
        _audit(1, 2, "warn", good, target=comic),
        _audit(1, 1, "fail", bad, target=comic),
        _audit(2, 1, "error", [], target=comic),
        _audit(3, 1, "fail", bad, target=comic),
    ]
    project = _project(screenplay, extraction, _five_shots())
    report = build_report(project, [], audits, target=comic, styles=styles, max_words=55)
    assert [s.state for s in report.shots] == [
        "warned",
        "withheld",
        "withheld",
        NOT_DRAWN,
        NOT_DRAWN,
    ]


def test_hard_checks_come_before_soft_in_check_order(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
    )
    severities = [k.severity for k in report.checks]
    assert Severity.HARD in severities and Severity.SOFT in severities
    hard = severities.count(Severity.HARD)
    assert all(s is Severity.HARD for s in severities[:hard])
    order = [k.check for k in report.checks]
    assert order[:hard] == sorted(order[:hard], key=list(type(order[0])).index)
    assert order[hard:] == sorted(order[hard:], key=list(type(order[0])).index)


def _unescaped_pipes(line: str) -> int:
    return len(re.findall(r"(?<!\\)\|", line))


def test_model_text_never_breaks_a_table(
    screenplay: Screenplay, extraction: Extraction, styles: StyleRegistry
) -> None:
    project, frames, audits = _run(screenplay, extraction)
    report = build_report(
        project, frames, audits, target=AuditTarget.STORYBOARD, styles=styles, max_words=55
    )
    odd = dataclasses.replace(report.objects[0], key="A|B", examples=("line one\nline two",))
    shots = (dataclasses.replace(report.shots[0], prompt="a | b\nc"), *report.shots[1:])
    text = to_markdown(dataclasses.replace(report, objects=(odd,), shots=shots))
    assert "A\\|B" in text
    table: list[str] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            table.append(line)
            continue
        if table:
            assert {_unescaped_pipes(row) for row in table} == {_unescaped_pipes(table[0])}
            table = []
