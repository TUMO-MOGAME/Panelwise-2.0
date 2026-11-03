"""The run report: what one live run stored, as markdown (docs/design/learning.md, T081).

    python -m app.verify.report <project-id> [--target storyboard|comic]

It reads the project, its frames and its `frame_audits` rows, and nothing else: no model call,
no Storage, no write. So it costs nothing, and a run is reported as the run itself decided.
"""

import argparse
import ast
import asyncio
import re
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.characters.labels import animals
from app.core.config import Settings
from app.db import make_engine, make_sessions
from app.frames.model import AuditTarget, FrameAuditRow, FrameRow
from app.grounding import EntityKind
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storyboard.prompt import (
    build_frame_prompt,
    character_sex,
    introduced_age,
    introduced_look,
)
from app.storyboard.styles import PUBLIC_STYLES, StyleRegistry, load_styles
from app.verify.model import Check, Severity, Verdict

NOT_DRAWN = "not drawn"
_IN_PROGRESS = frozenset({"rendering", "auditing"})
_COMIC_STATE = {
    Verdict.PASS: "passed",
    Verdict.WARN: "warned",
    Verdict.FAIL: "withheld",
    Verdict.ERROR: "withheld",
}

# run_checks' detail shapes (verify/audit.py), joined by "; " (§3 Causes).
_SPLIT = re.compile(r"; (?=object |person |text )")
_OBJECT = re.compile(r"^object (\d+) \((.*), ([^,]*)\): (.*)$")
_PERSON = re.compile(r"^person (\d+) \(([^,]*), (.*)\): (.*)$")
_TEXT = re.compile(r"^text (.*) isn't the script's$")
_PERSON_CUTS = (
    ",",
    " in ",
    " with ",
    " wearing ",
    " standing ",
    " sitting ",
    " holding ",
    " seen ",
    " looking ",
    " smiling ",
)
_OTHER = "other"
_TOP = 15
_EXAMPLES = 5


@dataclass(frozen=True)
class Counts:
    shots: int
    passed: int
    warned: int
    withheld: int
    failed: int
    not_drawn: int
    drawings: int
    first_attempt_accepted: int
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class CheckCount:
    check: Check
    severity: Severity
    attempts: int  # audits with this check not ok
    final: int  # shots whose last audit has it not ok


@dataclass(frozen=True)
class Cause:
    key: str
    count: int
    examples: tuple[str, ...]


@dataclass(frozen=True)
class CharacterLine:
    name: str
    age: str | None
    sex: str | None
    look: str | None


@dataclass(frozen=True)
class ShotLine:
    shot: str
    state: str
    attempts: int
    verdicts: tuple[Verdict, ...]
    failed: tuple[str, ...]  # the hard checks its last audit failed
    prompt: str | None
    prompt_error: str | None
    source: str


@dataclass(frozen=True)
class RunReport:
    title: str
    project_id: uuid.UUID
    target: AuditTarget
    started: datetime | None
    finished: datetime | None
    counts: Counts
    checks: tuple[CheckCount, ...]
    objects: tuple[Cause, ...]
    people: tuple[Cause, ...]
    texts: tuple[Cause, ...]
    characters: tuple[CharacterLine, ...]
    shots: tuple[ShotLine, ...]


def _pieces(audits: Sequence[FrameAuditRow], check: Check) -> Iterator[tuple[FrameAuditRow, str]]:
    """Each failure in the not-ok `check` entries' details, split as §3 says."""
    for row in audits:
        for entry in row.checks:
            if entry.get("check") == check.value and entry.get("ok") is False:
                for piece in _SPLIT.split(entry.get("detail") or ""):
                    if piece:
                        yield row, piece


