# Disclosure: Panelwise and FrameFlow

The hackathon rules ask projects that existed before the submission period (26 August 2026) to
explain what was significantly updated during it. This is that explanation.

## What existed before 26 August 2026

Panelwise builds on **FrameFlow**, a private, never-published project by the same team
(Katlego Tlhapiso and Tumo Mogame). Its first commit is dated 14 June 2026.

Before 26 August, FrameFlow was a **text-only pre-production pipeline built on IBM watsonx / Granite
and IBM Docling**. It had:

- screenplay parsing (via IBM Docling);
- LLM scene breakdowns, shot suggestions and casting profiles;
- a Day-Out-of-Days schedule and a film-commission compliance report;
- a first version of the grounding filter and faithfulness score;
- web and mobile scaffolds with auth.

It had **no image generation, no storyboards, no portraits and no comic output**, and it ran on no
open models.

## What changed in FrameFlow between 26 August and the start of Panelwise

197 commits: 322 files changed, +30,956 / −4,747 lines.

| Area | Change |
| --- | --- |
| Model layer | IBM watsonx / Granite removed; replaced with a provider seam for OpenAI-compatible endpoints |
| Parsing | IBM Docling removed; replaced with a pdfplumber parser |
| Grounding | Extraction chunked on scene boundaries; verbatim source spans; recall metric; line-break fixes |
| **Storyboards** | **New:** one frame per shot, selectable styles, scene PDF (6–13 September) |
| Image generation | **New:** provider chain (ComfyUI, A1111, Gemini), record/replay cache |
| Cast portraits | **New:** grounded reference portraits as polled jobs |
| Infrastructure | Asset store, lineage, budget ceilings, tracing |

## What is new in Panelwise (during the submission period)

Panelwise is a **new repository** focused on storyboards and comics. It ports only the pieces the
storyboard pipeline needs, and drops scheduling, compliance, auditions, voice and mobile.

| Area | New work |
| --- | --- |
| Models | NVIDIA Nemotron on Nebius Token Factory for every model call, with fast, reasoning and vision tiers (Nemotron 3.5 Super VL sees the frames since 17 Oct) |
| Frame audit | Nemotron 3.5 Super VL describes each frame without seeing the shot, Nemotron Super audits the description against its shot spec, the frame is re-rendered on mismatch, and every verdict is logged |
| Comic mode | Panel layout by story beat, speech bubbles from linked dialogue, lettering, comic page export |
| Character consistency | Each character's look drawn from the script's own words in every frame prompt (T079); reference portraits cut 2026-10-19, never built (T025) |
| Rendering | FLUX.2 [klein] 4B on fal.ai (FrameFlow rendered on CPU); ComfyUI on a Nebius GPU cut 2026-10-19, never built (T003) |
| Evaluation | Benchmarks for faithfulness and frame-audit accuracy |

## Code ported from FrameFlow

Each ported module is listed here with the FrameFlow file it came from and whether it predates
26 August. Anything marked *pre-26 Aug* is earlier work, not hackathon work.

