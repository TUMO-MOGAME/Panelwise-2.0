# Q&A defence

Judges use the Q&A to decide whether this is real engineering or a concept pitch. There is no live
Q&A at this event: judges read the README, the Devpost story and the repo, so these answers belong
there too (T033, and [docs/submission/about.md](docs/submission/about.md)). Each answer says what
is true **today** and what a named task will make true; update it as tasks land.

### 1. "Which part of what we just saw is real, and which part is mocked?"
State the boundary plainly: the core runs live, and the peripherals in MOCKS.md are mocked for
stability.

**Answer:** Nothing in the pipeline is mocked. Every model call is a live call to Nebius Token
Factory, and nothing is listed in [MOCKS.md](MOCKS.md). The unit tests replace the network with
`httpx2.MockTransport` so they run offline, but those are tests, not the demo. The one thing a judge
may see that isn't computed on the spot is the seeded judge project, rendered in advance so the
demo costs nothing to open (T030); uploading a script of your own runs the whole pipeline live.
And one plain fact about models: the frame audit's *describe* step runs on
`nvidia/Nemotron-3.5-Super-VL` with thinking off since 2026-10-17 (T105, findings U8). Before
that no Nemotron model on Token Factory accepted images (findings U7), so it ran on
`deepseek-ai/DeepSeek-V4.1-Flash`. Nemotron Super makes the verdict and never sees the image (T020).

### 2. "Can we try it with an input of our own?"
Accept straight away. If it breaks, give a calm post-mortem of the case it didn't handle.

**Answer:** Yes: upload any screenplay PDF to the hosted demo, within its upload limits (T030).
The parser expects standard screenplay layout (scene headings, character cues, dialogue). A
scanned PDF with no text layer, or a text with no `INT.`/`EXT.` scene heading, raises
`ScriptParseError` with that reason instead of returning an empty screenplay that looks like
success (docs/design/script.md § Failure paths). Grounding fails safe: a quote the model proposes that can't
be located in the script is dropped and reported, never shown, so an unusual script gives fewer
entities, not invented ones (docs/design/grounding.md).

### 3. "Why this database, framework or model?"
Defend it with a concrete constraint (latency, payload size, a guarantee), not popularity.

**Answer:** The fast tier is Nemotron 3.5 Lightning: 600 requests and 400K tokens a minute, $0.06
in / $0.24 out per million tokens, and Token Factory **enforces** a strict `json_schema` on it
(findings U1), which schema-bound extraction needs. Thinking is switched off on that tier, which
took a one-number answer from 271 completion tokens to 4 (U2). Nemotron 3 Super, with thinking on,
is the reasoning tier for judgement calls. Images render with FLUX.2 [klein] on fal.ai because Token
Factory serves no image-generation model (U5); ComfyUI on a Nebius GPU was the first plan, cut on
2026-10-19 (T003): a GPU kept up to 15 Dec would cost about $2,500. The vision step uses Nemotron 3.5 Super VL with thinking off (T105,
findings U8): on the-red-kite's 44 stored attempts it made no errors, used 0.95× DeepSeek's tokens
and was as often right on the disputed checks. Before 2026-10-17 it was DeepSeek-V4.1-Flash, after
the cheapest model we first chose (GLM-5.3-Flash) stopped receiving images (findings § U7
re-check, 2026-09-30).

### 4. "How did you check that it's accurate, safe or reliable?"
Cite your evaluation: even 5–10 deterministic test cases with measured results.

**Answer:** 15 live runs on three self-written samples (T031, T032; `eval/README.md`): 0
ungrounded quotes or shot citations kept, every action paragraph and speech in exactly one shot,
faithfulness 0.898 (246 of 274 entities) and recall 0.944 (85 of 90). The first check, on
2026-09-28, was a 3-scene sample at 1.000 / 1.000 (STATUS.md log). We report precision and recall
together because FrameFlow once scored a perfect 1.0 faithfulness while its recall was at most ~6%.
Every push runs the gate: ruff, pyright, pytest, eslint + tsc, vitest, next build, and placeholder,
secret, vulnerability and duplication scans, and the API image build (11 checks). The audit is scored on 109 drawings labelled by eye (T124, `eval/measurements/t124/`): it withholds 38 of 57 wrong frames and 1 of 40 right ones; model by model in eval/audit-mistakes.md (#194). T049 was closed on 2026-10-12.

### 5. "What did you deliberately cut, and why?"
Frame it as scope control: pruned at the midpoint so the golden path has no defects.

**Answer:** FrameFlow's multi-provider fallback chain (Gemini, Ollama): Panelwise calls one
provider, so an error names the model that failed instead of the last one in the chain
(`app/llm/client.py`). Self-hosting an NVIDIA vision model on the Nebius GPU is not needed, since
Nemotron 3.5 Super VL runs on Token Factory (findings § The vision decision, U8). ComfyUI on a
Nebius GPU (T003): cut on 2026-10-19, as a GPU kept up to 15 Dec would cost about $2,500; fal.ai
draws instead. Reference portraits (T025): cut on 2026-10-19, with consistent looks carried by the
script's own words in the frame prompts (T079). A check for bodies
drawn wrong (T111): measured on Super VL against 175 drawings labelled by eye and not adopted, as
it caught 5% of the defects (findings § U9). Private style packs are never needed for the demo
(Non-negotiable 2). Editable panels, animatics and shot-list export to scheduling tools are after
the event ([SCOPE.md](SCOPE.md) § Out of scope).

## Appendix material (in the README or the Devpost story, after the main content)

- [ ] The data model: the class diagrams in [docs/design/script.md](docs/design/script.md) and [docs/design/grounding.md](docs/design/grounding.md), plus verify and comic (T010, T011)
- [ ] Edge cases, and how they're handled: dropped quotes, parse errors, audit retry cap (T021)
- [ ] Unit economics: measured on the-red-kite (2026-10-16): 339,000 tokens and 44 drawings, about $0.15 on Token Factory (at most $0.19) and about $0.30 end to end (the Devpost draft's catalog-price estimate was ~$0.05); expected renders per frame from the audit loop (T021)
