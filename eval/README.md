# `eval`

Measured numbers for the README and the Devpost story, on self-written samples in
[`samples/`](../samples/README.md) (never a copyrighted script): the extraction on three of them,
the frame audit on 109 labelled drawings of 11 scripts. Design:
[docs/design/eval.md](../docs/design/eval.md).

| Measure | Task | Status |
| --- | --- | --- |
| Extraction faithfulness and recall, shot-plan partition, grounding re-checked in code | T032 | below |
| Frame-audit accuracy (precision, recall, false-FAIL rate on labelled renders) | T049 | deferred 2026-10-12; the 109 labelled frames score the audit instead: [audit-mistakes.md](audit-mistakes.md), [measurements/t124/rescore-2026-10-20/](measurements/t124/rescore-2026-10-20/) (Super VL, today's hosted ladder: wrong 38 of 57 withheld, right 1 of 40) |

## Extraction and shot planning (T032)

Each run parses a sample, extracts its grounded entities and plans its shots on the real Token
Factory account, the same calls the pipeline makes. Five runs a sample, because Nemotron at
temperature 0 still varies run to run.

```bash
cd services/api && uv run python -m tools.evaluate --runs 5
```

**2026-10-01**, `nvidia/Nemotron-3_5-Lightning` (thinking off), all 15 runs in
[`results/extraction-2026-10-01.json`](results/extraction-2026-10-01.json):

| Sample | Runs (failed) | Faithfulness mean (min–max) | Recall mean (min–max) | Shots mean (min–max) | Every element once | Ungrounded kept |
| --- | --- | --- | --- | --- | --- | --- |
| `lost-property` | 5 (0) | 0.877 (0.808–0.962) | 0.909 (0.909–0.909) | 50.2 (50.0–51.0) | yes, every run | 0 |
| `sipho-and-siphokazi` | 5 (0) | 0.939 (0.867–1.000) | 1.000 (1.000–1.000) | 31.0 (29.0–32.0) | yes, every run | 0 |
| `the-red-kite` | 5 (0) | 0.918 (0.714–1.000) | 1.000 (1.000–1.000) | 21.8 (21.0–22.0) | yes, every run | 0 |
| **All** | 15 (0) | 0.898 (246/274) | 0.944 (85/90) | 515 in all | yes, every run | 0 |

How to read it:

- **Faithfulness** is the share of the entities the model proposed whose name and every quote
  were found verbatim in the script (grounding.md §4). Below 1.0 means the model proposed
  something the script doesn't say — a paraphrased quote, a name the script never writes — and the
  grounding filter **dropped what didn't ground** (the unlocated quotes, or the whole entity when
  its name or every quote is missing). It measures the model, not what reaches a panel.
- **Ungrounded kept** is what reaches a panel: every kept quote and every shot's cited text,
  re-checked here in code, independently of the filter, against the script lines its span names.
  It is 0 in every run; the eval exits non-zero if it ever isn't (Non-negotiable I).
- **Recall** is the share of speaking characters the model found itself (the parser's cues add the
  rest, so no speaker is ever lost from the plan). `lost-property`'s 10/11 is the station
  ANNOUNCER, a V.O. voice the model doesn't list (samples/README.md).
- **Every element once**: every action paragraph and speech of every scene is in exactly one shot,
  so no line of dialogue is left without a panel.
- Pooled (**All**) faithfulness and recall are micro averages over every run (246 of 274 entities
  grounded; 85 of 90 speaking characters found), not a mean of means.
- Cost: 146,074 tokens in and 56,887 out over the 15 runs (about 9,700 in and 3,800 out a run, 5–18
  s each).

The gate's `tests/tools/test_evaluate.py` recomputes this table from the newest committed result
and fails if they differ. A new run writes a new dated file; results are never overwritten.

### Panelwise 2.0: on-device, through QVAC

**2026-11-03**, Qwen3 1.7B Q4_0 (`fast`) and Qwen3 4B Q4_K_M (`reasoning`) through `qvac serve --openai`
on a laptop (Intel Core Ultra 7 265U, 32 GB, Intel iGPU over Vulkan), no network call. One run a
sample, so this is a first look, not yet a five-run figure. The run is in
[`results/extraction-qvac-2026-11-03.json`](results/extraction-qvac-2026-11-03.json):

| Sample | Runs (failed) | Faithfulness mean (min–max) | Recall mean (min–max) | Shots mean (min–max) | Every element once | Ungrounded kept |
| --- | --- | --- | --- | --- | --- | --- |
| `lost-property` | 1 (0) | 0.952 (0.952–0.952) | 0.909 (0.909–0.909) | 106.0 (106.0–106.0) | yes, every run | 0 |
| `sipho-and-siphokazi` | 1 (0) | 0.400 (0.400–0.400) | 0.250 (0.250–0.250) | 54.0 (54.0–54.0) | yes, every run | 0 |
| `the-red-kite` | 1 (0) | 1.000 (1.000–1.000) | 0.667 (0.667–0.667) | 43.0 (43.0–43.0) | yes, every run | 0 |
| **All** | 3 (0) | 0.811 (30/37) | 0.722 (13/18) | 203 in all | yes, every run | 0 |

Against Nemotron above: **the grounding guarantee held** (0 ungrounded kept: the code-side check
drops whatever the small model makes up), but the small models find fewer of the speaking
characters (recall 0.72 against 0.94), fall apart on `sipho-and-siphokazi` (0.40 / 0.25), and
plan about twice as many shots. Each sample took 3.5–10 minutes against Nemotron's 5–18 s.
