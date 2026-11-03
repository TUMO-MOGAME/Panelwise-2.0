# Nebius Token Factory — findings (T001)

_Measured 2026-09-28 against our own account (trial tier, $1 credit) by Katlego (via Claude).
Every verdict below cites a response captured that day. Total spend for the whole probe: ~$0.004
(59 billed calls, priced from the catalog). U7 was re-checked on 2026-09-30 during T020
([§ U7 re-check](#u7-re-check-2026-09-30)): GLM-5.3-Flash no longer receives images._

Questions U1–U6 come from the FrameFlow Nebius plan (§3); U7 is Panelwise's own.

## Summary

| # | Question | Verdict | Consequence |
|---|---|---|---|
| U1 | Is `response_format: json_schema` enforced on Nemotron? | **Yes.** Schema-valid output even with no schema in the prompt. `json_object` gives valid JSON in the wrong shape; `guided_json` is ignored | T004 sends `json_schema` (strict) and keeps the schema in the prompt too; the repair retry stays as a backstop, not the plan |
| U2 | Can thinking be switched off? | **Yes**, two ways: `chat_template_kwargs: {enable_thinking: false}` or `reasoning_effort: "none"`. `"low"` and a `/no_think` system prompt do **not** switch it off | Fast tier defaults to thinking off. Reasoning arrives in a separate `reasoning_content` field, not as `<think>` in `content` — but `content` can start with `\n`, so strip it |
| U3 | Which host serves which model? | **All four Nemotron models answer on the default host** (`api.tokenfactory.nebius.com`) | One base URL. `NEBIUS_REASONING_BASE_URL` is not needed |
| U4 | Rate limits | Per model, from the catalog and confirmed by response headers. Lightning: **600 RPM / 400K TPM**. A burst of 20 concurrent calls: 20 × 200 | 17 extraction chunks in a burst is far inside the limit. Measured on the trial tier (2026-09-28); not re-read since the Builder Program credit landed |
| U5 | Is an image-generation model served? | **No.** No model in either host's catalog has an image output modality | ~~Rendering stays on ComfyUI on a Nebius GPU (T003)~~ **Superseded 2026-10-09:** FLUX on fal.ai draws every frame (FLUX.2 [klein] 4B today); re-checked 2026-10-08, still no image model ([§ U5](#u5--image-generation)). T003 cut 2026-10-19. FrameFlow plan item N8 is dropped |
| U6 | Sampling for grounded extraction | **Not settled by this probe** — 3 runs at each setting on one short scene all grounded their evidence verbatim | Still open: T006 shipped `temperature` 0.0 without settling it (grounding.md §10). The one failure seen was a *shape* failure under `json_object` (see U1), not a sampling one |
| U7 | Is a vision model served, and does it take an image in a chat message? | **Yes — but none is NVIDIA.** Every Nemotron model is `text->text` and rejects images. Five non-NVIDIA models accept images and all five read our test image correctly on 2026-09-28; **on 2026-09-30 GLM-5.3-Flash no longer received images** ([re-check](#u7-re-check-2026-09-30)), so the describer was DeepSeek-V4.1-Flash (Super VL since 2026-10-17: U8) | **Decided 2026-09-28: option A now, B as a stretch** — see [§ The vision decision](#the-vision-decision) |
| U8 | Is there an NVIDIA vision model now? (2026-10-17) | **Yes: `nvidia/Nemotron-3.5-Super-VL`** (`text+image->text`, listed 12 Oct, released 15 Oct). One probe read a comic page correctly | **Adopted 2026-10-17 (Katlego):** every vision call is Super VL with thinking off (T105). Measured on the-red-kite: it fits (0 errors, 0.95× tokens, 1.43× median time) and most of the audit carries over; T106–T108 adapt the rest ([§ U8](#u8--an-nvidia-vision-model-2026-10-17)) |

## Settled configuration

These are the values in [`.env.example`](../.env.example).

| Variable | Value | Why |
|---|---|---|
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1` | U3: every Nemotron model answers here |
| `NEBIUS_MODEL_FAST` | `nvidia/Nemotron-3_5-Lightning` | 1M context, $0.06 / $0.24 per 1M tokens, 600 RPM; `json_schema` enforced (U1) |
| `NEBIUS_MODEL_REASONING` | `nvidia/nemotron-3-super-120b-a12b` | 262K context, $0.30 / $0.90, 300 RPM |
| `NEBIUS_MODEL_VISION` | `nvidia/Nemotron-3.5-Super-VL`, with `NEBIUS_VISION_THINKING=false` | Since 2026-10-17 (T105, § U8; [super-vl-migration.md](super-vl-migration.md)): the first NVIDIA model on Token Factory that takes an image. Before it, `deepseek-ai/DeepSeek-V4.1-Flash`, which was `zai-org/GLM-5.3-Flash` (cheapest correct VLM on 2026-09-28) until the [U7 re-check](#u7-re-check-2026-09-30) found it no longer receives images. DeepSeek read real storyboard frames correctly, 3000 RPM. The vision model *describes* frames; Nemotron judges |
| `NEBIUS_REASONING_BASE_URL` | removed | U3 |

Other Nemotron models, both served on the default host: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
($0.06 / $0.24, **100 RPM** — a sixth of Lightning's, so a poor fast-tier fallback under load) and
`nvidia/Nemotron-3-Ultra-550b-a55b` ($1.00 / $3.00, 300 RPM, 1M context).

## How it was measured

A standard-library Python script sent each request and saved the full request and response (key
never written). The script is not committed: a `.py` file before T002 lands a manifest fails the
gate, and its reusable part becomes T004's startup check. The requests are reproduced below.

---

## U1 — JSON enforcement

The catalog lists `supported_features: ["tools", "reasoning"]` for every Nemotron model — no
`json_mode`, no `structured_outputs` — so the catalog alone suggested it would not work. It does.

Test scene (self-written, 7 lines) and schema:

```json
{"type": "object",
 "properties": {
   "characters": {"type": "array", "items": {"type": "object",
     "properties": {"name": {"type": "string"}, "evidence": {"type": "string"}},
     "required": ["name", "evidence"], "additionalProperties": false}},
   "location": {"type": "string"}},
 "required": ["characters", "location"], "additionalProperties": false}
```

Five variants × two models, `temperature: 0`, thinking off. "Bare prompt" means the user message
only said *"List the characters in this scene and the location."* — no schema, no mention of
`evidence`.

| Variant | Lightning | Nano |
|---|---|---|
| `json_schema` (strict) + schema in prompt | ✅ valid | ✅ valid |
| `json_schema` (strict), bare prompt | ✅ valid | ✅ valid |
| `json_object` + schema in prompt | ✅ valid | ✅ valid |
| `json_object`, bare prompt | ❌ wrong shape | ❌ wrong shape |
| `guided_json` (vLLM extra), bare prompt | ❌ ignored | ❌ ignored |

Request (the bare `json_schema` case):

```json
{"model": "nvidia/Nemotron-3_5-Lightning",
 "messages": [{"role": "user", "content": "List the characters in this scene and the location.\n\n<scene>"}],
 "response_format": {"type": "json_schema", "json_schema": {"name": "scene", "schema": <above>, "strict": true}},
 "temperature": 0, "chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 1024}
```

Response `content` — note it produced an `evidence` field it was never asked for in words, so the
schema really is steering decoding:

```json
{"characters": [{"name": "Nandi", "evidence": "NANDI (60s, oilskin coat) pours tea into two chipped mugs."},
                {"name": "Thabo", "evidence": "THABO (20s) stands dripping in the doorway, holding a torn map."}],
 "location": "INT. LIGHTHOUSE KITCHEN - NIGHT"}
```

The same bare prompt under `json_object` — Lightning flattened the array to strings; Nano added
fields and **invented a description the scene never gives**:

```json
{"name": "NANDI", "age": "60s",
 "description": "Oilskin coat, weathered, likely a lighthouse keeper or someone connected to the sea"}
```

A second, quieter failure under `json_object` *with* the schema in the prompt (U6, one run in six):
Lightning echoed the schema's own wrapper — `{"type": "object", "properties": {"characters": [...]}}`.
Valid JSON, correct content, unusable shape.

**Consequence for T004:** send `json_schema` with `strict: true`. Keep the schema in the prompt as
well (it's cheap, and the docs recommend it). The repair retry stays, but it should rarely fire.
The grounding filter stays regardless: schema enforcement fixes *shape*, not *truth*.

## U2 — Switching thinking off

Prompt: *"What is 17 * 23? Answer with the number only."* All answers were `391`.

| Setting | Lightning completion / reasoning tokens | Super completion / reasoning tokens |
|---|---|---|
| default | 271 / 266 | 67 / 61 |
| `chat_template_kwargs: {enable_thinking: false}` | **4 / 0** | **4 / 0** |
| `reasoning_effort: "none"` | **4 / 0** | **4 / 0** |
| `reasoning_effort: "low"` | 236 / 231 | 44 / 38 |
| system message `/no_think` | 239 / 234 | 67 / 61 |

- Reasoning tokens are reported in `usage.completion_tokens_details.reasoning_tokens` and billed as
  completion tokens: on Lightning, thinking multiplied the output ~68× for a one-number answer.
- The reasoning text comes back in `message.reasoning_content`, not wrapped in `<think>` inside
  `content`. With thinking on, Super's `content` was `"\n391"` — a leading newline.

**Consequence for T004:** fast-tier calls send `chat_template_kwargs: {enable_thinking: false}` by
default; a caller can opt in per call. Record `reasoning_tokens` in the trace. Still strip a leading
`<think>…</think>` defensively and `.strip()` the content.

## U3 — Hosts

`"Reply with the single word: ok"`, thinking off, each model on each host:

| Model | default host | us-central1 host |
|---|---|---|
| `nvidia/Nemotron-3_5-Lightning` | 200, 1.49 s | 200, 2.40 s |
| `nvidia/nemotron-3-super-120b-a12b` | 200, 2.10 s | 200, 2.38 s |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 200, 1.33 s | 200, 3.04 s |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 200, 1.21 s | 200, 1.83 s |

The default host lists 25 models, us-central1 lists 18. Super and Ultra are *hosted* in
us-central1 (catalog `regions`) but the default host routes to them. Single-call latencies only —
not a benchmark.

## U4 — Rate limits

Limits are **per model**, published in `GET /v1/models?verbose=true` under `per_request_limits`,
and echoed on every response:

```
x-ratelimit-limit-requests: 600          x-ratelimit-limit-tokens: 400000
x-ratelimit-remaining-requests: 587      x-ratelimit-remaining-tokens: 399944
x-ratelimit-reset-requests: 2s           x-ratelimit-reset-tokens: 1s
x-ratelimit-dynamic-scale-requests: 1.00 x-ratelimit-dynamic-period-remaining: 827s
```

| Model | RPM | TPM |
|---|---|---|
| Lightning | 600 | 400K |
| Super | 300 | 200K |
| Ultra | 300 | 200K |
| Nano | 100 | 800K |

Burst test: 20 concurrent Lightning calls → 20 × `200`, no `429`.

Caveats: measured on the **trial** tier; the `dynamic-scale` headers suggest limits can move. On the
us-central1 host, Super/Ultra/Kimi report `1e10` RPM — treat that as "not reported", not unlimited.
**Consequence for T004:** read `x-ratelimit-remaining-*` and honour `Retry-After` on 429 rather
than fixed backoff. TPM, not RPM, is the binding limit for extraction (17 chunks × ~8K tokens ≈
136K tokens, a third of Lightning's minute).

## U5 — Image generation

No model on either host has an image output modality (`architecture.modality` is `text->text` or
`text+image->text` for all 25). `flux-schnell` and `sdxl` are gone. ~~**Consequence:** images render on
ComfyUI on a Nebius AI Cloud GPU (T003), which still satisfies "runs on Nebius AI Cloud".~~

**Superseded (2026-10-09, Tumo; Katlego approved).** Re-checked on 2026-10-08: Token Factory still
serves no image model (`flux-schnell`, `flux-dev` and `sdxl` answer 404). A Nebius L40S kept up
until judging ends (15 Dec) would cost about $2,500, and started per session it would meet judges
with cold starts, so every frame is drawn on **fal.ai**: FLUX.1 [schnell] from 2026-10-09, FLUX.2
[klein] 4B since (at most one megapixel, $0.003 a drawing). ComfyUI on a Nebius GPU stayed an
optional backend until **T003 was cut on 2026-10-19** (Tumo; Katlego's proposal: no money for a
GPU VM). Every model call Panelwise makes still goes to Token Factory; only the drawing doesn't.
The research and sources: [design/storyboard.md](design/storyboard.md) §3.5.

## U6 — Sampling for grounded extraction

Lightning, `json_object` + schema in prompt, thinking off, 3 runs per setting on the test scene:

| Setting | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| `temperature: 0` | NANDI, THABO — evidence verbatim ✅ | same ✅ | schema-wrapper echo (U1) ❌ |
| `temperature: 1.0, top_p: 0.95` | NANDI, THABO ✅ | same ✅ | Nandi, Thabo ✅ |

Note: temperature 0 was **not deterministic** (run 3 differs from runs 1–2).

**Not settled.** Six runs on a 7-line scene can't separate the two settings. NVIDIA's
temp 1.0 / top_p 0.95 recommendation is for reasoning *on*; we run extraction with it off. Decide on
the full-script faithfulness + recall baseline in T006, with `json_schema` (which removes the one
failure seen here).

## U7 — Vision

Test image: a 256×256 PNG, white, with a red square top-left and a blue circle bottom-right, sent
as a base64 `data:` URL in an OpenAI-style content part:

```json
{"role": "user", "content": [
  {"type": "text", "text": "Describe the shapes in this image: for each, its colour and its position (which corner). Be brief."},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,<…>"}}]}
```

| Model | Maker | $/1M in · out | RPM | Result |
|---|---|---|---|---|
| `nvidia/Nemotron-3_5-Lightning` (control) | NVIDIA | 0.06 · 0.24 | 600 | **400** `"This model does not support image input"` |
| `zai-org/GLM-5.3-Flash` | Z.ai | 0.15 · 0.50 | 600 | ✅ "Red square — top-left corner / Blue circle — bottom-right corner" |
| `deepseek-ai/DeepSeek-V4.1-Flash` | DeepSeek | 0.30 · 1.20 | 3000 | ✅ "a red square in the top-left corner and a blue circle in the bottom-right corner" |
| `openbmb/MiniCPM-V-4_5` | OpenBMB | 0.66 · 1.11 | 300 | ✅ "A red square is positioned in the top-left corner. A blue circle is located in the bottom-right corner." Only 32K context |
| `moonshotai/Kimi-K2.6` | Moonshot | 0.95 · 4.00 | 200 | ✅ "Red square: top-left. Blue circle: bottom-right." |
| `moonshotai/Kimi-K3` | Moonshot | 3.00 · 15.00 | 1000 | ✅ correct ("bottom-right (right of center)") |

All four Nemotron models are `text->text` in the catalog. **On 2026-09-28 no NVIDIA vision model
was served on Token Factory** (Super VL was listed 12 Oct: § U8). A two-shape test proves the plumbing works, not that a model can audit a storyboard
frame — frame-audit accuracy is measured in T049.

### U7 re-check (2026-09-30)

T020's first live audit (`app.verify.run`) came back describing a person "with one visible eye" in a
frame that shows two adults and a child in a kitchen. The same request shape as U7, sent again on
2026-09-30 with our key:

| Request | Model | `prompt_tokens` | Answer |
|---|---|---|---|
| The U7 two-shape PNG (256×256, re-drawn), U7's prompt | `zai-org/GLM-5.3-Flash` | 37 | ❌ "Red blob top-left, dark green blob top-right, red blob bottom-centre, yellow blob bottom-right" |
| A 448×256 storyboard frame (kitchen, three people), "how many people…?" | `zai-org/GLM-5.3-Flash` | 31 | ❌ "no people… a dark scene… like stars in a night sky" |
| same frame at 1344 px (the original, 1.9 MB) and 448 px (0.18 MB) | `zai-org/GLM-5.3-Flash` | 31 | ❌ invented scenes at both sizes ("a conference room"; "eight young adults on a sofa"); the 448 px call took ~90 s, and 672 px calls timed out at 110 s |
| same frame | `deepseek-ai/DeepSeek-V4.1-Flash` | 238 | ✅ "three people… a man and a woman… a young girl watches from an open doorway" |
| same frame | `openbmb/MiniCPM-V-4_5` | 94 | ✅ three people, the girl at the door |
| same frame | `moonshotai/Kimi-K2.6` | 189 | ✅ three people, the girl peeking through the doorway |

**Verdict:** GLM-5.3-Flash on Token Factory now answers image requests **without receiving the image**:
a text-only prompt's token count, and a confident invented description. No error is returned, so
nothing upstream can tell. The audit would have judged made-up frames.

**Consequence:** `NEBIUS_MODEL_VISION` became `deepseek-ai/DeepSeek-V4.1-Flash` ($0.30 · $1.20,
3000 RPM; until 2026-10-17, § U8), the cheapest model that read both the U7 image and a real storyboard frame correctly.
Its structured output held on every describer call in T020's live runs (`json_schema`, no repair
needed). Option A is unchanged: only the describer's model moved. T049 should re-check whichever
describer is configured, since this changed silently between two dates.

### The vision decision

SPEC, README and the pitch said "a **Nemotron** vision auditor". That couldn't be true on Token Factory
as-is. Options, for the team to decide before T010 (`docs/design/verify.md`):

| | Option | Nemotron's role in the audit | Cost / effort | Risk |
|---|---|---|---|---|
| **A** | **Perceive + judge split** — a Token Factory VLM (GLM-5.3-Flash) describes the frame as structured JSON (who is in frame, count, framing, time of day, props); Nemotron compares that description to the shot spec and issues the verdict | **Nemotron makes every audit decision** | Two cheap calls per frame; no new infra | The VLM's description is a lossy middle step; audit accuracy is only as good as it |
| **B** | Self-host an NVIDIA VLM (e.g. Nemotron Nano VL) with vLLM on the same Nebius GPU as ComfyUI | Nemotron sees the image directly | New serving work on T003's box; GPU memory shared with ComfyUI | Schedule — this is new infrastructure in a 5-week project |
| **C** | A Token Factory VLM does the whole audit | None | One call per frame | "Nemotron vision auditor" becomes false; wording in SPEC/README/pitch must change |

**Decided 2026-09-28 (Katlego): A now, B as a stretch.** Build A for the deadline; try B only if
T003's GPU has headroom once US1 works. A keeps the claim honest in a narrower form — *"a vision
model describes each frame; Nemotron audits it against the script"* — needs no new infrastructure,
and makes the audit's reasoning inspectable, since the description is logged next to the verdict.

## U8 — An NVIDIA vision model (2026-10-17)

_Checked 2026-10-17 by Katlego (via Claude): the catalog (`GET /v1/models?verbose=true`, 28 models)
and one call._ NVIDIA released three Nemotron 3.5 models on 15 Oct: **Super VL** (120B, about 12B
active, text and images, 1M context), **Bolt 74B-A9B** and **Bolt E4B** (due 23 Oct). Only Super VL
is on Token Factory; the two Bolts are for local and edge hardware, so they don't fit a project
whose model calls must be Token Factory's.

| | `nvidia/Nemotron-3.5-Super-VL` | `deepseek-ai/DeepSeek-V4.1-Flash` (the describer until 17 Oct) |
|---|---|---|
| Modality | `text+image->text` | `text+image->text` |
| Context | 1,048,576 | 1,048,000 |
| Price per 1M tokens (in / out) | $0.30 / $0.90 | $0.30 / $1.20 |
| `supported_features` | `tools`, `reasoning` | none listed |
| Listed on Token Factory | 2026-10-12 | 2026-09-15 |

Neither lists `structured_outputs`, and DeepSeek has honoured our strict `json_schema` all the same
(T010 onwards), so Super VL's must be measured, not assumed.

**The probe** (one call, no `response_format`, thinking left to the model's default):
`docs/design/comic/the-red-kite-page-1.png`, "How many panels are on it, and what text is lettered
in the first speech bubble?" It answered **4 panels** and **"Come on. Come on, wind."**, which is
line 17 of `samples/the-red-kite.fountain` verbatim, in 3.6 s: 3,361 prompt tokens (3,314 of them the
image) and 395 completion tokens, **367 of them reasoning** (about $0.0014). So it receives images
on this host (GLM-5.3-Flash stopped doing so in September: § U7 re-check) and reads lettering, and
it thinks by default.

### U8 measured (2026-10-17, T105)

_Run by Katlego (via Claude) on Katlego's machine: today's `audit_frame` (as `python -m
app.verify.reaudit` runs it, nothing written, nothing drawn) on every stored attempt of the-red-kite
project `28a0476c` (2026-10-16, klein, 22 storyboard frames and 22 comic panels, all attempt 1).
The vision model and its thinking toggle are the only change between runs; the judge is the same
Nemotron Super. Four attempts at a time. About $0.5 of Token Factory for the three runs._

| | DeepSeek-V4.1-Flash (the describer then) | Super VL, thinking default | Super VL, `NEBIUS_VISION_THINKING=false` |
|---|---|---|---|
| Attempts, `ERROR`s | 44, 0 | 44, 0 (one schema answer repaired) | 44, 0 |
| Raw verdicts (pass / warn / fail) | 4 / 34 / 6 | 3 / 30 / 11 | 8 / 28 / 8 |
| Hosted verdicts (`drawn_sex,no_character`) | 4 / 40 / 0 | 3 / 41 / 0 | 8 / 36 / 0 |
| Hard checks failed | `unscripted_person` 5, `unscripted_object` 2 | `unscripted_person` 9, `setting` 1, `unscripted_object` 1 | `unscripted_person` 5, `setting` 2, `unscripted_object` 1 |
| `text_in_frame` warnings | 6 | 17 | 22 |
| Tokens (prompt + completion, judge included) | 333,931 (7,589 an attempt) | 399,137 (9,071): **1.20×** | 317,055 (7,206): **0.95×** |
| Reasoning tokens in that | 82,635 | 147,740 | 62,344 |
| Seconds an attempt, median / mean | 22.6 / 32.7 | 24.7 / 36.5 | 32.4 / 36.2: **1.43× / 1.11×** |

**Every attempt whose hard checks differ, looked at** (10 of 44; 5 more differ only between pass
and warn). The drawing first, then who was right:

| Attempt (shot) | The drawing | DeepSeek | VL default | VL thinking off |
|---|---|---|---|---|
| comic 1.1 (LERATO on the roof with the kite) | a short-haired child at street level, no kite: **wrong** | warns ✗ | `unscripted_person` ✓ | `unscripted_person` ✓ |
| comic 1.4 (roof) | Lerato at a roof parapet | ✓ | `setting` "interior" ✗ | `setting` "interior" ✗ |
| comic 2.2 (workshop) | Mokgosi and Lerato, right | `unscripted_person` ✗ | ✓ | ✓ |
| comic 4.1 (night street, torch) | Lerato with a torch, right | ✓ | `unscripted_person` ✗ | ✓ |
| storyboard 1.3 (roof) | Lerato, right | ✓ | `unscripted_person` ✗ | ✓ |
| storyboard 1.4 (roof, close-up) | Lerato under the eaves, likely exterior | ✓ | ✓ | `setting` "interior" ✗ |
| storyboard 2.5 (workshop) | Lerato, right | `unscripted_person`, `unscripted_object` ✗ | ✓ | ✓ |
| storyboard 3.1 (the kite high) | Lerato flying it, right | ✓ | `unscripted_person` ✗ | ✓ |
| storyboard 4.1 (night street) | Lerato with a torch, right | ✓ | `unscripted_person` ✗ | `unscripted_person` ✗ |
| storyboard 4.2 (night street) | Lerato, right | ✓ | `unscripted_person` ✗ | ✓ |
| **Right** | | **7 of 10** | **4 of 10** | **7 of 10** |

**Why they differ:** both models see the same child. Super VL often writes **"pigtails"** where the
script says "braids tied back", and the judge then refuses the match (`unscripted_person`); with
thinking off it writes "braided hair" more often. It also reads the scrawled signatures as text
(`text_in_frame`, a warning: 6 → 22) and twice called a rooftop "interior".

**Fit and translation** ([vision-model.md](design/vision-model.md) §8; Super VL is the target,
decided by Katlego on 2026-10-17, so the question is fit and how much carries over, not whether it
beats DeepSeek):
- **It fits, with thinking off:** 0 `ERROR`s; 0.95× the tokens; 1.43× the median seconds and 1.11×
  the mean (four at a time from South Africa, where uploads timed out and were retried for both
  models); and it shows no wrong frame DeepSeek withheld (the two DeepSeek withheld, comic 2.2 and
  storyboard 2.5, are right frames). **Thinking on doesn't fit:** 4 of 10 disputed checks right,
  1.20× the tokens.
- **What carries over**, Super VL with thinking off against DeepSeek, the same 44 attempts:

| Part of the audit | Agrees | What differs |
|---|---|---|
| Structured output (strict `json_schema`) | 44 of 44, 0 repairs | — |
| People described (how many) | 44 of 44 | — |
| The sex agent (T095) | 51 questions each; 48 of 48 answers on the same people the same | — |
| The presence agent (T099) | ran on 3 attempts against 2 | — |
| The judge's matches (person → character) | 36 of 44 the same | 4 real: Super VL right on 3 (comic 1.1, 2.2, storyboard 2.5), DeepSeek on 1 (storyboard 4.1: "pigtails", T108) |
| Setting | 42 of 44 | a flat roof read `interior` twice (T106) |
| Light, shot size | 37 of 44 each | soft checks only |
| Lettering against signature | `has_text` 33 of 44 | text entries 9 → 25, `text_in_frame` 6 → 22: signatures read as text (T107) |

- **Decision (Katlego, 2026-10-17): migrate.** The defaults are Super VL with thinking off (#192);
  T106, T107 and T108 adapt the three parts that differ; a held-out project (Tumo) checks that
  there is nothing else. Pitch and plan: [super-vl-migration.md](super-vl-migration.md).

**What this changes:** option B of [§ The vision decision](#the-vision-decision) (an NVIDIA model
that sees the frame) no longer needs a GPU of our own. **What T105 settled:** the describer was
DeepSeek-V4.1-Flash until T105 ([docs/design/vision-model.md](design/vision-model.md)) measured
Super VL on stored drawings with `python -m app.verify.reaudit` (above: the verdicts it changes,
looked at; schema failures; tokens and seconds an attempt, with thinking on and off), and the
defaults moved to Super VL on 2026-10-17 (#192).

### U8 held out: the-lighthouse-inspector (2026-10-17, T105's translation run)

_Run by Tumo (via Claude) on Tumo's machine, as Katlego asked on #192: `measure.py` (#192's
comment, unchanged) on every stored attempt of the-lighthouse-inspector, project `78f8735f`
(held out, 2026-10-14, 26 storyboard frames, all attempt 1), on main @ `abefcd6`. DeepSeek ran with
`NEBIUS_VISION_THINKING=false` too (main's default since #192; the-red-kite's DeepSeek column above
had it unset). The stored extraction predates T101, so the bare `FORTUIN` is still a sexless
character here. Every attempt has an eye verdict from the held-out run (`eval/frame-labels.json`)._

| | DeepSeek-V4.1-Flash | Super VL, `NEBIUS_VISION_THINKING=false` |
|---|---|---|
| Attempts, `ERROR`s | 26, 0 | 26, **1** (8.1: the describer's answer failed the schema, then its repair) |
| Raw verdicts (pass / warn / fail) | 2 / 19 / 5 | 5 / 16 / 4 (+1 error) |
| Hosted verdicts (`drawn_sex,no_character`) | 2 / 24 / 0 | 5 / 20 / 0 (+1 error, withheld) |
| Tokens (prompt + completion) | 173,890 | 149,618: **0.86×** |
| Seconds an attempt, median | 14.8 | 11.7: **0.79×** |
| Text entries more on Super VL | | 10 of 26 attempts (T107's pattern) |
| Setting differences | | none besides 8.1's error (no rooftops in this script) |

**Every attempt whose hard checks or hosted verdict differ (5 of 26), against the eye verdict:**

| Attempt | Eye verdict | DeepSeek | Super VL |
|---|---|---|---|
| 4.3 | right | warn | pass ✓ |
| 5.2 | right | warn | pass ✓ |
| 9.2 | right | `unscripted_object` ✗ (warn on the ladder) | pass ✓ |
| 7.5 (Mr. Fortuin drawn as an old woman) | **wrong** | the judge matched her as FORTUIN: warn, shown ✗ | the judge refused her (`unscripted_person`), the presence agent found her as FORTUIN: warn, shown ✗ |
| 8.1 (no rescue boat) | weak | `unscripted_person` (warn) | `ERROR`, withheld: a redraw |

**What carries over**, the rows of the-red-kite's table above, from the same two records (no new
run; 25 attempts, since 8.1 has no description on Super VL):

| Part of the audit | Agrees | What differs |
|---|---|---|
| Structured output (strict `json_schema`) | 25 of 26 | 8.1 failed the schema and its repair (the new item below) |
| People described (how many) | 25 of 25 | — |
| The sex agent (T095) | 24 questions each; 23 of 23 answers on the same people the same | — |
| The presence agent (T099) | found someone on 2 attempts against 0 | 7.3 and 7.5, the two judge differences below |
| The judge's matches (person → character) | 23 of 25 the same | both a match DeepSeek made and Super VL's judge refused, then the presence agent found: 7.3 (Ms. Naidoo drawn twice, weak; described as "an adult … in a suit jacket", no sex) and 7.5 (Mr. Fortuin as an old woman, wrong; FORTUIN found). The same outcome both ways |
| Setting | 25 of 25 | — |
| Light, shot size | 14 and 21 of 25 | soft checks only |
| Lettering against signature | `has_text` 19 of 25 | text entries more on 10 of 26 (T107) |

**What this adds to the-red-kite's findings:** nothing new among T106–T108's three items, and one
new item: **the describer's schema on Super VL**: 1 of 26 here (8.1), 7 of 109 on the labelled
frames below, against 0 of 44 on the-red-kite. Each is an `ERROR`: withheld, redrawn on the hosted
demo (a drawing and an audit spent). 7.5 is shown by both: with T101 (MR. FORTUIN gets "male" from
his title) and T102 (a found person is asked its sex), it is caught (T102's real-code measurement,
verify.md §3).

### U8 on the labelled frames (2026-10-17): 109 drawings judged by eye

_`eval/tools/score_labels.py` on all 109 frames of `eval/frame-labels.json` (11 scripts, judged by
eye on the days they were drawn: 57 wrong, 12 weak, 40 right), main @ `abefcd6` (so T095 and T099
run; T101–T104 are not on main yet), both with thinking off, the hosted ladder
`drawn_sex,no_character`. A frame is withheld when its laddered verdict is FAIL or `ERROR`._

| | DeepSeek-V4.1-Flash | Super VL |
|---|---|---|
| Wrong frames withheld (57) | **17** | 14 (one of them an `ERROR`) |
| Right frames withheld (40) | 3 | 5 (**4 of them `ERROR`s**) |
| Weak frames withheld (12) | 0 | 2 (both `ERROR`s) |
| `ERROR`s (the describer's schema, after its repair) | 0 | **7 of 109** (market-day 2.1, 3.2, 5.2; sipho-and-siphokazi 2.1; the-borrowed-bicycle 5.5; the-lighthouse-inspector 8.1; the-night-taxi 1.1) |
| Leaving the 7 out: wrong withheld (56) / right withheld (36) | 17 / 2 | 13 / 1 |
| `drawn_sex` faults (15) withheld | 9 | **10** (the sex agent: the-borrowed-bicycle 2.3 and 5.2 caught only by Super VL) |
| `absent` faults (8) withheld | **4** | 1 |

**Frames only one model withholds** (looked at, by their eye verdicts):
- **Only DeepSeek** (6 wrong, 1 right): final-whistle 2.3 (no crowd), 4.3 (Lindi, not Palesa),
  lost-property 7.4 (one man, no Tebogo), 9.6 (a split), the-bread-van 4.4 (three boys for Theo),
  the-lighthouse-inspector 7.5 (Mr. Fortuin as a woman), all through `no_character`; and
  final-whistle 1.4 (right, a false alarm). On Super VL the judge matches someone or the presence
  agent finds them, so the frame is shown.
- **Only Super VL**: the-borrowed-bicycle 2.3 and 5.2 (NALEDI drawn as a boy: `drawn_sex`), and the
  7 `ERROR`s.

**What this adds** (beside T106–T108):
1. **The describer's schema on Super VL:** 7 of 109 (6%) fail even after the repair; 0 on
   DeepSeek. Each withholds the frame (on the hosted demo, a redraw), and most land on right frames.
2. **Absent characters let through:** `no_character` withholds 1 of the 8 absent-character frames
   on Super VL against 4 on DeepSeek. The presence agent (T099) finds people more readily on Super
   VL, or the judge matches them; worth a look at those six frames' `found` answers, since T102
   and T104 (merged 18 Oct) build on the presence agent.
3. **The sex agent holds up:** 10 of 15 sex faults withheld against 9.

**One run is noisy at the level of a frame:** lighthouse 7.5 on DeepSeek was shown in the
`measure.py` run above and withheld (`no_character`) in this one, the same attempt and settings:
the judge isn't deterministic. Read single-frame differences as leads to look at, and the counts
over many frames as the measurement.

Raw: `eval/measurements/2026-10-17/` (both runs' per-frame results and logs, and the
lighthouse's `measure.py` records).

### U8 follow-ups: T106 and T107 (2026-10-18, Katlego)

The two describer items § U8 left on Super VL, measured on the-red-kite's same 44 stored attempts
with T105's `measure.py` (Super VL with thinking off, today's full `audit_frame`, writing nothing),
against 17 Oct's Super VL run:

| | 17 Oct | The wording only (#210, run 1) | Wording and the signature slot (run 2) |
|---|---|---|---|
| Rooftop 0.4, comic / storyboard | `interior` / `interior` (hard `SETTING` fail) | `exterior` / `exterior` | `exterior` / `unclear` (both pass) |
| Other settings changed | | none of 42 | none of 42 |
| `text` entries | 25 | 24 | **7** |
| `text_in_frame` frames | 22 | 21 | **5** (DeepSeek: 6) |
| Errors | 0 | 0 | 0 |

**The hand classification** of 17 Oct's 25 `text` entries, with each drawing looked at: 4 are
lettering in the scene ("SNAP." twice, "SLAP & NOPE.", a door's "1"), and 21 are the artist's corner
signature, or a reading of nothing visible ("K. K. K."). All 4 stay in `text` in both runs.

**What did it.** T106's sentence alone fixed the roof. T107's sentence alone moved nothing: Super
VL wrote the signature under `text` anyway. Giving the signature its own field, `signature_text`,
written before `text`, moved 22 signatures out of it. The schema's order is the order the model
writes in, and with `text` first it had already put the scrawl there. Three signatures still land
in both fields ("J. Eubred", "HATAP", "P-16"); that's a soft warning each.

**Not from these changes:** two new `unscripted_person` fails in run 2. On comic 0.4 the description
of Lerato is identical in all three runs and the judge refused it once; storyboard 2.1's "pigtails"
is T108's case. The judge never sees `text` or `signature_text`, only the people and objects lines
(`prompts.py`). Storyboard 4.2's `split_panels` is T104's layout agent, which 17 Oct's run predates.

Raw: `eval/measurements/2026-10-18-describer/` (both runs' records per attempt).

## U9 — Does the vision model see a body drawn wrong? (2026-10-18, T111)

**No.** Measured for T111 (limb-agent.md) on `nvidia/Nemotron-3.5-Super-VL`. The question was
the 14 Oct prototype's, unchanged (§6): per listed person, count heads, arms and legs, then
`normal`, `defect` (which) or `unclear`, and the hands. Each drawing was asked twice. The bar was
written before the run and confirmed by Katlego (§8). Pass or fail is judged on the base set;
the hunted drawings are reported apart.

**The labels** (`docs/design/limb-agent/labels.json`, Katlego by eye, every drawing shown alone):

| Pool | Normal | Defect | Unclear |
|---|---|---|---|
| Tumo's 109 labelled frames | 92 | 16 | 1 |
| T097's 14 Oct probe, 18 | 14 | 3 | 1 |
| Hunted: Claude's picks from the 1,382 drawings in the dev bucket | 15 | 29 | 4 |

The base set's 19 defects were named by no earlier label; Tumo's were about the script, not
anatomy. Extra arms and extra legs are the commonest (24 of the 42 faults named), then fused
bodies, two heads, missing limbs, twists and one deformed hand.

**The runs** (asks and drawings below count only ones Katlego labelled normal or defect):

| Run | Pool | Catches (bar ≥ 60%) | False alarms (≤ 2.5%) | Agreement (≥ 90%) | Errors (≤ 2%) |
|---|---|---|---|---|---|
| thinking off | base | **2/38 = 5.3%** | 0/198 = 0% | 117/117 = 100% | 0/234 = 0% |
| thinking off | hunted | 0/56 = 0% | 2/28 = 7.1% | 42/42 = 100% | 0/84 = 0% |
| thinking on | base | **0/26 = 0%** | 0/178 = 0% | 99/99 = 100% | **36/238 = 15.1%** |
| thinking on | hunted | 0/36 = 0% | 0/23 = 0% | 26/26 = 100% | **29/88 = 33%** |

By framing (base, thinking off): wide 2/16, medium 0/22; the close-up shots had no defects. Six
base drawings have nobody in their stored description, so they were never asked. Four of the 66
fresh descriptions (thinking off) looped to the token limit, T109's problem; those drawings got
no limb question.

**What the model does:** it does not count; it fills in a template. On drawings labelled
`defect`, 274 of 276 body answers (thinking off) were "1 head, 2 arms, 2 legs, normal". That
includes the man with three arms on the rooftop, the diving girl with three legs, and both boys
drawn with two heads. Its one base catch named `misplaced_limb` on a drawing labelled
`missing_limb`, while still counting 2 arms and 2 legs. Its two hunted false alarms are real
oddities Katlego didn't count as a body fault: a giraffe's neck that seems to grow out of a
woman's head ("extra arm"), and a hand floating in the air ("deformed hand"). The perfect
agreement is the same template answer twice. With thinking on, the answers are about 10 times
longer (389,894 completion tokens against 38,790), a quarter of asks spend the whole 4,096-token
budget thinking and return nothing, and not one answer names a defect.

**Decision (limb-agent.md §8): no `LIMBS` check.** This is the same result as DeepSeek-V4.1-Flash
on 14 Oct (verify.md §3, *The head agent*). Two vision models, three runs: the question doesn't
work, whatever the model or thinking setting. The labels and the hunt stay as a test set for any
later try, such as the research's box-per-defect prompt or a dedicated detector (limb-agent.md
§10).

**Cost:** run 1 used 511,456 + 38,790 tokens for 318 asks, plus 121,538 + 17,818 for 57
descriptions. Run 2 used 414,384 + 389,894 for 261 asks, plus 129,182 + 29,415 for 61
descriptions. Both runs were announced on #208 first, one process each.

Raw: `eval/measurements/2026-10-18-limbs/` (both runs' answers per drawing, and their logs).

## Follow-ups this creates

- ✅ T004: `json_schema` strict by default; thinking off by default on the fast tier; trace
  `reasoning_tokens`; honour `Retry-After` and the ratelimit headers; one base URL.
- U6: still open (T006 shipped `temperature` 0.0; grounding.md §10).
- ✅ T010: build `verify.md` on option A (perceive with `NEBIUS_MODEL_VISION`, judge with Nemotron).
- ✅ (done 2026-09-30) SPEC, README and `docs/submission/about.md` say "Nemotron vision auditor": correct them to the
  option A wording, in their own PR.
- U4: re-read the limits now the Builder Program credit has landed (not done).
