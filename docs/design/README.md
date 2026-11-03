# Design documents

One per non-trivial lane, named after it, so `feat/<lane>` <-> `docs/design/<lane>.md`.
Start from [DESIGN-DOC.template.md](../../DESIGN-DOC.template.md); rules and the
which-diagram-when table are in [../design-documentation.md](../design-documentation.md).

Diagrams are **Mermaid in fenced code blocks**, never images -- they diff in a PR and every
assistant can read and write them.

| Lane | Doc | Status | Covers |
| --- | --- | --- | --- |
| `llm` | [llm.md](llm.md) | agreed | class, sequence (retry + repair), contracts, settings |
| `script+grounding` | [script.md](script.md) | agreed | class (scenes, elements, spans), parse sequence + classification rules, contracts |
| `script+grounding` | [grounding.md](grounding.md) | agreed | class (entities, quotes, report), extraction + filter sequence, faithfulness/recall, contracts |
| `shots` | [shots.md](shots.md) | agreed | class (Shot, plan, report), per-scene sequence, range normalisation, name filtering, contracts |
| `verify` | [verify.md](verify.md) | agreed | class (description, judgement, audit, outcome), render→describe→judge→check loop, frame state machine, checks table, contracts, audit log |
| `characters` | [characters.md](characters.md) | agreed; not built (T025 cut 2026-10-19) | portrait + references classes, portrait and frame flow, portrait state machine, prompt rules (no names, script words only), IP-Adapter choice, contracts |
| `comic` | [comic.md](comic.md) | agreed | class (book, pages, panels, bubbles, captions), weights, tiers, lettering budget, frames rendered at panel size, bubble placement, withheld card, contracts, reader JSON |
| `storyboard` | [storyboard.md](storyboard.md) | built | class (styles, prompt parts, renderer, storyboard, pages), plan → render → audit → Storage → PDF sequence, grounded prompt rules and invariant, public/private style validation, render key and cache, contracts, JSON |
| `infra` | [limits.md](limits.md) | built | the hosted demo's monthly token budget, uploads per day, pages per script, the judge seed; flow, `llm_usage`, contracts, copy (T069) |
| `infra` | [deploy.md](deploy.md) | agreed | where each piece runs, env contract, browser → web → API flow, Job state, decisions |
| `eval+submission` | [eval.md](eval.md) | built | run/summary/report classes, sample × runs sequence, in-code grounding re-check, table recomputed by the gate, T049's report shape |
| `web` | [web.md](web.md) | built | visual reference (web/*.png + mockups, tokens), lined-script storyboard, Project + Job stage, upload → job flow, API §6 types, component tree, copy |
| `verify` | [vision-model.md](vision-model.md) | built | Nemotron 3.5 Super VL as every vision call (T105): the thinking setting, the measurement, what translated |
| `verify` | [limb-agent.md](limb-agent.md) | measured, not adopted | the limb agent (T111): eye labels, the measurement, the decision (no `LIMBS` check) |
| `eval+submission` | [learning.md](learning.md) | built | run reports and the learning log (T081): `build_report`, the markdown layout, the log entry |
| `narration` | [narration.md](narration.md) | draft, stretch (not in the submission) | the comic read aloud by ElevenLabs (T113, US5): voices, clips, routes; no code |