| Panelwise module | Ported from (FrameFlow) | Origin |
| --- | --- | --- |
| `services/api/app/llm/client.py` | `services/api/app/services/openai_compat.py` (retry on 429/5xx with backoff; the reasoning-but-no-content error) | 28 Aug 2026 (`dceba8d`, T257), during the submission period. Rewritten for Panelwise: async, Nebius-only, three tiers, `Retry-After`, thinking toggle, `<think>` stripping, usage with reasoning tokens |
| `services/api/app/script/parser.py` | `services/api/app/services/screenplay_parser.py` (pdfplumber layout text, margin classification, heading and furniture patterns) | 26 Aug 2026 13:02 PT (`c796f8e`, after the 09:00 PT start), during the submission period. Rewritten: ordered elements with page + line spans, wrapped lines joined, real pages, no invented `DAY`, heading-anchored margin, cue column, `EXT/INT`; T039: `INT./EXT.`, 12 pt layout rows, the time of a two-dash heading, wrapped parentheticals |
| `services/api/app/script/scene_time.py` | `services/api/app/services/scene_time.py` (absolute/relative times) | 7 Sep 2026 (`72a549c`), during the submission period. Now a pure function over parsed scenes (no DB) |
| `services/api/app/script/speakers.py` | `services/api/app/services/dialogue_linker.py` (`normalise`, `match_speaker`) | 10 Sep 2026 (`611412e`), during the submission period. Matching only; DB linking not ported |
| `services/api/app/grounding/text.py` | `services/api/app/services/grounding.py` (`normalize_for_grounding`) | 26 Aug 2026 16:45 PT (`79621d0`), during the submission period. Ported as is; new: locating a quote inside one element to get its span, and (T039) stripping a speech's own cue header from a dialogue quote |
| `services/api/app/grounding/extract.py` | `extraction_service.py`: `chunk_by_scene`, `merge_entities` | 29 Aug 2026 (`ae18e81`, T286), during the submission period. Rewritten: chunks of parsed scenes, concurrent, fail-loud; names + quotes only (FrameFlow's age/gender/role fields dropped) |
| `services/api/app/grounding/filter.py` | `extraction_service.py::validate_entity_grounding` (28 Aug, `a520945`), `governance_service.py::compute_recall` (29 Aug, `990f6ce`), `compute_faithfulness` | The filter and recall: during the submission period. **`compute_faithfulness` predates it** (20 Jun 2026, `7d832e3`, *pre-26 Aug*). Rewritten here: per-quote filtering with located spans, cue-based recall, heading locations, cue backfill |
| `services/api/app/shots/planner.py` | `services/api/app/services/shot_service.py` (the per-scene shot-list call and the camera vocabularies; passing the time of day explicitly) | The shot-list call and vocabularies **predate the submission period** (20 Jun 2026, `bc51a18`, *pre-26 Aug*); the explicit time of day is from 7 Sep 2026 (`72a549c`). Rewritten here: shots cover numbered script elements (every element in exactly one shot, ranges normalised), only extracted characters and props present in the scene, spans and verbatim source per shot, no free-text frame description, no hard-coded fallback shots, no Redis cache |
| `services/api/app/storyboard/prompt.py` | `services/api/app/services/storyboard_service.py` (`build_prompt`: comma phrases with the medium first, `_ANGLE_WORDS`, `_setting`'s "inside/outside/at <place>", the resolved clock) | 6 Sep 2026 (`94881cf`, the framing words) and 13 Sep 2026 (`234c15e`, the setting and the medium-first order), during the submission period. Rewritten: a tuple of parts each tagged with its source span, script text only from this shot's heading and covered action lines, names redacted, a figure count from who the covered lines show, a word budget that only drops or cuts script words; the free-text description and its 400-character scene fallback, the movement words and the `classic` prompt are not ported |
| `services/api/app/storyboard/styles.py`, `styles/{clean,ink,pencil}.toml` | `services/api/app/services/storyboard_styles.py` (the `clean`, `ink` and `pencil` styles, their media, emphasis and shared finish) | 13 Sep 2026 (`234c15e`), during the submission period. Rewritten: one TOML file per style, validated at start-up, a public/private split by directory; `classic` and the `fast` draft mode are dropped |
| `services/api/app/storyboard/document.py` | `services/api/app/services/storyboard_document.py` (A4 portrait, two 16:9 frames a page with the shot's line under each) | 7 Sep 2026 (`72161ab`, the scene PDF; `388200f`, the width that fits two a page), during the submission period. The layout idea only, rewritten with Pillow and Courier Prime: every source line verbatim, never cut or folded; the page/line span on every block; withheld and failed cards; a block continued across pages; built from the frames rows and stored by a document key |
| `services/api/app/storyboard/workflow.py` (`postprocess`) | `services/api/app/services/image_postprocess.py::storyboard_grayscale` (grayscale, then `autocontrast(cutoff=0.5)`, as a pixel pass because SDXL-Turbo tinted pencil frames sepia) | 13 Sep 2026 (`234c15e`), during the submission period. Ported as the style's `grayscale` pass after `fit`; FrameFlow's `face_crop` (for IP-Adapter references) is not ported |
| `services/api/app/llm/structured.py` | `services/api/app/services/llm_provider.py::structured_chat` (strict `json_schema` + one repair retry) | 28 Aug 2026 (`dceba8d`, T261), during the submission period. Rewritten: async, schema inlined in the system prompt, returns the answering model and usage |