def _tally(pairs: Sequence[tuple[str, str]]) -> list[Cause]:
    """(key, example) pairs → causes by count then key; examples most frequent first, each once."""
    counts: Counter[str] = Counter(key for key, _ in pairs)
    examples: dict[str, Counter[str]] = defaultdict(Counter)
    for key, example in pairs:
        examples[key][example] += 1
    causes = [
        Cause(
            key,
            n,
            tuple(
                e
                for e, _ in sorted(examples[key].items(), key=lambda kv: (-kv[1], kv[0]))[
                    :_EXAMPLES
                ]
            ),
        )
        for key, n in counts.items()
    ]
    return sorted(causes, key=lambda c: (-c.count, c.key))


def object_causes(audits: Sequence[FrameAuditRow]) -> list[Cause]:
    """`unscripted_object` (hard; since T089 only an animal or a weapon) and `background_object`
    (soft, T083; since T089 every other object) failures."""
    pairs: list[tuple[str, str]] = []
    pieces = [*_pieces(audits, Check.UNSCRIPTED_OBJECT), *_pieces(audits, Check.BACKGROUND_OBJECT)]
    for _, piece in pieces:
        if m := _OBJECT.match(piece):
            pairs.append((f"{m.group(3)} · {m.group(4)}", m.group(2)))
        else:
            pairs.append((_OTHER, piece))
    return _tally(pairs)


def _person_key(appearance: str) -> str:
    text = appearance.lower().lstrip()
    cuts = [i for i in (text.find(word, 1) for word in _PERSON_CUTS) if i > 0]
    key = text[: min(cuts, default=len(text))].rstrip()
    return key if any(ch.isalpha() for ch in key) else _OTHER


def person_causes(audits: Sequence[FrameAuditRow]) -> list[Cause]:
    pairs: list[tuple[str, str]] = []
    for _, piece in _pieces(audits, Check.UNSCRIPTED_PERSON):
        if m := _PERSON.match(piece):
            pairs.append((_person_key(m.group(3)), m.group(4)))
        else:
            pairs.append((_OTHER, piece))
    return _tally(pairs)


def _read_back(quoted: str) -> str:
    try:
        value = ast.literal_eval(quoted)
    except ValueError, SyntaxError:
        return quoted
    return value if isinstance(value, str) else quoted


def text_causes(
    audits: Sequence[FrameAuditRow], *, label: Callable[[int, int], str]
) -> list[Cause]:
    """Examples are the shots the text appeared in, in plan order, each once."""
    counts: Counter[str] = Counter()
    shots: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for row, piece in _pieces(audits, Check.TEXT_IN_FRAME):
        key = _read_back(m.group(1)) if (m := _TEXT.match(piece)) else _OTHER
        counts[key] += 1
        shots[key].add((row.scene_index, row.shot_number))
    causes = [
        Cause(key, n, tuple(label(*s) for s in sorted(shots[key])[:_EXAMPLES]))
        for key, n in counts.items()
    ]
    return sorted(causes, key=lambda c: (-c.count, c.key))


