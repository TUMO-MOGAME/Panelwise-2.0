# Scope

A long event still needs one clear problem. It just has room for more than one milestone of work
toward it. The user stories themselves belong in [SPEC.md](SPEC.md) (US1–US4, with their
scenarios); this file holds the scope decisions and the milestone plan.

## The problem

A specific person and a measurable cost.

**Problem:** A storyboard is how a director shows everyone what the film will look like before a
single day is shot, and on a small production it is often the first thing cut, because it takes an
artist, time and money. Image models could draw it, but they invent: ask for "a kitchen at night"
and you get a third person or a window that isn't in the scene, and a storyboard that shows the
crew something the writer never wrote is worse than none. The cost Panelwise measures is that
invention: every panel must trace to a verbatim span of the script (PLAN.md Non-negotiable 1), and
faithfulness, recall and frame-audit accuracy are reported as numbers (T032 for extraction over
the samples; the audit on 109 hand-labelled frames, T124, after T049 closed on 2026-10-12).

## Who it's for

**Persona:** the writer-director of a small production who has a finished screenplay and no
storyboard artist, and needs shot-by-shot frames the crew can trust. The same script as a comic
book is Panelwise's second output, held to the same grounding rule.

## Milestones

What each milestone in `./hack status` will show working (the weeks of STATUS.md's timeline). Log
what was actually shown in [MILESTONES.md](MILESTONES.md).

| Milestone | Shows working |
|---|---|
| Week 1: foundations | A sample script parses and extracts on Nemotron with faithfulness and recall (T001, T002, T004–T006: done). ComfyUI renders a frame on a Nebius GPU, with its cost per hour and seconds per frame (T003: cut 2026-10-19; fal.ai draws, T026) |
| Week 2: US1 storyboard | Upload a script in the web app and get a grounded storyboard: one frame per shot in a public style, and a PDF (T007–T009). Design docs for verify and comic merged (T010, T011) |
| Week 3: US2 audit + US4 portraits | Each frame audited against its shot spec, re-rendered on mismatch within a retry cap, every verdict in a log visible in the app (T020, T021). The same character looks the same across panels (T012, T025: cut 2026-10-19; T079's look prompts instead) |
| Week 4: US3 comic + hosted demo | Comic pages with speech bubbles from the script's dialogue, in the reader and as a PDF (T022–T024). The hosted demo is live on Vercel + Render + Supabase with a seeded judge account and spend caps (T030) |

After week 4: hardening and eval (T031, T032, T033, T036), then the freeze with the video and the
submission (T034, T035), by 29 Oct.

## Out of scope

Written down so nobody quietly builds it.

- Editable panels (redraw one frame with a note), animatics with scratch audio, and exporting shot
  lists into scheduling tools: after the event (docs/submission/about.md § What's next).
- Self-hosting an NVIDIA vision model on the Nebius GPU (vision option B): not needed since
  Nemotron 3.5 Super VL on Token Factory describes the frames (T105), and there is no Nebius GPU
  (T003 cut) (docs/nebius-findings.md § The vision decision).
- A multi-provider fallback chain (FrameFlow's Gemini and Ollama): Panelwise runs on Token Factory
  only (`app/llm/client.py`).
- Private style packs in the demo: the public repo runs everything the demo shows (PLAN.md
  Non-negotiable 2).
- Any copyrighted screenplay in the repo, the demo or the video: public-domain or self-written
  samples only (T031).
