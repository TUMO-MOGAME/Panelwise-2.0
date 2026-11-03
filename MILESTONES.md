# Milestones

One row per milestone in `./hack status`, written when it passes: what was actually shown working,
and the proof (a commit, a recording, a URL). `./hack preflight` checks that every passed milestone
has a row whose first cell contains its name exactly as the clock spells it.

The milestones are STATUS.md's weeks (the clock is `.hack/format.toml`). What each one must show is
planned in [SCOPE.md](SCOPE.md) § Milestones; this file records only what happened. A milestone
that slips gets its row anyway, saying what was shown and what moved to which task, and the
STATUS.md timeline row changes in the same PR.

| Milestone (clock name) | Closes |
|---|---|
| Week 1: foundations | Sun 4 Oct, 23:59 SAST |
| Week 2: US1 storyboard | Sun 11 Oct, 23:59 SAST |
| Week 3: US2 audit + US4 portraits | Sun 18 Oct, 23:59 SAST |
| Week 4: US3 comic + hosted demo | Sun 25 Oct, 23:59 SAST |

## Milestones

Weeks 1 and 2's rows were written late, on 2026-10-18, from the merge history and the run reports;
week 3's was written on the evening it closes; week 4's late, on 2026-10-27.

| Milestone | Date | Shown working | Evidence |
|---|---|---|---|
| Week 1: foundations | 2026-10-04 | **Shown, except the GPU.** A self-written sample parses and extracts on Nemotron through Token Factory, with faithfulness 1.000 (5 of 5 entities, 8 of 8 quotes found) and recall 1.000 (2 of 2 speakers), on 28 Sep. Versions are pinned and the local stack runs (T002); the tiered provider (T004), parser (T005) and grounding (T006) are merged. **Slipped:** T003, ComfyUI on a Nebius GPU, for lack of GPU access. It became optional on 9 Oct, and fal.ai's FLUX draws instead (T026); cut 19 Oct | PRs #3 (T001), #5 (T002), #6 (T004), #9 (T005), #10 (T006), all 28 Sep; STATUS log 2026-09-28 (Phase 1 checkpoint); [docs/nebius-findings.md](docs/nebius-findings.md) |
| Week 2: US1 storyboard | 2026-10-11 | **Shown, on the last day.** A script uploaded through the app comes back as a grounded storyboard: one frame per shot in a public style, drawn by FLUX on fal.ai and audited, plus a PDF. Live on the-red-kite at 21:16 SAST on Sun 11 Oct: 21 shots, 16 accepted, 38 drawings. The shot planner (T007), web pages (T040–T042) and the verify, comic and characters designs (T010–T012) were merged earlier | PRs #15 (T007), #27 (T008), #70 (T042), #91 (T026), #99 (T027, the PDF), #101 (T066); [eval/runs/2026-10-11-the-red-kite.md](eval/runs/2026-10-11-the-red-kite.md) |
| Week 3: US2 audit + US4 portraits | 2026-10-18 | **US2 shown; US4 slipped.** Every frame is audited against its shot: a vision model describes it blind, Nemotron judges, and code checks. A failed frame is redrawn up to the cap, and every attempt's verdict is in the audit log in the app (T020, T021, T061). This has been live on every run since 11 Oct, and on the hosted demo since 16 Oct, which audits with Nemotron 3.5 Super VL since 17 Oct (T105). The audit grew agents for sex, presence, layout and heads (T095, T099, T102, T104, T097). Measured on 109 frames labelled by eye (#194), and on Super VL for limbs (T111, not adopted) and for the describer's rooftops and signatures (T106, T107). **Slipped:** T025's reference portraits are not built; cut 19 Oct (Tumo, on Katlego's proposal, #212). The same character's look is carried by T079's look prompts, drawn from the script's own words | PRs #22 (T020), #77 (T021), #78 (T061), #127 (T079), #167, #172, #187, #193, #192, #194, #208, #210; [eval/runs/](eval/runs/); https://panelwise.vercel.app |
| Week 4: US3 comic + hosted demo | 2026-10-25 | **Shown.** A planned project becomes a comic: pages laid out by story beat, every line of dialogue lettered verbatim with its span, frames drawn at panel size and audited, a failed or withheld panel shown as its card, a PDF, and the reader in the app tracing each bubble to its script line (T022, T023, T064, T067, T024). Bubbles placed by the speaker's head, tails that never cross, balloon voices and linked lines (T097, T098, T112, T114–T121). Hosted on Vercel and Render since 16 Oct; on 20 Oct the-red-kite was drawn end to end on the hosted stack (storyboard and a 6-page comic) and copied to the seeded judge account (T030) | PRs #29 (T023), #86 (T064), #87 (T024), #103 (T067), #170 (T097, T098), #197 (T112), #178 (T030), #232 (records T030's hosted run); https://panelwise.vercel.app |