def build_report(
    project: ProjectRow,
    frames: Sequence[FrameRow],
    audits: Sequence[FrameAuditRow],
    *,
    target: AuditTarget,
    styles: StyleRegistry,
    max_words: int,
) -> RunReport:
    screenplay = load_screenplay(project.screenplay)  # type: ignore[arg-type]
    extraction = load_extraction(project.extraction)
    plan = load_plan(project.plan)
    scenes = screenplay.scenes

    def label(scene_index: int, number: int) -> str:
        return f"{scenes[scene_index].number}.{number}"

    mine = [a for a in audits if a.project_id == project.id and a.target == target.value]
    by_shot: dict[tuple[int, int], list[FrameAuditRow]] = defaultdict(list)
    for row in sorted(mine, key=lambda r: r.attempt):
        by_shot[(row.scene_index, row.shot_number)].append(row)
    stored = (
        {(f.scene_index, f.shot_number): f.state for f in frames if f.project_id == project.id}
        if target is AuditTarget.STORYBOARD
        else {}
    )
    style = styles.get(None)

    lines: list[ShotLine] = []
    last_audits: list[FrameAuditRow] = []
    for shot in sorted(plan.shots, key=lambda s: (s.scene_index, s.number)):
        rows = by_shot.get((shot.scene_index, shot.number), [])
        last = rows[-1] if rows else None
        if last is not None:
            last_audits.append(last)
        if target is AuditTarget.STORYBOARD:
            state = stored.get((shot.scene_index, shot.number), NOT_DRAWN)
        else:
            state = _COMIC_STATE[Verdict(last.verdict)] if last is not None else NOT_DRAWN
        failed = (
            tuple(
                e["check"]
                for e in last.checks
                if e.get("ok") is False and e.get("severity") == Severity.HARD.value
            )
            if last is not None
            else ()
        )
        try:
            prompt: str | None = build_frame_prompt(
                shot, screenplay, extraction, style, max_words=max_words
            ).text()
            error = None
        except Exception as exc:  # the report shows any failure instead of stopping
            prompt, error = None, f"{type(exc).__name__}: {exc}"
        lines.append(
            ShotLine(
                shot=label(shot.scene_index, shot.number),
                state=state,
                attempts=len(rows),
                verdicts=tuple(Verdict(r.verdict) for r in rows),
                failed=failed,
                prompt=prompt,
                prompt_error=error,
                source=shot.source,
            )
        )

    states = Counter(line.state for line in lines)
    counts = Counts(
        shots=len(lines),
        passed=states["passed"],
        warned=states["warned"],
        withheld=states["withheld"],
        failed=states["failed"],
        not_drawn=states[NOT_DRAWN] + sum(states[s] for s in _IN_PROGRESS),
        drawings=len(mine),
        first_attempt_accepted=sum(
            1
            for rows in by_shot.values()
            if any(r.attempt == 1 and r.verdict in (Verdict.PASS, Verdict.WARN) for r in rows)
        ),
        prompt_tokens=sum(r.prompt_tokens for r in mine),
        completion_tokens=sum(r.completion_tokens for r in mine),
    )

    severities: dict[str, str] = {}
    attempts: Counter[str] = Counter()
    for row in mine:
        for entry in row.checks:
            severities.setdefault(entry["check"], entry["severity"])
            if entry.get("ok") is False:
                attempts[entry["check"]] += 1
    final: Counter[str] = Counter(
        e["check"] for r in last_audits for e in r.checks if e.get("ok") is False
    )
    order = list(Check)
    checks = sorted(
        (
            CheckCount(Check(name), Severity(sev), attempts[name], final[name])
            for name, sev in severities.items()
        ),
        key=lambda c: (c.severity is not Severity.HARD, order.index(c.check)),
    )

    beings = animals(extraction)  # an animal is never a person: a pet PRINCESS gets no sex
    characters = tuple(
        CharacterLine(
            name=e.name,
            age=age[0] if (age := introduced_age(e.name, screenplay, extraction)) else None,
            sex=None
            if e.name in beings
            else found[0].value
            if (found := character_sex(e.name, screenplay, extraction))
            else None,
            look=look[0] if (look := introduced_look(e.name, screenplay)) else None,
        )
        for e in extraction.entities
        if e.kind is EntityKind.CHARACTER
    )
    times = sorted(r.created_at for r in mine)
    return RunReport(
        title=project.title,
        project_id=project.id,
        target=target,
        started=times[0] if times else None,
        finished=times[-1] if times else None,
        counts=counts,
        checks=tuple(checks),
        objects=tuple(object_causes(mine)),
        people=tuple(person_causes(mine)),
        texts=tuple(text_causes(mine, label=label)),
        characters=characters,
        shots=tuple(lines),
    )


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.split()).replace("|", "\\|")


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return out


def _when(at: datetime | None) -> str:
    return at.strftime("%Y-%m-%d %H:%M UTC") if at is not None else "no audits"


