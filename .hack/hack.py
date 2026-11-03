#!/usr/bin/env python3
"""hack: this event's clock and checks.

Reads event.toml (the facts of the event, copied from the organisers) and .hack/format.toml (the
format's phase table, copied in by the Hackathon kit). Standard library only; Python 3.11+ for
tomllib. The ./hack wrapper fetches a suitable Python with uv when the system one is older.

    ./hack status                 phase, time left, next checkpoint, what's still unknown
    ./hack schedule               every phase with its real start and end
    ./hack preflight              the audit before submitting (runs scripts/gate.sh)
    ./hack get <key>              print a value from event.toml, e.g. checks.smoke

Adapted for Panelwise from the Hackathon kit's MARATHON format. Left out: `kickoff` (the event had
started, so the times and baseline were written into event.toml by hand, with their source, and a
change to it goes through a PR like any other) and `freeze-check` (the kit's pre-push hook called
it; Panelwise keeps its own .githooks/pre-push, which never pushes to main). The freeze audit in
`preflight` counts non-merge commits, because main only moves by merged PRs here.

HACK_NOW=2026-10-03T14:00:00+02:00 overrides the clock, for tests and rehearsals.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import tomllib
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
EVENT_FILE = ROOT / "event.toml"
FORMAT_FILE = ROOT / ".hack" / "format.toml"

FATAL_PREFIX = "FATAL-FIX:"
COMMON_HEADINGS = ["Problem", "Solution", "How to run it", "Baseline and dependencies", "Team"]
JUDGED_HEADINGS = ["Demo", "Architecture", "Sponsor Technologies Deployed",
                   "What's real and what's mocked"]
DEFENSE_QUESTIONS = 5
MIN_REHEARSALS = 5


def _style(code: str):
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return lambda s: f"\033[{code}m{s}\033[0m"
    return lambda s: s


red, green, yellow, bold = _style("0;31"), _style("0;32"), _style("1;33"), _style("1")


class HackError(Exception):
    """A problem the user has to fix. Printed without a traceback."""


# ------------------------------------------------------------------ loading ---
def load_event() -> dict:
    if not EVENT_FILE.exists():
        raise HackError(f"no event.toml at {ROOT}")
    try:
        return tomllib.loads(EVENT_FILE.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise HackError(f"event.toml is not valid TOML: {e}") from e


def load_format() -> dict:
    if not FORMAT_FILE.exists():
        raise HackError(f"no .hack/format.toml at {ROOT} (this repo wasn't made by the kit?)")
    return tomllib.loads(FORMAT_FILE.read_text(encoding="utf-8"))


def layers(fmt: dict) -> list[str]:
    return list(fmt.get("format", {}).get("layers", []))


def parse_time(value: str, what: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value)
    except ValueError as e:
        raise HackError(f"{what} is not an ISO 8601 time: {value!r}") from e
    if t.tzinfo is None:
        raise HackError(f"{what} has no UTC offset: {value!r} "
                        "(write it like 2026-10-03T18:00:00+02:00)")
    return t


def now() -> dt.datetime:
    fake = os.environ.get("HACK_NOW")
    if fake:
        return parse_time(fake, "HACK_NOW")  # type: ignore[return-value]
    return dt.datetime.now(dt.UTC)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise HackError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


# -------------------------------------------------------------------- clock ---
class Phase(NamedTuple):
    name: str
    start: dt.datetime
    end: dt.datetime
    exit: str
    freeze: bool
    milestone: bool


def check_table(table: list[dict], reference: float, tail: float | None) -> None:
    """The phase table must still be valid after someone edits it to match an agenda."""
    problems = []
    if any(not {"name", "from", "to"} <= p.keys() for p in table):
        problems.append("every [[phase]] needs name, from and to")
    else:
        if float(table[0]["from"]) != 0:
            problems.append("the first phase must start at 0")
        for a, b in pairwise(table):
            if float(a["to"]) != float(b["from"]):
                problems.append(f"{a['name']!r} ends at {a['to']} but {b['name']!r} starts at "
                                f"{b['from']}: phases must follow on without gaps")
        problems += [f"{p['name']!r} ends before it starts" for p in table
                     if not float(p["from"]) < float(p["to"])]
        if float(table[-1]["to"]) != reference:
            problems.append(f"the last phase must end at reference_hours ({reference:g})")
        freezes = [p for p in table if p.get("freeze")]
        if len(freezes) != 1:
            problems.append(f"exactly one phase needs freeze = true (found {len(freezes)})")
        elif tail and not 0 < float(freezes[0]["from"]) < reference:
            problems.append("with freeze_before_deadline, the freeze can't be the first phase")
    if problems:
        raise HackError(".hack/format.toml's phase table is invalid: " + "; ".join(problems))


class Clock:
    """The format's phase table, scaled from its reference length onto the real event.

    Phases scale proportionally. With [clock] freeze_before_deadline, the freeze starts that many
    real hours before the deadline instead: the table up to the freeze scales into start → freeze,
    and the rest into freeze → deadline (DESIGN.md §4.3).
    """

    def __init__(self, fmt: dict, event: dict):
        clock = fmt.get("clock") or {}
        if "reference_hours" not in clock or not fmt.get("phase"):
            raise HackError(".hack/format.toml has no [clock] and [[phase]] table")
        self.reference = float(clock["reference_hours"])
        self.skeleton_ref = clock.get("skeleton_by")
        self.tail = clock.get("freeze_before_deadline")
        self.table = fmt["phase"]
        check_table(self.table, self.reference, self.tail)
        self.freeze_ref = float(next(p["from"] for p in self.table if p.get("freeze")))
        t = event.get("time", {})
        self.start = parse_time(t.get("start", ""), "[time] start")
        self.deadline = parse_time(t.get("deadline", ""), "[time] deadline")
        self.freeze_override = parse_time(t.get("freeze", ""), "[time] freeze")
        if self.start and self.deadline:
            if self.deadline <= self.start:
                raise HackError("[time] deadline must be after [time] start")
            if self.tail and self.deadline - self.start <= dt.timedelta(hours=float(self.tail)):
                raise HackError(f"the event is shorter than the format's {float(self.tail):g}-hour "
                                "freeze ([clock] freeze_before_deadline in .hack/format.toml): "
                                "lower it, or set [time] freeze")

    @property
    def known(self) -> bool:
        return self.start is not None and self.deadline is not None

    def at(self, ref_hours: float) -> dt.datetime:
        assert self.start and self.deadline
        ref = float(ref_hours)
        if not self.tail:
            return self.start + (self.deadline - self.start) * (ref / self.reference)
        anchor = self.deadline - dt.timedelta(hours=float(self.tail))
        if ref <= self.freeze_ref:
            return self.start + (anchor - self.start) * (ref / self.freeze_ref)
        span = self.reference - self.freeze_ref
        return anchor + (self.deadline - anchor) * ((ref - self.freeze_ref) / span)

    def phases(self) -> list[Phase]:
        rows = [Phase(p["name"], self.at(p["from"]), self.at(p["to"]), p.get("exit", ""),
                      bool(p.get("freeze")), bool(p.get("milestone"))) for p in self.table]
        if self.freeze_override:
            i = next(i for i, p in enumerate(rows) if p.freeze)
            lower = rows[i - 1].start if i > 0 else self.start
            if not (lower < self.freeze_override < rows[i].end):  # type: ignore[operator]
                raise HackError(f"[time] freeze must fall after {lower.isoformat()} (when the "
                                f"phase before it starts) and before {rows[i].end.isoformat()} "
                                "(when the freeze phase ends)")
            rows[i] = rows[i]._replace(start=self.freeze_override)
            if i > 0:
                rows[i - 1] = rows[i - 1]._replace(end=self.freeze_override)
        return rows

    def freeze(self) -> dt.datetime:
        return next(p.start for p in self.phases() if p.freeze)

    def skeleton(self) -> dt.datetime | None:
        return None if self.skeleton_ref is None else self.at(self.skeleton_ref)


def human(delta: dt.timedelta) -> str:
    secs = abs(int(delta.total_seconds()))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def when(t: dt.datetime, tz: dt.tzinfo | None) -> str:
    return t.astimezone(tz).strftime("%a %d %b %H:%M")


# ------------------------------------------------------------------- status ---
def unknown_facts(event: dict, fmt: dict) -> list[str]:
    missing = []
    if not event.get("time", {}).get("source"):
        missing.append("where the times came from ([time] source)")
    if not event.get("checks", {}).get("smoke"):
        missing.append("the walking-skeleton command ([checks] smoke)")
    if "judged" in layers(fmt):
        if not event.get("rubric", {}).get("source"):
            missing.append("the rubric's source ([rubric] source)")
        if not event.get("team", {}).get("presenter"):
            missing.append("the presenter ([team] presenter)")
        if not event.get("scope", {}).get("core"):
            missing.append("the core paths that are never mocked ([scope] core)")
    return missing


def cmd_status(_args: argparse.Namespace) -> int:
    event, fmt = load_event(), load_format()
    info = fmt.get("format", {})
    clock = Clock(fmt, event)
    t = now()
    print(bold(f"== {event.get('name') or '(unnamed event)'} · {info.get('label', '?')} =="))
    source = event.get("time", {}).get("source") or red("unknown")
    print(f"Medium:    {event.get('medium', '?')}   ·   times from: {source}")
    if not clock.known:
        print(red("Deadline:  UNKNOWN. Copy the times into event.toml [time] from the organisers' "
                  "page, with their source; never assume them."))
    else:
        start, deadline = clock.start, clock.deadline
        assert start and deadline
        tz = start.tzinfo
        phases = clock.phases()
        print(f"Now:       {when(t, tz)}")
        if t < start:
            print(f"Phase:     pre-event: kickoff in {human(start - t)} (see PREP.md)")
        elif t >= deadline:
            print(red(f"Phase:     after the deadline ({human(t - deadline)} ago)"))
        else:
            i, p = next((i, p) for i, p in enumerate(phases) if p.start <= t < p.end)
            print(f"Phase:     {p.name} ({i + 1}/{len(phases)}), until {when(p.end, tz)} "
                  f"({human(p.end - t)} left)")
            if p.exit:
                print(f"           done when: {p.exit}")
            if i + 1 < len(phases):
                print(f"Next:      {phases[i + 1].name} at {when(phases[i + 1].start, tz)}")
        skeleton = clock.skeleton()
        if skeleton:
            if t >= skeleton:
                line = f"Skeleton:  was due {when(skeleton, tz)}. Is [checks] smoke green? " \
                       "If not, cut scope now."
                print(yellow(line) if t < deadline else line)
            else:
                print(f"Skeleton:  due {when(skeleton, tz)} (in {human(skeleton - t)})")
        fz = clock.freeze()
        if t >= fz:
            print(red(f"Freeze:    since {when(fz, tz)}: main takes {FATAL_PREFIX} PRs only"))
        else:
            print(f"Freeze:    {when(fz, tz)} (in {human(fz - t)})")
        if t < deadline:
            print(f"Deadline:  {when(deadline, tz)} (in {human(deadline - t)})")
    missing = unknown_facts(event, fmt)
    if missing:
        print(yellow("Unknown:   " + "; ".join(missing)))
    return 0


def cmd_schedule(_args: argparse.Namespace) -> int:
    event, fmt = load_event(), load_format()
    clock = Clock(fmt, event)
    print(bold(f"== schedule: {event.get('name') or '(unnamed event)'} · "
               f"{fmt.get('format', {}).get('label', '?')} =="))
    if not clock.known:
        print(yellow("The start and deadline are unknown (event.toml [time]), so these are the "
                     f"table's reference hours ({clock.reference:g}h):"))
        for i, p in enumerate(clock.table, 1):
            mark = "  (freeze)" if p.get("freeze") else ""
            print(f"  {i}. {float(p['from']):>6g}h → {float(p['to']):>6g}h   {p['name']}{mark}")
        return 0
    start, deadline = clock.start, clock.deadline
    assert start and deadline
    tz = start.tzinfo
    print(f"Times from: {event.get('time', {}).get('source') or red('unknown')}")
    for i, p in enumerate(clock.phases(), 1):
        mark = "  (freeze)" if p.freeze else ""
        print(f"  {i}. {when(p.start, tz)} → {when(p.end, tz)}   {p.name}{mark}")
    skeleton = clock.skeleton()
    if skeleton:
        print(f"Skeleton:   {when(skeleton, tz)}")
    fz = clock.freeze()
    print(f"Freeze:     {when(fz, tz)} ({human(deadline - fz)} before the deadline)")
    print(f"Deadline:   {when(deadline, tz)}")
    print("These are working numbers. If the agenda differs, edit .hack/format.toml (the phase "
          "table) or event.toml [time] freeze, then run ./hack schedule again.")
    return 0


# ---------------------------------------------------------------- preflight ---
def strip_comments(s: str) -> str:
    return re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL).strip()


def filled(section: str) -> bool:
    """True when a section has real content: not just comments, or a table with no rows."""
    lines = [ln.strip() for ln in strip_comments(section).splitlines() if ln.strip()]
    lines = [ln for ln in lines if not re.fullmatch(r"\|?[\s:|-]+\|?", ln)]  # table separators
    table = [ln for ln in lines if ln.startswith("|")]
    return len(lines) > len(table) or len(table) > 1


def md_sections(text: str) -> dict[str, str]:
    """## Heading -> the text under it, up to the next ## heading."""
    parts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def md_field(text: str, label: str) -> list[str]:
    """Every answer after  **label:**  up to the next heading or the next **field:**."""
    pattern = rf"\*\*{re.escape(label)}:\*\*(.*?)(?=^#|^\*\*[^*\n]+:\*\*|\Z)"
    return [strip_comments(m) for m in re.findall(pattern, text, flags=re.DOTALL | re.MULTILINE)]


