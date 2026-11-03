# Rubric map

The weights live in `event.toml [rubric]`: Devpost's four judging criteria, **equal weights**
(25 each). Two of them, **Technological Implementation** and **Quality of the Idea**, name
"Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron" in their own text, so Nemotron on
Token Factory has to be visibly load-bearing, not a footnote. Judging runs 1–15 Dec, from the
repo, the hosted demo and the video, with no live pitch.

Judges' scores are normalised across panels, and that punishes polarised scores: a steady 8 from
every judge beats a 10 and a 2. Build for stability before flourishes.

"Built" below means listed under *What's built so far* in [STATUS.md](STATUS.md). Everything else
is planned, with the task that delivers it.

| Criterion (Devpost's question) | Evidence built today | Planned (task) |
|---|---|---|
| **Technological Implementation** — "How well is the project built, and how effectively does it use Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron as part of the solution?" | Token Factory measured before and while building: U1–U9 in [docs/nebius-findings.md](docs/nebius-findings.md) (strict `json_schema` enforced on Nemotron; thinking off takes Lightning from 271 to 4 completion tokens; the switch to Nemotron 3.5 Super VL measured before it was made). `app/llm` with fast / reasoning / vision tiers (T004); the parser with a span on every element (T005); grounding on Nemotron 3.5 Lightning, every kept quote located (T006); the shot planner (T007). Frames drawn by FLUX.2 [klein] on fal.ai (T026). The frame audit: Nemotron 3.5 Super VL describes, Nemotron Super judges, code checks, re-render on mismatch (T020, T021, T105), with agents for sex, presence, layout and heads (T095, T099, T102, T104, T097). Hosted on Vercel + Render + Supabase with spend caps (T037, T063), the judge account seeded with the-red-kite's storyboard and comic (T030, 2026-10-20). Gate: 11 checks across 2 projects | — |
| **Design** — "Does the project deliver a complete, coherent product experience not just a technical proof of concept?" | In the web app: upload → script → shots → storyboard (T040–T042, T009); the audit log with "Try another render" (T061); the storyboard PDF (T027); the comic made, stored and read (T064, T024), with its PDF (T023). Comic lettering that reads like a comic: bubbles by the speaker's head, tails that never cross and point at the mouth, balloon shapes from the script's own words, one speaker's lines linked (T098, T112, T114–T121) | Characters that stay consistent across panels (T025: cut 2026-10-19; T079's look prompts carry the looks). Stretch: the comic read aloud (T113, not built) |
| **Potential Impact** — "Does the project make a credible, specific case for solving a real problem for a real audience and does the solution actually address it based on what's demonstrated?" | The problem and persona ([SCOPE.md](SCOPE.md)); the Devpost story draft ([docs/submission/about.md](docs/submission/about.md)). Public-domain and self-written samples only (T031); extraction and shot-plan numbers (T032, `eval/README.md`); the audit scored on 109 drawings labelled by eye, 38 of 57 wrong frames withheld and 1 of 40 right ones (T124, [eval/measurements/t124/](eval/measurements/t124/README.md); model by model in [eval/audit-mistakes.md](eval/audit-mistakes.md)); run reports for every live run ([eval/runs/](eval/runs/README.md)) | A video showing it end to end (T034) |
| **Quality of the Idea** — "Is this a creative, non-obvious use of Nebius Token Factory or AI Cloud model(s), and NVIDIA Nemotron and does the team show genuine understanding of the problem space?" | Grounding enforced in code after generation: a quote that can't be located in the script is dropped (T006). Recall reported beside faithfulness, because FrameFlow's perfect precision hid a recall of at most ~6% ([docs/submission/about.md](docs/submission/about.md) § Challenges). Nemotron as the judge of an image-audit loop, with each new check kept only if it measures well: the body check (T111) was measured against 175 eye labels and not adopted (findings § U9). Findings that contradicted the catalog (U1, U2, U7) | Tool feedback for the Devpost form (T033) |

A feature that appears in no row is a candidate to cut ([SCOPE.md](SCOPE.md) § Out of scope).

**Honesty line for every row:** the frame audit is two steps on two models. Since 2026-10-17 the
*describe* step runs on `nvidia/Nemotron-3.5-Super-VL` (T105, findings U8); before that no Nemotron
model on Token Factory accepted images (findings U7) and it ran on `deepseek-ai/DeepSeek-V4.1-Flash`.
Every claim a judge reads uses the approved wording, *"Nemotron 3.5 Super VL describes each frame;
Nemotron Super judges it against the script"* (docs/super-vl-migration.md), never "Nemotron vision
auditor", which suggests one model does both.
