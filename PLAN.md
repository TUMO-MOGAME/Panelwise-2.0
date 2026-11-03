# `Panelwise` — Implementation Plan (the HOW)

**Companions:** [SPEC.md](SPEC.md) (the WHAT) · [docs/design/](docs/design/) (the shapes) ·
[TASKS.md](TASKS.md) (the task list)

---

## Summary

A FastAPI service and a Next.js web app. The screenplay is parsed, entities and shots are
extracted by NVIDIA Nemotron on Nebius Token Factory with verbatim source spans, frames are rendered
by FLUX.2 [klein] 4B on fal.ai (FLUX.1 [schnell] before 2026-10-11) (ComfyUI on a Nebius GPU cut 2026-10-19, T003; storyboard.md §3.5), and every frame is audited before it reaches a storyboard or comic
page: Nemotron 3.5 Super VL describes it (since 2026-10-17, T105) and Nemotron judges it against its
shot spec. The key bet:
**grounding plus an auditor loop** makes generated panels trustworthy, which is what the judges
score. Hard constraints: submission by
30 Oct 2026 10:00 PDT, the demo stays up until 15 Dec, about $50 of Token Factory credit, and the
public repo must run everything the demo shows.

---

## Non-negotiables (project principles)

These are the values every change is held to. If you're also running Spec-Kit or a similar tool,
this list is the "constitution" in plain language — keep both in sync, or drop the formal
constitution and let this section be the single copy (see
[docs/planning-workflow.md](docs/planning-workflow.md)).

1. **Grounded panels.** A frame or panel never shows a character, prop, line or event that is not in the screenplay. Every panel traces to a verbatim source span, and every audit verdict is logged.
2. **Stay inside the credits.** LLM and image spend are capped in code; fast-tier Nemotron by default, the reasoning tier only where it earns it. **The public repo runs everything the demo shows**: private style packs are optional and never needed for the demo.
3. **Test-first.** Each user story writes failing tests before implementation.
4. **Design before code, and no placeholders.** Non-trivial lanes have a merged design doc in
   [docs/design/](docs/design/) with the diagrams implementation is checked against; nothing ships
   with a `TODO`, a stub body, or hard-coded stand-in data. Can't build the real thing → the task
   is blocked, not done. (AGENTS.md §2a ·
   [docs/design-documentation.md](docs/design-documentation.md).)
5. **Phased delivery.** Independent user stories; each phase ends demoable.
6. **Coordinate through shared state.** STATUS.md, AGENTS.md, and TASKS.md are the only coordination
   surfaces; one writer per task.
7. **Branch-only, always-green `main`.** No direct pushes; every change lands via PR with a green gate.

---

## Technical Context

> 📝 The Architecture / Messaging / Frontend / Containerization rows carry this project's defaults
> from [docs/architecture-defaults.md](docs/architecture-defaults.md) — overwrite them if this
> project has a real reason to deviate (and say what it is), don't just leave them as unexamined
> defaults. Record **exact, pinned versions** in the `Language(s)` / `Runtime` rows — default is the
> latest LTS/stable, verified against the source rather than assumed (architecture-defaults §5).

| Dimension | Value |
| --- | --- |
| **Language(s) + versions** | **Python 3.14** (image `python:3.14.7-slim-trixie`; Python has no LTS line, 3.14 is the newest stable) · **Node 24.21.0 LTS** (image `node:24.21.0-trixie-slim`; Node 26 only becomes LTS on 2026-10-28) · Next.js 16.4.1 (16.3.6 until T060, 2026-10-08: six advisories; 16.3.8 until T127, 2026-10-22: three critical) · pnpm 11.10.0 · uv 0.11.32. Local datastore: `postgres:17.11-trixie`, the Supabase project's own version (changed from 18.6 on 2026-10-02, Katlego's decision: tests run on what production runs; deployed: Supabase Postgres; Redis removed 2026-09-29). Checked against endoflife.date and Docker Hub on 2026-09-28 (T002) |
| **Architecture** | `Modular monolith - one FastAPI API service plus one Next.js web app, split by module not by service` |
| **Messaging / async** | `none (job status and progress in a Postgres table; Redis removed 2026-09-29)` |
| **Frontend** | `Next.js + shadcn/ui (Radix + Tailwind + CVA)` |
| **Containerization** | `Docker per service + one docker-compose.yml for local dev` |
| **Runtime/deploy target** | Web on **Vercel**, API on **Render** (`render.yaml`), data/storage/auth on **Supabase**; images by FLUX.2 [klein] 4B on **fal.ai** (FLUX.1 [schnell] before 2026-10-11) (changed 2026-10-09 from ComfyUI on a Nebius GPU, cut 2026-10-19: a GPU kept up to 15 Dec would cost about $2,500; storyboard.md §3.5). Changed 2026-09-29 from "API + web on Nebius" to the Hackathon kit's stack; API host changed 2026-10-08 by Katlego from Railway (never deployed) to Render: [docs/design/deploy.md](docs/design/deploy.md) §8, §11 |
| **Data layer** | Supabase Postgres via the session pooler (SQLAlchemy 2 async + Alembic; compose Postgres locally), Supabase Storage for images, Supabase Auth |
| **Key external services/models** | Nebius Token Factory: Nemotron fast tier (Lightning), reasoning tier (Nemotron Super), vision model Nemotron 3.5 Super VL with thinking off since 2026-10-17 (T105; IDs in .env.example) · **stretch (US5, T113):** ElevenLabs text-to-speech for narrating the comic, off without `ELEVENLABS_API_KEY`, capped by `NARRATION_MONTHLY_CHARACTER_CAP` ([narration.md](docs/design/narration.md)) |
| **Testing** | pytest + ruff + pyright; Vitest + Playwright; eval/ benchmarks |
| **Perf/cost goals** | Full script under ~$0.10 of Token Factory credit (measured on the-red-kite, 2026-10-16: about $0.15, at most $0.19; about $0.30 with fal); one frame in seconds, not minutes, at $0.003 per frame on fal.ai (≤ 1 MP drawn) |
| **Constraints** | OSI licence, public repo, 3-minute video, no copyrighted scripts in repo/demo/video |
| **Scale** | Judges plus a demo account; tens of concurrent users at most |