def table_rows(text: str, heading: str) -> list[list[str]]:
    body = md_sections(text).get(heading, "")
    rows = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and not set("".join(cells)) <= set("-: "):
            rows.append(cells)
    return rows[1:]  # drop the header row


class Row(NamedTuple):
    result: str  # PASS | FAIL | CONFIRM
    text: str


def read(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def check_common(event: dict, fmt: dict, clock: Clock | None, t: dt.datetime) -> list[Row]:
    rows: list[Row] = []
    tm = event.get("time", {})
    missing = [k for k in ("start", "deadline", "source") if not tm.get(k)]
    rows.append(Row("FAIL", f"times not set: {', '.join(missing)} (event.toml [time])") if missing
                else Row("PASS", "start, deadline and their source are set"))

    baseline = event.get("provenance", {}).get("baseline", "")
    if not baseline:
        rows.append(Row("FAIL", "no baseline commit recorded (event.toml [provenance])"))
    elif subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"],
                        cwd=ROOT, check=False, capture_output=True).returncode != 0:
        rows.append(Row("FAIL", f"baseline {baseline[:7]} is not an ancestor of HEAD"))
    else:
        rows.append(Row("PASS", f"baseline {baseline[:7]} recorded; everything after it is "
                                "built during the event"))

    readme = read("README.md")
    headings = COMMON_HEADINGS + (JUDGED_HEADINGS if "judged" in layers(fmt) else [])
    sections = md_sections(readme)
    empty = [h for h in headings if not filled(sections.get(h, ""))]
    title = re.search(r"^# +(.+)$", readme, flags=re.MULTILINE)
    if not title or "<" in title.group(1):
        empty.insert(0, "the project name (the # title)")
    rows.append(Row("FAIL", "README sections empty or missing: " + "; ".join(empty)) if empty
                else Row("PASS", "README has every required section"))

    tracked = git("ls-files").splitlines()
    envs = [f for f in tracked if re.search(r"(^|/)\.env($|\.)", f)
            and not re.search(r"\.(example|sample|template)$", f)]
    rows.append(Row("FAIL", f"env files committed: {', '.join(envs)}") if envs
                else Row("PASS", "no .env file committed"))

    smoke = event.get("checks", {}).get("smoke", "")
    skeleton = clock.skeleton() if clock and clock.known else None
    if smoke:
        rows.append(Row("PASS", f"walking-skeleton smoke test declared: {smoke}"))
    elif skeleton and t < skeleton:
        rows.append(Row("PASS", f"smoke test not due until {when(skeleton, skeleton.tzinfo)}"))
    else:
        rows.append(Row("FAIL", "no [checks] smoke: the walking skeleton is due, so declare the "
                                "command that sends one input end to end (the gate runs it)"))

    if clock and clock.known:
        fz = clock.freeze()
        if t >= fz:
            branch = "main" if git("rev-parse", "--verify", "main", check=False).strip() else "HEAD"
            log = git("log", branch, "--no-merges", f"--since={fz.isoformat()}",
                      "--format=%h%x09%s")
            bad = [c for c in log.splitlines() if not c.split("\t", 1)[-1].startswith(FATAL_PREFIX)]
            rows.append(Row("FAIL", f"commits on {branch} after the freeze without "
                                    f"{FATAL_PREFIX}: {', '.join(c.split(chr(9))[0] for c in bad)}")
                        if bad else Row("PASS", f"nothing but {FATAL_PREFIX} commits since the "
                                                "freeze"))
        else:
            rows.append(Row("PASS", "freeze not reached yet"))

    gate = subprocess.run(["bash", "scripts/gate.sh"], cwd=ROOT, check=False, capture_output=True,
                          text=True)
    last = (gate.stdout.strip().splitlines() or ["(no output)"])[-1]
    rows.append(Row("PASS" if gate.returncode == 0 else "FAIL", f"gate: {last}"))
    rows.append(Row("CONFIRM", "the app runs from a fresh clone with the README's commands"))
    return rows