def to_markdown(report: RunReport) -> str:
    c = report.counts
    lines = [
        f"# Run report: {report.title}",
        "",
        f"Project `{report.project_id}` · target {report.target.value} · "
        f"{_when(report.started)} to {_when(report.finished)} · "
        "prompts rebuilt with the code that wrote this report",
    ]
    in_progress = sum(1 for s in report.shots if s.state in _IN_PROGRESS)
    if in_progress:
        lines += ["", f"The run had not finished: {in_progress} shots still in progress."]
    lines += ["", "## Result", ""]
    lines += _table(
        [
            "shots",
            "passed",
            "warned",
            "withheld",
            "failed",
            "not drawn",
            "drawings",
            "accepted at attempt 1",
            "prompt tokens",
            "completion tokens",
        ],
        [
            [
                c.shots,
                c.passed,
                c.warned,
                c.withheld,
                c.failed,
                c.not_drawn,
                c.drawings,
                c.first_attempt_accepted,
                c.prompt_tokens,
                c.completion_tokens,
            ]
        ],
    )
    lines += ["", f"{c.passed + c.warned} of {c.shots} accepted", "", "## Checks", ""]
    lines += _table(
        ["check", "severity", "attempts", "final"],
        [[k.check.value, k.severity.value, k.attempts, k.final] for k in report.checks],
    )
    lines += ["", "## Causes", ""]
    for name, causes in (
        ("Objects", report.objects),
        ("People", report.people),
        ("Text", report.texts),
    ):
        lines += [f"**{name}**", ""]
        if causes:
            lines += _table(
                ["count", "key", "examples"],
                [[x.count, x.key, ", ".join(x.examples)] for x in causes[:_TOP]],
            )
        else:
            lines += ["None."]
        lines += [""]
    none = "none from the script"
    lines += ["## Characters", ""]
    lines += _table(
        ["character", "age", "sex", "look"],
        [[x.name, x.age or none, x.sex or none, x.look or none] for x in report.characters],
    )
    lines += ["", "## Shots", ""]
    lines += _table(
        ["shot", "state", "attempts", "verdicts", "final failed checks", "prompt"],
        [
            [
                s.shot,
                s.state,
                s.attempts,
                ", ".join(v.value for v in s.verdicts),
                ", ".join(s.failed),
                s.prompt if s.prompt is not None else f"(not built: {s.prompt_error})",
            ]
            for s in report.shots
        ],
    )
    lines += [""]
    lines += [f"- **{s.shot}:** {_cell(s.source)}" for s in report.shots]
    return "\n".join(lines) + "\n"


async def _main(project_id: uuid.UUID, target: AuditTarget) -> int:
    settings = Settings()
    engine = make_engine(settings)
    sessions = make_sessions(engine)
    try:
        async with sessions() as session:
            project = await session.get(ProjectRow, project_id)
            frames = list(
                await session.scalars(select(FrameRow).where(FrameRow.project_id == project_id))
            )
            audits = list(
                await session.scalars(
                    select(FrameAuditRow).where(
                        FrameAuditRow.project_id == project_id,
                        FrameAuditRow.target == target.value,
                    )
                )
            )
    except (SQLAlchemyError, OSError) as exc:
        print(f"the database answered {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    if project is None:
        print("no such project", file=sys.stderr)
        return 2
    if project.plan is None or project.screenplay is None or project.extraction is None:
        print("no shot plan yet", file=sys.stderr)
        return 2
    private = settings.panelwise_private_styles
    styles = load_styles(PUBLIC_STYLES, Path(private) if private else None)
    report = build_report(
        project,
        frames,
        audits,
        target=target,
        styles=styles,
        max_words=settings.comfyui_max_words,
    )
    sys.stdout.write(to_markdown(report))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.verify.report",
        description="A live run's report from its stored audits; writes nothing, costs nothing.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    parser.add_argument(
        "--target", choices=[t.value for t in AuditTarget], default=AuditTarget.STORYBOARD.value
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.project_id, AuditTarget(args.target))))


if __name__ == "__main__":
    main()
