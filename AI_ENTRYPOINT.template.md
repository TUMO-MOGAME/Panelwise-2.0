# `<TOOL_NAME>`.md — `<PERSON>`'s entry point (`<TOOL_NAME>`)

Copy this file to `<TOOL_NAME>.md` (the filename your tool auto-reads — check its docs; some tools
need a specific name/location) whenever a contributor uses an AI tool not already covered by
[CLAUDE.md](CLAUDE.md) or [GEMINI.md](GEMINI.md). The content is identical in shape — only the tool
name and person change. This keeps the rule from [AGENTS.md](AGENTS.md) §2 true: **the rules are
identical for every assistant, no matter which one you switch to.**

> **Tool doesn't auto-read repo files?** At the start of a session, paste this file + the current
> `STATUS.md` into it. That's all any assistant needs to participate correctly.

## Before you do anything

Read, in this order:

0. **The `## ⇄ HANDOFF` block at the top of [STATUS.md](STATUS.md).** If it says `ACTIVE`,
   another AI has handed work to you: read the handoff document it links, end to end, before
   touching a single file — then resume from its "Resume at" pointer. Do not re-plan or
   re-decide anything it records as locked; that re-derivation wastes the very budget the
   handoff exists to protect. Verify any file, function or identifier it names still exists
   before relying on it. Full rules: [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md)
   § Handoffs.
1. [STATUS.md](STATUS.md) — what's happening right now and who owns which lane.
2. [AGENTS.md](AGENTS.md) — the universal contract (rules, git flow, Definition of Done).
   §2a: build to a drawn shape, never ship a placeholder.
3. [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md) — how multiple AIs share state here.
4. The **design doc for your lane** in [docs/design/](docs/design/), plus anything your task's
   `Design:` field points at.

Then claim a lane in STATUS.md before you start editing.

## Before you write a line of code

Your task in [TASKS.md](TASKS.md) carries `Design: / Files: / Contract: / Verify: / Done:` — all
binding.

1. **Read the `Design:` reference.** The class diagram fixes which fields exist; the sequence
   diagram fixes the call order; the state machine fixes which transitions are legal (undrawn ones
   must be made impossible, not merely unimplemented); `Contract:` is verbatim.
2. **No design reference and the shape isn't obvious? Stop.** Write one from
   [DESIGN-DOC.template.md](DESIGN-DOC.template.md), or ask. Don't proceed on a plausible
   interpretation — plausible-but-wrong looks finished, which is what makes it expensive.
3. **UI: open the reference image the task names and match it** — layout, spacing, tokens, copy.
4. **Diff your output against the diagram before calling it done.**

## What `Panelwise` is

`Panelwise turns a screenplay into a grounded storyboard and then a comic book. Nemotron models on Nebius Token Factory extract characters, locations and shots from the script, image models render one frame per shot, a vision model describes each frame and Nemotron audits it against the shot spec, re-rendering on mismatch, and the frames are laid out as storyboard pages or comic pages with speech bubbles from the script dialogue.`

The plan lives in [PLAN.md](PLAN.md); the WHAT in [SPEC.md](SPEC.md); the task list in [TASKS.md](TASKS.md).

## What you (`<TOOL_NAME>`) should do

- **Research** and summarize `<source material, if any>`.
- **Scaffold** modules, write **tests first**, review diffs, write and tighten docs.
- **Propose** edits to SPEC / PLAN / TASKS via PR — the team reviews and lands them.
- Work the **same** [TASKS.md](TASKS.md) list everyone uses; one task at a time.
- Keep [STATUS.md](STATUS.md) accurate after every step.

## What you must NOT do

- **Never push directly to `main`.** Always branch and open a PR.
- **Never report a placeholder as done** — no `TODO`/`FIXME`, stub body, empty component,
  hard-coded stand-in data, or constant-returning function. If you can't build the real thing, the
  task is **blocked**: say so in STATUS.md and name what unblocks it. (AGENTS.md §2a.)
- **Never invent structure the design doc doesn't have** — extra fields, extra endpoints, a
  different call order. Change the doc first, in its own PR.
- **Never substitute your own scope.** Deliver the whole task or split it and say so.
- Edit a file another lane has claimed in STATUS.md without coordinating.
- **Own a frontend lane, or restyle the UI.** Visual design, component structure, tokens,
  layout and accessibility are Claude's by default (AGENTS.md §1). Use the existing
  components freely; don't introduce a new palette, restyle a component, or hand-roll UI
  that bypasses the component layer. If you need UI to finish your lane, wire up what
  exists and flag in STATUS.md that it needs a Claude pass.
- **`A storyboard frame or comic panel must never show a character, prop, line of dialogue or event that is not in the screenplay - every panel traces back to a verbatim source span`.** (Non-negotiable I in [PLAN.md](PLAN.md).)
- Blow any stated budgets (runtime, cost, size — see PLAN.md).

## Locked stack (do not swap without a plan change)

`<the real, locked technology choices — same line across every entry-point file>`