def check_judged(event: dict, fmt: dict) -> list[Row]:
    rows: list[Row] = []
    rubric = event.get("rubric", {})
    weights = {k: v for k, v in rubric.items() if isinstance(v, int)}
    if sum(weights.values()) != 100:
        rows.append(Row("FAIL", f"rubric weights add up to {sum(weights.values())}, not 100"))
    elif not rubric.get("source"):
        rows.append(Row("FAIL", "rubric has no source: copy it from the event's judging page"))
    else:
        rows.append(Row("PASS", f"rubric from {rubric['source']}"))

    team = event.get("team", {})
    members = [m for m in team.get("members", []) if m.get("name")]
    if not team.get("presenter"):
        rows.append(Row("FAIL", "no presenter: one person presents ([team] presenter)"))
    else:
        rows.append(Row("PASS", f"one presenter: {team['presenter']}"))
    if len(members) > 4 and "solo" not in layers(fmt):
        rows.append(Row("CONFIRM", f"{len(members)} members: over four, process loss sets in"))

    if not event.get("scope", {}).get("core"):
        rows.append(Row("FAIL", "no [scope] core: the mock boundary has nothing to protect"))

    refs = [(s.get("name", "?"), ref) for s in event.get("sponsors", [])
            for ref in s.get("used_in", [])]
    broken = []
    for name, ref in refs:
        path, _, line = ref.rpartition(":")
        target = ROOT / path
        if not (target.is_file() and line.isdigit()
                and int(line) <= len(target.read_text(encoding="utf-8").splitlines())):
            broken.append(f"{name} → {ref}")
    if broken:
        rows.append(Row("FAIL", "sponsor references that don't exist: " + "; ".join(broken)))
    elif refs:
        rows.append(Row("PASS", f"{len(refs)} sponsor integration reference(s) resolve"))

    mocks_md = read("MOCKS.md")  # every file in any folder named mocks, ignored files aside
    mock_files = [f for f in git("ls-files", "--cached", "--others", "--exclude-standard")
                  .splitlines() if "mocks" in Path(f).parts[:-1]
                  and Path(f).name not in (".gitkeep", "__init__.py") and (ROOT / f).is_file()]
    unlisted = [f for f in mock_files if f not in mocks_md and Path(f).name not in mocks_md]
    rows.append(Row("FAIL", "mocks not listed in MOCKS.md: " + ", ".join(unlisted)) if unlisted
                else Row("PASS", f"every mock is listed in MOCKS.md ({len(mock_files)})"))

    demo = read("DEMO.md")
    limit = int(event.get("demo", {}).get("limit_seconds", 180))
    runs = [r for r in table_rows(demo, "Rehearsal log") if len(r) >= 3 and r[1].isdigit()]
    good = [r for r in runs if int(r[1]) <= limit]
    offline = [r for r in good if r[2].lower().startswith("y")]
    if len(good) < MIN_REHEARSALS or not offline:
        rows.append(Row("FAIL", f"rehearsals within {limit}s: {len(good)} of {MIN_REHEARSALS}; "
                                f"offline runs: {len(offline)} of 1 (DEMO.md)"))
    else:
        rows.append(Row("PASS", f"{len(good)} timed rehearsals, {len(offline)} offline"))

    answers = md_field(read("DEFENSE.md"), "Answer")
    blank = [str(i + 1) for i, a in enumerate(answers) if not a]
    if len(answers) < DEFENSE_QUESTIONS or blank:
        rows.append(Row("FAIL", "Q&A answers missing in DEFENSE.md: question(s) "
                                + ", ".join(blank or ["(some removed)"])))
    else:
        rows.append(Row("PASS", "all five Q&A answers prepared"))

    medium = event.get("medium", "in-person")
    demo_section = md_sections(read("README.md")).get("Demo", "")
    if medium in ("virtual", "hybrid") and not re.search(r"https?://", demo_section):
        rows.append(Row("FAIL", f"{medium} event: the README's Demo section needs the recorded "
                                "video's link"))
    rows.append(Row("CONFIRM", "the live URL works, and the offline video plays without Wi-Fi"))
    rows.append(Row("CONFIRM", "the golden path runs end to end on the demo laptop"))
    return rows


