# AGENTS.md — the Panelwise contract

This is the single contract every contributor follows — **human or AI, whichever tool**.
Read it before you touch anything. If a rule here conflicts with a habit, the rule wins.

Entry points funnel here: every per-tool file (e.g. [CLAUDE.md](CLAUDE.md), [GEMINI.md](GEMINI.md))
says "read AGENTS.md first." This file is the source of truth for *how we work*; the
**Non-negotiables** in [PLAN.md](PLAN.md) are the source of truth for *what cannot be compromised*.

> **New session / new tab / new AI? Do this before anything else:**
> 1. Read **[STATUS.md](STATUS.md)** — the live board: what's done, in progress, and next.
> 2. Read this file — the rules below.
> 3. Check the **lane labels** so you don't collide with someone else's work.
> 4. When you finish a meaningful step, **update STATUS.md** before you stop.

---

## 1. Team & lanes

| Person | Role | AI copilot(s) |
|--------|------|----------------|
| Katlego Thapelo Tlhapiso | Project leader | Claude, Gemini |
| Tumo Olorato Mogame | Co-builder | Claude |

> 📝 **Customize:** add a row per contributor. Solo project? One row, and "lanes" still matter — they're
> how *you* avoid two of your own AI sessions colliding. Set the review mode in §4 to `solo` as well.

We do **not** hard-partition file ownership by person; we coordinate with **lane labels** in
[STATUS.md](STATUS.md) instead (e.g. `<lane-example-1>`, `<lane-example-2>`, `docs`, `infra`). Before
working a lane, claim it in the STATUS.md "Current focus" table so nobody else — human or AI — collides
with it.

**Rule:** never edit a file another active lane owns without saying so in STATUS.md first.

### Frontend work goes to Claude

Lanes are otherwise first-come — with one standing exception. **Any lane that produces
user-facing UI is assigned to Claude by default**: visual design, component structure,
styling and token systems, layout, accessibility, and interaction.

Why this one is pinned rather than claimed: the `frontend-design` skill in `.claude/skills/`
only loads for Claude, and it is the thing that keeps UI from drifting into the templated
look. A project's visual identity also degrades fastest when it is authored by several hands
in turn — palette and spacing decisions get re-litigated per session, and the result reads as
assembled rather than designed. One owner keeps it coherent.

In practice:

- Frontend lanes (`feat/<ui-lane>`) are Claude's unless the STATUS.md focus table says otherwise.
- Other AIs may still **use** existing components and read the token file; what they should not
  do is introduce a new palette, restyle a component, or hand-roll UI that bypasses the
  component layer.
- If another AI needs UI to finish its own lane, it wires up the existing components and notes
  in STATUS.md that the styling needs a Claude pass — rather than inventing a look in passing.
- Backend, data, infra and docs lanes carry no such default; claim whichever is free.

If the project has no frontend, this section is inert — delete it.

## 2. How we plan

Planning is driven directly by the team through living documents:

- [SPEC.md](SPEC.md) — the WHAT (user stories, acceptance criteria).
- [PLAN.md](PLAN.md) — the HOW (stack, non-negotiables, code layout, build phases).
- [docs/design/](docs/design/) — the SHAPES (class / sequence / state diagrams, per lane).
- [TASKS.md](TASKS.md) — the checkbox task list (`T001…`).
- [STATUS.md](STATUS.md) — the live board.

The full loop is in [docs/planning-workflow.md](docs/planning-workflow.md).

- **Shared state lives in exactly three places:** AGENTS.md (rules), STATUS.md (live board),
  TASKS.md (the task list). Everything else is derived. If it isn't reflected in these three, it
  didn't happen.
- **Single writer per task.** One task ID (`T0xx`) is worked by one person/AI at a time. Claim it in
  STATUS.md before you start; release it when the PR merges.

See [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md) for the collision-avoidance detail.

## 2a. Build to a drawn shape, and never ship a placeholder

Two rules that apply to every contributor, and that exist because of one specific, repeated failure:
work comes back **adjacent to** what was asked — *a* screen instead of *the* screen, the agreed
function names with stubbed bodies, the right entity with invented fields — and gets reported as
done, because by the letter of the task it was.

**Before you build:**

- Non-trivial work has a **design doc** in [docs/design/](docs/design/) — class diagram for
  entities, sequence diagram for anything crossing a service or agent boundary, state machine for
  anything with a lifecycle, and the exact contracts between lanes. Written in Mermaid, merged
  before the implementation tasks are. Rules and the which-diagram-when table:
  [docs/design-documentation.md](docs/design-documentation.md).
