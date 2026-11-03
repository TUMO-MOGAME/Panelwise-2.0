# Measurements of 2026-10-15/16 (T101–T104), raw

The scripts and their raw output, as run on Tumo's machine (the API container, the stored runs of
11 scripts, the newest run of each title). Each paper's summary is in its design doc and in
[docs/learning-log.md](../../../docs/learning-log.md) (L015, L022); [eval/audit-mistakes.md](../../audit-mistakes.md)
says how they fit together. Paths in the scripts (`/work`, `/tmp`) are the container's.

| Script | Measures | Cost | Output here |
|---|---|---|---|
| `dupes2.py` | T101: character pairs where one name's words are a subset of another's, every stored extraction | free | (in grounding.md §3: only the lighthouse) |
| `proto_fold.py` | T101: `ground` replayed with and without a prototype fold, 30 extractions | free | (grounding.md §3: 1 changed) |
| `proto_found_sex.py` | T102 prototype: the presence agent on the 77 frames it runs on, then the sex question on each found person | Token Factory | `proto_found_sex.out`: 36 asked, 2 flagged, 6 empty answers at 1,024 tokens |
| `real_t102.py` | T102's real code (the branch's `app/` mounted), the lighthouse re-grounded with T101's names | Token Factory | `real_t102.out`, `real_t102_results.json`: 4 frames fail `drawn_sex`, 1 of 37 empty at 4,096 |
| `proto_twice.py` | T104: the layout question on the 332 attempts with two or more people | Token Factory, 456,411 tokens | `proto_twice.out`, `proto_twice_answers.json` (every answer) |
| `veto_check.py` | T104: the matched-people veto on each one-picture copy flag, from the stored judgements | free | in verify.md §3: 2 of 8 vetoed |
| `real_t104.py` | T104's real `frame_layout` + `run_checks` replayed on the stored answers | free | verify.md §3: `split_panels` 23, `drawn_twice` 6 |
| `fetch_shots.py`, `twice_sheets.py` | pull stored drawings (by `script:shot`) and make contact sheets to look at | free | |

To repeat one on another vision model, run it with `NEBIUS_MODEL_VISION` (and
`NEBIUS_VISION_THINKING=false` for Super VL) set in the container's environment: each takes the
model from the settings.