def check_short(_event: dict) -> list[Row]:
    scope = read("SCOPE.md")
    blank = [label for label in ("Problem", "Aha", "Not a wrapper because")
             if not any(md_field(scope, label))]
    return [Row("FAIL", "SCOPE.md gates not filled: " + ", ".join(blank)) if blank
            else Row("PASS", "the three scope gates are filled")]


def check_long(clock: Clock | None, t: dt.datetime) -> list[Row]:
    rows = []
    scope = read("SCOPE.md")
    rows.append(Row("PASS", "SCOPE.md states the problem") if any(md_field(scope, "Problem"))
                else Row("FAIL", "SCOPE.md: **Problem:** is empty"))
    contracts = re.findall(r"^### +\S", read("CONTRACTS.md"), flags=re.MULTILINE)
    rows.append(Row("PASS", f"{len(contracts)} contract(s) in CONTRACTS.md") if contracts
                else Row("FAIL", "CONTRACTS.md has no contracts: write them before the code"))
    if clock and clock.known:
        logged = " ".join(r[0].lower() for r in table_rows(read("MILESTONES.md"), "Milestones"))
        due = [p.name for p in clock.phases() if p.milestone and p.end <= t]
        missing = [n for n in due if n.lower() not in logged]
        rows.append(Row("FAIL", "milestones passed but not logged in MILESTONES.md: "
                                + "; ".join(missing)) if missing
                    else Row("PASS", f"{len(due)} passed milestone(s) logged"))
    return rows


