# Demo

The demo is the release. This event has no live pitch: judges score the **video** (a public
YouTube video, 3 minutes or shorter, "with audio covering how you used Nebius Token Factory and
NVIDIA Nemotron") and the **hosted demo**, which must stay up, free and unrestricted, until
15 Dec. The narration is the team's script voiced through the ElevenLabs API (`event.toml [team] presenter`, decided in T034). The limit is
`event.toml [demo] limit_seconds` = 180.

Only public-domain or self-written screenplays appear anywhere in the video or the demo (T031).
Every step below names the task that makes it real; nothing is shown before that task is done.

## Pitch (the video, 180 s)

30% problem, 70% solution and demo.

| Time | Part | On screen |
|---|---|---|
| 0:00–0:20 | Hook: Panelwise turns a screenplay into a storyboard and a comic, and every panel traces back to the script | title card over a finished comic page (T023) |
| 0:20–0:50 | The problem: a storyboard needs an artist, time and money, and image models invent things the script never says | a raw image-model frame beside the script line it contradicts |
| 0:50–1:10 | The solution: what it does, before how | the README flow diagram |
| 1:10–2:20 | Live demo: the golden path below, from upload to the audit log | the hosted app (T030) |
| 2:20–2:40 | Architecture, in the audio: Nemotron 3.5 Lightning on Token Factory extracts and plans; FLUX.2 [klein] on fal.ai renders; Nemotron 3.5 Super VL describes each frame and Nemotron Super judges it | the README diagram, corrected for the describe/judge split |
| 2:40–3:00 | Close: the measured faithfulness, recall and audit numbers (T032, T124), the repo link | one slide |

## Golden path script

The recorded path is [docs/submission/video.md](docs/submission/video.md): pre-opened tabs on the
judge account, no upload on camera. It wins wherever the steps below differ.

Pre-fill every input. Never click an unrehearsed path on camera.

1. Open the hosted demo (T030) signed in as the seeded judge account.
2. Upload the demo screenplay, `samples/the-red-kite.pdf` (T031; self-written, see `samples/README.md`).
3. The scenes, characters and locations appear, each with its verbatim quote and page/line span (T006 builds it; T009 shows it in the app).
4. The shot list appears, planned on Nemotron (T007, T009).
5. Frames render, one per shot, in a public style (T008, T026).
6. Open the audit log: one frame was re-rendered, with the vision model's description and Nemotron's verdict shown (T020, T021).
7. Export the storyboard PDF (T027).
8. Switch to the comic: pages with speech bubbles taken from the script's dialogue, in the reader (T022–T024).
9. Click a panel to show the script lines it came from (Non-negotiable 1, PLAN.md; T009 for frames, T024 for comic panels).

## Fallbacks

- [x] The seeded judge project is already rendered, so a judge sees a full storyboard and comic without spending credit or waiting on a GPU (T030).
- [x] LLM and image spend caps and upload limits on the hosted demo, so a judge can't drain the credit before 15 Dec (T030).
- [x] The video itself is the offline recording of the whole walkthrough, made during the freeze (Wed 28 – Thu 29 Oct): link in `event.toml [links] video` (T034).
- [ ] Appendix material for judges who read further ([DEFENSE.md](DEFENSE.md)).

## Rehearsal log

At least five timed takes within 180 s, one of them recorded with the network off (playing the
pre-rendered seeded project). `./hack preflight` counts these rows. The takes are recorded in T034.
On 29 Oct the video was produced rather than performed live: screenshots of the hosted app (judge
account) with an ElevenLabs narration, so there were no live takes; the row below is that video.

| When | Seconds | Offline? | Notes |
|---|---|---|---|
| 2026-10-29 | 173 | yes (a video file) | Produced, not a live take: hosted app screenshots, ElevenLabs narration (Jedediah); the submitted cut has no music (YouTube, 30 Oct); Tumo (via Claude) |
