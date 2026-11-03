# Design — `eval` (the numbers in the README)

**Status:** built (T032: #33 design, #34 code); T049 deferred 2026-10-12 · **Owner:** Katlego (Claude) · **Tasks:** T032, T049 · **Spec:** [SPEC.md](../../SPEC.md)
§ Success criteria ("Measured: faithfulness, recall and frame-audit accuracy numbers in the README")

---

## 1. What this covers

Repeatable measurements on three of the self-written samples (`lost-property`,
`sipho-and-siphokazi`, `the-red-kite`, T031; `samples/` holds 13 since T090), run on the real
Token Factory account and committed with the date, the model and the command that produced them:

- **Extraction and shot planning (T032):** grounding faithfulness and recall (grounding.md §4), and
  for the shot plan: every element in exactly one shot, and every kept quote and every shot's
  `source` re-checked in code as verbatim script text. Several runs per sample, because Lightning
  at temperature 0 still varies run to run (samples/README.md).
- **Frame-audit accuracy (T049):** the audit's precision and recall on a labelled set of rendered
  frames, including frames with a deliberately injected extra person or object (verify.md §8, §9).
  Was blocked on T026 (renders were to need T003's GPU); fal.ai draws them since 2026-10-09.
  **Deferred 2026-10-12** (TASKS T049): #106/#107 built it on the Workers AI renderer, since dropped.
  The audit is scored instead on 109 hand-labelled fal frames ([eval/audit-mistakes.md](../../eval/audit-mistakes.md),
  `eval/tools/score_labels.py`). Only T049's contract is kept here.

**Not covered:** the README's prose (T033); costs in dollars (tokens are recorded; prices change);
any copyrighted script, ever.

## 2. Reference material

| Kind | Where |
| --- | --- |
| Metric definitions | grounding.md §4 (faithfulness) and `GroundingReport` §6 (recall), shots.md §9 (partition), verify.md §9 (accuracy) |
| Inputs | `samples/*.pdf` (T031); `extract` (grounding.md §6), `plan_shots` (shots.md §6) |
| Existing one-run CLIs | `app.grounding.run`, `app.shots.run` (same calls; eval repeats them and aggregates) |
| Previous numbers | samples/README.md § Live runs (one run each, T039, T048) |

## 3. Domain model

```mermaid
classDiagram
    class EvalRun {
        +str sample
        +int run
        +str|None error
        +float faithfulness
        +int entities_grounded
        +int entities_proposed
        +int quotes_located
        +int quotes_proposed
        +float recall
        +int cues_found
        +int cues_total
        +int shots
        +bool partitioned
        +int ungrounded_kept
        +int names_dropped
        +int ranges_repaired
        +int tokens_in
        +int tokens_out
        +float seconds
    }
    class SampleSummary {
        +str sample
        +int runs
        +int failed
        +Stat faithfulness
        +Stat recall
        +Stat shots
        +bool always_partitioned
        +int ungrounded_kept
    }
    class Stat { +float mean +float min +float max }
    class EvalReport {
        +str date
        +tuple~str~ models
        +str command
        +tuple~EvalRun~ runs
    }
    EvalReport --> EvalRun
    SampleSummary --> Stat
```

- **`EvalRun`** is one `extract` + `plan_shots` over one sample. A run that raises
  `ExtractionError` / `ShotError` / `LLMError` is kept with `error` set (its message) and zeroed
  numbers, and is **counted** in `failed`, never silently dropped.
- **`ungrounded_kept`** re-checks Non-negotiable I in code, independently of the filter: the number
  of kept quotes whose `text` is not inside their `span`'s lines (`normalize_for_grounding`), plus
  shots that don't cite exactly what they cover. A shot with elements cites them when its `source`
  is `"\n".join(e.text for e in covered)` (planner, shots.md), its `span` runs from the first
  covered element's start to the last one's end, and each covered element's text normalises to its
  own span's lines (script.md §3). A shot with **no** elements (the establishing shot of a
  heading-only scene) cites the heading: `source == scene.heading` and `span` is the heading line.
  It must be 0; anything else is a bug, and the eval exits non-zero.
- **Field mapping:** `cues_found` is `GroundingReport.cues_found_by_model`; `tokens_in` /
  `tokens_out` are extraction's plus planning's `prompt_tokens` / `completion_tokens`
  (`reasoning_tokens` is left out: thinking is off on the fast tier, llm.md).
- **`names_dropped`** = the planner's `characters_dropped + props_dropped` (names the model put in a
  shot that aren't extracted for that scene; dropped by code, shots.md §4).
- **`SampleSummary`** is computed from the runs that didn't fail. `Stat` is mean / min / max.

## 4. Flow

```mermaid
sequenceDiagram
    participant C as tools.evaluate (CLI)
    participant P as parse_pdf
    participant G as extract
    participant S as plan_shots
    participant F as eval/results/*.json
    C->>P: samples/<name>.pdf
    loop runs × samples (sequential: no rate-limit surprises)
        C->>G: model, screenplay
        G-->>C: Extraction
        C->>S: model, screenplay, extraction
        S-->>C: ShotPlan
        C->>C: EvalRun (re-check spans in code)
    end
    C->>F: EvalReport as JSON
    C-->>C: print the summary table (markdown)
```

The committed `eval/README.md` table is the printed table, pasted with its date and command. A gate
test recomputes the table from the committed JSON and compares, so the README can't drift from
the data. The gate never calls a model.

## 5. State

None: a run is a pure function of the sample and the model's answers. Results are append-only
files named by date.

## 6. Contracts

```python
# services/api/tools/evaluate.py
@dataclass(frozen=True) class EvalRun: ...          # §3 fields, in that order
@dataclass(frozen=True) class Stat: mean: float; min: float; max: float
@dataclass(frozen=True) class SampleSummary: ...    # §3 fields
@dataclass(frozen=True) class EvalReport: date: str; models: tuple[str, ...]; command: str; runs: tuple[EvalRun, ...]

def check_run(screenplay: Screenplay, extraction: Extraction, plan: ShotPlan, *, sample: str, run: int, seconds: float) -> EvalRun: ...  # pure
def summarise(runs: Sequence[EvalRun]) -> list[SampleSummary]: ...   # pure; one per sample, in first-seen order
def table(report: EvalReport) -> str: ...                            # pure; the markdown table eval/README.md carries
def to_json(report: EvalReport) -> str: ...; def from_json(text: str) -> EvalReport: ...  # round-trip
async def main(argv: list[str]) -> int: ...  # [--runs N (default 5)] [--out PATH] [sample ...]; exit 1 if any ungrounded_kept > 0
```

`cd services/api && uv run python -m tools.evaluate --runs 5` runs all three samples and writes
`eval/results/extraction-<YYYY-MM-DD>.json` (a second run the same day gets `-2`, never
overwrites).

**The table** (one row per sample, then a pooled row over all runs):

| Sample | Runs (failed) | Faithfulness mean (min–max) | Recall mean (min–max) | Shots mean (min–max) | Every element once | Ungrounded kept |

Pooled faithfulness is entities grounded ÷ entities proposed over every run (micro), not a mean of
means; same for recall over cues.

**T049 (deferred) report shape:** per frame `{frame, shot, label: "correct" | "injected_person" |
"injected_object", verdict, failed_checks}`; precision and recall of FAIL against the injected
labels, and the false-FAIL rate on correct frames (verify.md §10). Same file and table conventions,
`eval/results/audit-<date>.json`.

## 7. Structure

| Path | New/changed | What |
| --- | --- | --- |
| `services/api/tools/evaluate.py` | new | §6 |
| `services/api/tests/tools/__init__.py` | new | package marker, as `tests/samples/` has |
| `services/api/tests/tools/test_evaluate.py` | new | pure functions; the README table equals `table(from_json(latest))` |
| `eval/README.md` | changed | what is measured, the command, the latest table, what the numbers don't show |
| `eval/results/extraction-<date>.json` | new | raw runs |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Runs per sample | 5, reported with min–max | 1 run: the T039 numbers moved 0.625 → 0.143 between two runs of the same sample |
| Where the runner lives | `services/api/tools/` (like `build_samples`) | a separate `eval/` package: it would need its own env to import `app` |
| Re-check grounding | in the eval, in code, independent of the filter | trusting `GroundingReport`: the eval would then measure the filter with itself |
| Failed runs | counted and shown | dropped: hides the case a judge most needs to see |
| Gate | recomputes the table from JSON, offline | runs the eval: costs credit and isn't deterministic |

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none.

## 9. How this is verified

- `check_run` on hand-built extractions and plans: a quote moved to the wrong span and a shot
  whose `source` was edited or whose `span` was moved each count as `ungrounded_kept`; a
  heading-only scene's establishing shot (no elements, cites the heading) does not; an
  unpartitioned plan reads `False`.
- `summarise` / `table` on fixed runs: mean/min/max, a failed run excluded from stats but counted,
  pooled micro averages.
- `to_json` / `from_json` round-trip; the committed README table equals the table recomputed from
  the newest committed JSON.
- Live: `uv run python -m tools.evaluate --runs 5` on the real account, results committed.

## 10. Open questions

- [ ] A target bar for faithfulness / recall: SPEC.md open question 5 asks the same for audit
  accuracy. Reported without a bar until the team sets one.