def cmd_preflight(_args: argparse.Namespace) -> int:
    event, fmt = load_event(), load_format()
    t = now()
    try:
        clock: Clock | None = Clock(fmt, event)
    except HackError as e:
        print(red(f"clock: {e}"))
        clock = None
    rows = check_common(event, fmt, clock, t)
    if "judged" in layers(fmt):
        rows += check_judged(event, fmt)
    if "short" in layers(fmt):
        rows += check_short(event)
    if "long" in layers(fmt):
        rows += check_long(clock, t)
    print(bold(f"== preflight: {event.get('name') or '(unnamed event)'} =="))
    paint = {"PASS": green, "FAIL": red, "CONFIRM": yellow}
    for r in rows:
        print(f"{paint[r.result](f'[{r.result}]'):<18} {r.text}")
    counts = {k: sum(r.result == k for r in rows) for k in ("FAIL", "PASS", "CONFIRM")}
    print(bold(f"== {counts['FAIL']} FAIL · {counts['PASS']} PASS · "
               f"{counts['CONFIRM']} to confirm by a person =="))
    return 1 if counts["FAIL"] else 0


# --------------------------------------------------------------------- get ---
def cmd_get(args: argparse.Namespace) -> int:
    node: object = load_event()
    for part in args.key.split("."):
        if not isinstance(node, dict) or part not in node:
            return 1
        node = node[part]
    print("\n".join(map(str, node)) if isinstance(node, list) else node)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hack", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="phase, time left, next checkpoint").set_defaults(func=cmd_status)
    sub.add_parser("schedule", help="every phase with its real times").set_defaults(
        func=cmd_schedule)
    sub.add_parser("preflight", help="the audit before submitting").set_defaults(func=cmd_preflight)
    g = sub.add_parser("get", help="print a value from event.toml")
    g.add_argument("key")
    g.set_defaults(func=cmd_get)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HackError as e:
        print(red(f"hack: {e}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