- **If the task has no design reference and you can't tell exactly what shape to build, stop and
  say so.** Write the design doc (it's markdown; it takes minutes) or ask. Do not proceed on a
  plausible interpretation — a plausible-but-wrong implementation is the expensive outcome here,
  because it looks finished.
- **UI work builds to a named visual reference** — the mockup path, the screenshot, the screen it
  must match. If none exists, producing one is the first task, not an assumption you make quietly.

**When you finish:**

- **No placeholder counts as done.** Not `TODO`, not `FIXME`, not `pass` / `NotImplementedError`,
  not an empty component, not hard-coded sample data standing in for a real call, not a function
  returning a constant to make a test green. If the real thing can't be built yet, the task is
  **blocked** — say so in STATUS.md and name what unblocks it. Reporting a stub as complete is a
  correctness failure, not a shortcut.
- The only exception: a stub the task text **explicitly declared**, with a follow-up task ID
  already written for replacing it.
- **Implementation is checked against the diagram**, not the prose. Every class in the design
  exists with those fields; the call order matches the sequence; every drawn state is reachable and
  every undrawn transition is impossible. Code and diagram disagree → fix whichever is wrong, in
  the same PR.

## 3. `main` is always green

- **Branch-only.** Nobody pushes to `main`, ever. The pre-push hook rejects it.
- Enable the hooks once per clone — every contributor, on every clone, because `core.hooksPath` is
  local config and is never cloned: `bash install-hooks.sh`.
- One gate, two triggers: [`scripts/gate.sh`](scripts/gate.sh) holds every check, the
  [pre-push hook](.githooks/pre-push) runs it locally, and [CI](.github/workflows/ci.yml) runs the
  same script on every PR. Add checks to `gate.sh` only — anything added in one place drifts.
- **A check that did not run is a failed check.** The gate has no skip state: missing tooling,
  uninstalled dependencies, or a package with no test script all fail the push rather than reporting
  green. Rationale: [docs/git-workflow.md](docs/git-workflow.md#the-skip-rule).
- A red `main` blocks the whole team, so it never happens.

## 4. Branch & commit flow

- Branch names: `feat/<lane>`, `fix/<thing>`, `docs/<thing>`, `chore/<thing>`.
- Open a PR into `main`. The gate must be green. Then it is reviewed, according to this project's
  **review mode**:
  - **Team mode** (two or more people): a quick review from another contributor.
  - **Solo mode** (one person): a review by a fresh AI reviewer — the `code-reviewer` agent, or a
    different AI tool from the one that wrote the code, never the same session — posted on the
    PR and read by you before you merge. GitHub never lets you approve your own PR, so this
    replaces the human approval; it does not skip review. Details:
    [docs/git-workflow.md](docs/git-workflow.md#solo-mode).

  This project's review mode: **`team`**, with a solo-mode fallback:
  - **When the other contributor is unavailable** and the work can't wait, the author may merge on a
    **fresh AI reviewer's** review instead, exactly as in solo mode: the `code-reviewer` agent or a
    different AI tool, never the session that wrote the change. Its verdict and findings are posted
    on the PR *before* merging, every finding is fixed or answered there, and the PR description
    says `Reviewed by: <reviewer> (fallback — <contributor> unavailable: <when and how they were
    asked, or why they couldn't be>)`. "Unavailable" is that recorded fact, not a feeling.
  - The fallback never covers a change to the Non-negotiables in [PLAN.md](PLAN.md), this file, or
    [scripts/gate.sh](scripts/gate.sh) — those wait for the other contributor, **unless the project
    lead explicitly authorizes the exception**. The authorization, its reason and the PR number go
    in the STATUS.md Log *before* the merge, and the fresh AI review is still required.
  - The other contributor reads fallback-merged PRs when they're back; anything they object to gets
    a follow-up PR, not a revert war.
  - `main` has no server-side branch protection (decided 2026-09-28 while the repo was private on GitHub Free; public since 2026-10-05, turning it on is the team's call),
    so this rule and the pre-push hook are the only guards. Don't merge a PR whose `gate` check is
    red or missing.
- Commit format ties work back to a task ID: `type(lane): T0xx short description`
  (e.g. `feat(audio): T012 faster-whisper HIP transcription`).

Full detail: [docs/git-workflow.md](docs/git-workflow.md).

## 5. Update STATUS.md every step

After any meaningful step, update [STATUS.md](STATUS.md):
1. Tick / add the relevant checkbox and task ID (in [TASKS.md](TASKS.md)).
2. Update the lane's **Status** column and the phase timeline.
3. Add a dated line to the **Log** at the bottom.

Format the header line as: `_Last updated: YYYY-MM-DD — by <name> (via <tool>)_`.

If you don't update STATUS.md, the next session (human or AI) starts blind and you get conflicts.
**Treat STATUS.md as part of "done."**

## 6. Grounding & honesty rules

> 📝 **Customize this section entirely** — it's the single highest-leverage section in this file. Every
> real project has *some* thing an AI must never fabricate (data, citations, financial figures, legal
> claims, screenplay facts, medical claims...). Name yours explicitly; a vague "be accurate" doesn't work
> as a rule anyone can check a PR against. Examples that shipped elsewhere:
> - *"Caption only what the evidence supports — no invented people, places, dialogue, or events."*
> - *"Every extracted entity MUST be verifiable in the source document — no hallucinated production data."*

- **`A storyboard frame or comic panel must never show a character, prop, line of dialogue or event that is not in the screenplay - every panel traces back to a verbatim source span`.** This is **Non-negotiable I** in [PLAN.md](PLAN.md).
- **Respect the budgets.** `<runtime/latency/cost/size budgets, if any>`.
- **Deterministic I/O / graceful degradation.** `<what a partial failure must still produce>`.
- **Report failures honestly.** If a stage breaks or a result comes out weak, say so in STATUS.md.
  Don't paper over a broken run.

## 7. Repository map

```
Panelwise/
├── README.md · AGENTS.md · <per-tool>.md         shared-state entry points
├── STATUS.md · STATUS.template.md                the live board + its template
├── SPEC.md · PLAN.md · TASKS.md                  the planning documents
├── DESIGN-DOC.template.md                        the per-lane design-doc template
├── docs/                                         topic docs (incl. architecture-defaults.md)
│   └── design/                                   per-lane design docs — the diagrams code is built to
├── .claude/                                      agents, /feature-dev command, frontend-design skill
├── scripts/gate.sh                               THE gate — every check lives here, and only here
├── .githooks/pre-push                            branch protection; runs scripts/gate.sh
├── .github/workflows/ci.yml                      runs the same scripts/gate.sh
├── install-hooks.sh                              run once per clone, by everyone
└── <your services/apps tree + docker-compose>    see docs/project-structure.md
```

Our default build shape (microservices · Kafka/RabbitMQ · shadcn/ui · Docker · latest-LTS-pinned)
lives in [docs/architecture-defaults.md](docs/architecture-defaults.md) — with per-project deviations
recorded in [PLAN.md](PLAN.md)'s Technical Context.

## 8. Definition of Done

A task is done when **all** of these hold:
- [ ] Code + tests written; tests were written **first**, failed for the right reason, and now pass.
- [ ] **It matches its design doc** — every class/field, every call in the sequence, every state
      (§2a). Doc corrected in the same PR if reality diverged.
- [ ] **No placeholders anywhere in the diff** — no `TODO`/`FIXME`, stub body, empty component,
      hard-coded stand-in data, or constant-returning function, except one the task explicitly
      declared *and* that has a follow-up task ID (§2a).
- [ ] For UI: visually matches the reference named in the task, not merely "a version of" it.
- [ ] **`bash scripts/gate.sh` is green — and green because it ran, not because it found nothing.**
      Check the count it prints; lint, format, types, and tests all actually executed.
- [ ] The app still boots/imports; the golden-path example still works.
- [ ] No secret in the diff (the gate sweeps, but it only catches known shapes —
      [docs/security-basics.md](docs/security-basics.md)).
- [ ] No dependency with a known vulnerability, unless it's declared in `osv-scanner.toml` against
      a task; no copied logic pushing duplication over the threshold (the gate checks both).
- [ ] Runs inside any stated budgets (no new regression in latency/memory/cost).
- [ ] STATUS.md updated (checkbox + lane status + Log line); task ID referenced in the commit.
- [ ] PR opened into `main`, CI green, reviewed according to the review mode in §4, merged.

## 9. Judged by people (this event)

From the Hackathon kit's judged layer; applied 2026-09-29 on Katlego's authorization.

- **Build to the rubric** (`event.toml [rubric]`, [RUBRIC.md](RUBRIC.md)). A feature that earns no
  points is a candidate to cut. Judges' scores are normalised, and that punishes polarised scores:
  stability first.
- **Mock the edges, never the core.** Peripheral services (payments, email, identity, third-party
  data you can't rely on at demo time) may be mocked in `mocks/` and listed in
  [MOCKS.md](MOCKS.md). Nothing under `event.toml [scope] core` may import from `mocks/`.
  `scripts/gate.sh` does **not** check this yet (that needs a gate change), so reviewers do.
- **Sponsor SDKs are load-bearing or absent.** Record where each one runs in
  `event.toml [[sponsors]] used_in` (file:line). An unused dependency in a package file gets
  spotted.
- **The demo is the release.** [DEMO.md](DEMO.md) is the script. Rehearse it, and keep the
  fallbacks working.

## 10. Long-form rules (a week or more)

From the Hackathon kit's long layer; applied 2026-09-29 on Katlego's authorization.

- **Sustainable pace.** Work in the agreed hours (recorded in STATUS.md by T038), with no
  overnight pushes. Longer formats exist partly to avoid burnout; don't bring it back.
- **A stand-up line per working block** in the STATUS.md Log: done, next, blocked.
- **Contracts before code.** Anything two people or time zones build against goes in
  [CONTRACTS.md](CONTRACTS.md) first (it indexes each design doc's §6).
- **Hand off at every time-zone change**, using the STATUS.md handoff block and
  [docs/HANDOFF.template.md](docs/HANDOFF.template.md): what's done, what's decided, the next
  step, the gotchas.
- **Milestones are demos.** Each milestone in the clock (`./hack status`) ends with something shown
  working; record it in [MILESTONES.md](MILESTONES.md).
