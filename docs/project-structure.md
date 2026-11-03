# Project structure

## The tree

```
panelwise/
├── LICENSE                      # Apache-2.0
├── README.md                    # setup, Nemotron + Token Factory usage, demo link
├── CHANGES-FROM-FRAMEFLOW.md    # the "what was significantly updated" disclosure
├── .env.example                 # key names only
├── docker-compose.yml           # local: postgres, api, web; deployed: docs/design/deploy.md
├── render.yaml                  # the hosted API on Render (the web app: apps/web/vercel.json)
├── infra/
│   ├── nebius/                  # README only: ComfyUI on a Nebius GPU (T003, cut 2026-10-19)
│   └── comfyui/workflows/       # README only (T003 cut)
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
│   │   ├── projects/ jobs/ frames/ storage/ limits/ demo/   # uploads, job state, frame rows, Supabase Storage, spend caps, the judge seed
│   │   ├── characters/          # name redaction, labels, sex from the script's words (portraits cut, T025)
│   │   ├── images/              # provider chain + cache (planned, not built; fal renders)
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

## Why this shape

- **A modular monolith, not microservices.** The hackathon runs five weeks and has two builders.
  One FastAPI service split into modules gives the same boundaries without the deploy overhead.
  The modules talk through plain Python interfaces, so any one can be split out later.
- **The storyboard pipeline is the spine.** `script → grounding → shots → storyboard` is the chain
  every feature depends on; `verify` and `comic` sit on top of it.
- **The public/private line is `styles/`.** The style registry loads the public styles in `styles/`
  and, if `PANELWISE_PRIVATE_STYLES` points somewhere, a private pack from outside the repo. The
  hosted demo uses only public styles, so judges can reproduce everything they see.
- **No copyrighted scripts.** `samples/` holds public-domain or self-written screenplays only.

## Run it

See [README.md § Run it](../README.md#run-it).

## Status

What is built and what is waiting: [README.md § What works today](../README.md#what-works-today) and
[STATUS.md](../STATUS.md). Some folders hold only a README describing their responsibility:
`infra/` (ComfyUI on a Nebius GPU, T003, cut 2026-10-19: fal.ai renders), `packages/shared/`, and
`app/images/` (the renderer lives in `app/storyboard/`, storyboard.md §3.5).
