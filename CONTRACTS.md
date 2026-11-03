# Contracts

Anything that two people, two lanes or two AIs build against is written down before the code:
endpoints, function signatures, schemas, component props. Then each side can build in parallel and
still fit together. One `###` heading per contract; `./hack preflight` counts them.

In Panelwise the contract text itself lives in **one place only**: §6 of the lane's design doc in
[docs/design/](docs/design/), which the task's `Contract:` field quotes verbatim (TASKS.md
§ Anatomy). This file is the index across lanes, so nothing here is a second copy that can drift.
A new contract gets its heading here in the same PR that merges its design doc.

### `GET /api/v1/health` and web `GET /api/health`
Where:    TASKS.md T002 `Contract:` (200 / 503 / 502 bodies)
Owner:    `infra` · Consumer: `web`, docker-compose healthchecks, the hosted demo (T030)
Status:   built (T002)

### `app/llm`: `NebiusChatModel`, `Tier`, `structured_chat`
Where:    [docs/design/llm.md](docs/design/llm.md) §6, including the exact request body and the thinking defaults per tier
Owner:    `llm` · Consumers: `script+grounding` (T006), `shots` (T007), `verify` (T020)
Status:   built (T004)

### `app/script`: `Screenplay`, `Scene`, `Span`, `parse_pdf`, `resolve_times`, `match_speaker`
Where:    [docs/design/script.md](docs/design/script.md) §6
Owner:    `script+grounding` · Consumers: grounding (T006), shots (T007), comic bubbles (T023)
Status:   built (T005)

### `app/grounding`: `Entity`, `Quote`, `GroundingReport`, `Extraction`, `extract`, `ground`, `locate`
Where:    [docs/design/grounding.md](docs/design/grounding.md) §6
Owner:    `script+grounding` · Consumers: shots (T007), storyboard (T008, T026), verify (T020); characters (T025, cut)
Status:   built (T006)

## Written in their design docs, not yet indexed here

Each contract is §6 of its design doc; a `###` heading above is still to be added for each.
- `shots`: [docs/design/shots.md](docs/design/shots.md) §6 (built, T007).
- `storyboard`: [docs/design/storyboard.md](docs/design/storyboard.md) §6 (built, T008, T026, T027).
- `verify`: [docs/design/verify.md](docs/design/verify.md) §6 (built, T020, T021); the vision tier in [docs/design/vision-model.md](docs/design/vision-model.md).
- `comic`: [docs/design/comic.md](docs/design/comic.md) §6 (built, T022–T024).
- `web` ↔ API: [docs/design/web.md](docs/design/web.md) §6 (built).
- `limits`: [docs/design/limits.md](docs/design/limits.md) §6 (built, T069, T030).
- `characters`: [docs/design/characters.md](docs/design/characters.md) §6 (designed, T012; not built: T025 cut 2026-10-19).