---

## Project structure

The long version, with why each module exists, is in [docs/project-structure.md](docs/project-structure.md).

```
panelwise/
├── LICENSE                      # Apache-2.0
├── README.md                    # setup, Nemotron + Token Factory usage, demo link
├── CHANGES-FROM-FRAMEFLOW.md    # the "what was significantly updated" disclosure
├── .env.example                 # key names only
├── docker-compose.yml           # local: postgres, api, web; deployed: Vercel/Render/Supabase
├── render.yaml                  # the hosted API on Render
├── infra/                       # README only: ComfyUI on a Nebius GPU (T003, cut 2026-10-19)
├── services/api/                # FastAPI
│   ├── app/
│   │   ├── core/                # config, auth, budget (+ LLM spend cap), tracing
│   │   ├── llm/                 # nebius provider, model tiers, structured_chat
│   │   ├── script/              # parser, scene_time, speakers
│   │   ├── grounding/           # extraction, grounding filter, faithfulness
│   │   ├── shots/               # shot planner
│   │   ├── storyboard/          # frame gen, styles registry, PDF        (headline)
│   │   ├── verify/              # frame audit (vision model describes, Nemotron judges) + re-render loop
│   │   ├── comic/               # page layout, panel sizing, bubbles, lettering
│   │   ├── projects/ jobs/ frames/ storage/ limits/ demo/   # uploads, job state, frame rows, Storage, spend caps, the judge seed
│   │   ├── characters/          # name redaction, labels, sex from the script's words (portraits cut, T025)
│   │   ├── images/              # README only (planned, not built; fal renders from storyboard/fal.py)
│   │   └── api/v1/              # projects, script, shots, storyboard, comic, audit log
│   ├── tests/
│   └── tools/                   # build_samples, build_comic_reference, evaluate
├── apps/web/                    # Next.js: upload → shots → storyboard → comic reader
├── packages/shared/             # types + api client (README only)
├── styles/                      # public storyboard + comic styles
├── samples/                     # public-domain / self-written screenplays ONLY
├── eval/                        # faithfulness + frame-audit benchmarks
└── (Cultivation kit)            # AGENTS/STATUS/SPEC/PLAN/TASKS, docs/, scripts/gate.sh, .githooks/, .claude/
```

---

## Design documents

The diagrams implementation is built and reviewed against. One per non-trivial lane, merged before
that lane's implementation tasks are written — see
[docs/design-documentation.md](docs/design-documentation.md).

| Lane | Design doc | Covers |
| --- | --- | --- |
| `llm` | [llm.md](docs/design/llm.md) | the Token Factory client, tiers, `structured_chat` |
| `script` | [script.md](docs/design/script.md) | the parser and its spans |
| `grounding` | [grounding.md](docs/design/grounding.md) | extraction, the grounding filter, faithfulness and recall |
| `shots` | [shots.md](docs/design/shots.md) | the shot planner |
| `storyboard` | [storyboard.md](docs/design/storyboard.md) | styles, frame prompts, rendering on fal.ai, the PDF |
| `verify` | [verify.md](docs/design/verify.md), [vision-model.md](docs/design/vision-model.md), [limb-agent.md](docs/design/limb-agent.md) | the frame audit, the re-render loop, the vision model; the limb agent (measured, not adopted) |
| `comic` | [comic.md](docs/design/comic.md) | page layout, bubbles, lettering, the reader |
| `characters` | [characters.md](docs/design/characters.md) | reference portraits (not built: T025 cut) |
| `web` | [web.md](docs/design/web.md) | the web app and the API it calls |
| `deploy` | [deploy.md](docs/design/deploy.md), [limits.md](docs/design/limits.md) | Vercel + Render + Supabase; spend caps and upload limits |
| `eval` | [eval.md](docs/design/eval.md), [learning.md](docs/design/learning.md) | the measured numbers; run reports and the learning log |
| `narration` | [narration.md](docs/design/narration.md) | US5 stretch, not built |

---

## Build phases (MVP-first)

Mirrors [TASKS.md](TASKS.md). Each phase should be independently demoable at its checkpoint.

0. **Design** — domain model + one design doc per non-trivial lane (markdown, merged first).
1. **Setup** — repo skeleton, CI, lint/test config, schemas/contracts.
2. **Foundational (blocking)** — the pieces every user story depends on.
3. **US1** — upload a script and get a grounded storyboard (one frame per shot, public style, PDF).
4. **US2** — frame audit with re-render and a visible audit log. **US3** — comic pages with speech bubbles. **US4** — consistent characters via reference portraits (cut 2026-10-19, T025).
5. **Hardening** — validation, budget/latency enforcement, edge cases.
6. **Polish / submission** — docs, checklist, release.

---

## Testing gate

- **Test-first:** every story phase writes failing tests before implementation.
- **Gate:** the [pre-push hook](.githooks/pre-push) runs [scripts/gate.sh](scripts/gate.sh) — lint,
  type checks, the fast suite, and the placeholder, secret, vulnerability and duplication scans; CI
  re-runs it plus anything too slow/expensive for local (integration, latency, real-model smoke tests).

See [docs/testing-strategy.md](docs/testing-strategy.md).
