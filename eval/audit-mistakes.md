# What each model got wrong, what fixed it, and how to check it again

**For:** Katlego, and anyone changing a model (the Super VL migration, T105, done 2026-10-17; its
re-score is under *The baseline*) · **From:** Tumo (via
Claude), 2026-10-17 · **The full record:** [docs/learning-log.md](../docs/learning-log.md) (L001–L023,
one entry per lesson, with its numbers) and the run reports in [eval/runs/](runs/README.md).

This page is the index: every mistake we found in the frames, by the model that made it, what we
changed, what that measured, and which labelled frames test it again. The point is that a new model
(Super VL for the describer and the agents) can be put through the **same frames with the same
verdicts**, so "it fits" means the same thing it meant for DeepSeek.

## The tools

| File | What it is |
|---|---|
| [frame-labels.json](frame-labels.json) | **109 stored drawings we looked at by eye**, each `right`, `weak` or `wrong` with its faults (`drawn_sex`, `absent`, `split_panels`, `drawn_twice`, `extra_person`, `setting`, `age`, `missing_prop`, `missing_action`, `empty_frame`, `unclear_sex`) and where the verdict came from. 57 wrong, 12 weak, 40 right, across 11 scripts. Made by [tools/make_labels.py](tools/make_labels.py) |
| [labelled/](labelled/) | Everything those frames need to be audited anywhere: per script, the stored project's id, screenplay, extraction and plan, and per labelled attempt its drawing's Storage path, seed and the audit stored then (DeepSeek's). Made by [tools/export_labelled.py](tools/export_labelled.py) from Tumo's local database |
| [tools/score_labels.py](tools/score_labels.py) | **The scorer.** Re-audits every labelled frame with this process's settings (the vision model, thinking, the ladder) and counts: wrong frames caught or missed, right frames withheld (false alarms), and per fault which checks fired. `--stored` scores the stored audits for free |
| [measurements/2026-10-16/](measurements/2026-10-16/) | The raw logs and the scripts of the T101–T104 measurements below |

The drawings themselves are in Supabase Storage (`frames/<hash>.png`, the dev bucket); the scorer
reads them with the API's own Storage settings. Nothing is written and nothing is drawn.

### Redo it on a new model

```bash
# in the API container, the repo mounted at /work (or copied in)
python /work/eval/tools/score_labels.py /work --stored                     # the "before": free
NEBIUS_MODEL_VISION=nvidia/Nemotron-3.5-Super-VL NEBIUS_VISION_THINKING=false \
  python /work/eval/tools/score_labels.py /work --json /work/super-vl.json  # the "after"
```

A re-run costs one description, one judgement and the agents' questions per frame: about
4,000–6,000 Token Factory tokens a frame, so about 500,000–650,000 for all 109 (roughly $0.25).
`--script <title>` runs one script. Then look at every frame whose result differs (the scorer prints
one line per frame; pull a drawing with [measurements/2026-10-16/fetch_shots.py](measurements/2026-10-16/fetch_shots.py)).

**The baseline** (2026-10-17, `--stored`, the ladder `drawn_sex,no_character`): of 57
wrong frames 15 are withheld, of 40 right frames 14 are withheld. Most stored audits predate the
agents (T095–T104), so this is the audit of the day each frame was drawn, not today's: a re-run with
DeepSeek is the fair "before" for Super VL.

**After** (2026-10-20, the T109 re-score on Super VL,
[measurements/t124/rescore-2026-10-20/](measurements/t124/rescore-2026-10-20/)): run with
`drawn_twice` on the ladder, 43 of 57 wrong and 7 of 40 right withheld; on today's hosted ladder
`drawn_sex,no_character,split_panels` (`drawn_twice` warns since 2026-10-20), **38 of 57 wrong
withheld, 1 of 40 right, 0 of 12 weak**.

## The mistakes, by the model that made them

Each row: what went wrong, an example frame (in the labels), the cause, what we did, and what it
measured. **Re-check** says what to score on a new model.

### The image model (FLUX.2 [klein] on fal.ai): what gets drawn

| # | Mistake | Example | Cause | Fix | Measured | Re-check on a new vision model |
|---|---|---|---|---|---|---|
| L001, L002, L018, L023 | A girl drawn as a boy (and the other way) | the-borrowed-bicycle 1.1–5.2 (NALEDI), sipho 2.1 a2 (MAMA THEMBI as a man) | the prompt had no sex: the extraction found none | the sex from the script: pronouns, titles, nouns, a next-sentence He/She, a Her/His (T079, T082, T088, T091, T096, T100); the **sex agent** withholds a frame drawn as the other sex (T095); a found person is asked too (T102) | sex agent prototype 175 asked, 12 flagged, all real, 0 false alarms; T102 real code on 77 frames: 4 flagged, 3 plainly real, 1 arguable | fault `drawn_sex` (15 frames): caught by `drawn_sex`, not by an accident of another check |
| L015, T104 | A strip of panels instead of one picture | lost-property 11.5 (all 3 attempts), the-red-kite 5.2 (shown) | klein lays out storyboard strips; fal's klein takes no negative prompt | the **layout agent** (T104): `split_panels` (hard, on the hosted ladder) | 23 flagged on 332 attempts, all real | fault `split_panels` (23): caught by `split_panels`; the describer must still list both halves' people |
| L022, T104 | One person drawn twice in one picture | the-night-taxi 1.4 (THABO three times), the-red-kite 4.1 | the same; often a sequence of actions drawn at once | the layout agent: `drawn_twice` (hard; warns on the hosted ladder), vetoed when the two are two known characters | 8 flagged, 6 real; after the veto 5 real + 1 wrong frame anyway | fault `drawn_twice` (8): lighthouse 4.2 and 7.3 are **missed** (the two women's hair differs) |
| L020 | Extra people: klein fills places with shoppers, passengers | market-day (every shot) | places drawn as they look | `unscripted_person` warns instead of withholding (T094 ladder); a person must trace to an action line (T084) | market-day 0 of 15 → 16 of 17 shown, none wrong in sex or age | fault `extra_person`: warned, never withheld (by design) |
| L016 | An action given to the wrong person ("He salutes" drawn on Theo) | the-bread-van 5.3 | names become "a person" and the pronoun's owner isn't drawn | T093: a He/She with no one drawn is the one cast person of that sex | 4 shots now draw the right person | (prompt side; no vision check) |
| L004, L014 | Lettering the script didn't write | many signs and hulls | klein paints words and can't spell | `text_in_frame` warns (T089); signatures `signature` (T077) | every withheld-by-lettering frame looked at: none wrong for that | **T107**: Super VL reads signatures as lettering (warnings 6 → 22 on the-red-kite) |
| L008 | The prompt's word budget cut the characters' action | | cut from the end | open | | |
| L013, L003, L005 | The place's own things (bread in a bakery, a van's dashboard) failed as unscripted | the-bread-van | food and vehicles were never set dressing | T083/T086: what the scene names is scripted; a vehicle scene's parts are the place | food 26 → 0, vehicle 14 → 8 failures | fault-free right frames stay shown |

### The extraction (Nemotron 3.5 Lightning): who is in the script

| # | Mistake | Example | Fix | Measured |
|---|---|---|---|---|
| L010, L018, L023 | No sex for a character the script sexes | NALEDI ("Her little brother") | T082, T088, T091, T096, T100 (above) | WRONG 0 and INVENTED 0 on every labelled script; each rule's own counts in the log |
| L022 | A bare surname became a second, sexless character (FORTUIN beside MR. FORTUIN) | lighthouse 7.1, 7.5 | **T101**: a bare name folds into its one titled spelling | 30 stored extractions replayed: only the lighthouse changes; MS. NAIDOO gets her sex |
| L017 | A team or a crowd extracted as a character | final-whistle (EAGLES, CROWD) | open | |
| L019 | A character the shot's own action names left out of its cast (the planner) | stormwater | T092: the action's named figures join the cast | 45 times in 266 shots before |

### The describer (DeepSeek-V4.1-Flash, now Nemotron 3.5 Super VL): what the frame shows

The describer's words are what every check reads, so **a describer change can move every row
above**. Known on Super VL (T105, findings § U8, the-red-kite):

| Item | On Super VL | Task | Re-check |
|---|---|---|---|
| A rooftop read as `interior` | 2 of 44 | T106 (Katlego) | fault `setting` and the right frames labelled `setting` false alarms (lost-property 5.1, 7.3, 12.2, sipho 2.1, stormwater 5.1) |
| Signatures read as lettering | `text_in_frame` 6 → 22 | T107 (Katlego) | warnings only; no label changes |
| "pigtails" for the script's "braids" | the judge refuses LERATO | T108 (Tumo) | the-red-kite frames; `absent`/`unscripted_person` on right frames |
| The people described | 44 of 44 the same | | `absent` (8) and the no_character false alarms (19 right frames) |

### The judge (Nemotron Super): does the frame match the shot

| # | Mistake | Example | Fix | Measured |
|---|---|---|---|---|
| L021 | The judge leaves a drawn character unmatched, quoting their own line | the-night-taxi 2.4 ("Thabo laughs.") | **T099**: the presence agent asks per character; a found person counts for `no_character` | 30 frames: 17 of 23 false alarms found, 3 of 7 real misses wrongly found |
| L011 | A stranger excused by a line of dialogue | lost-property 7.4 | T084: a stranger's support must be an action line with no he/she | lost-property 12 → 9 accepted, the 3 now refused all wrong |
| L012 | A character's name put on someone it can't check | the-bread-van THEO | T086: a code age check | 0 of 19 THEO matches to a non-child after |
| L006 | A storm doesn't support lightning | | open | |

### The agents (vision questions after the judge)

| Agent | Asks | Withholds | Measured on stored drawings |
|---|---|---|---|
| Sex agent (T095) | each matched person a script sexes: male, female, unclear | `drawn_sex` | 175 asked, 12 flagged, all real; Super VL 48 of 48 the same answers (T105) |
| Presence agent (T099) | which numbered person is each drawn character, when the judge matched none | `no_character` passes when found | 17 of 23 false alarms fixed, 3 of 7 misses let through |
| Found person's sex (T102) | the sex agent's question on found people | `drawn_sex` | 4 flagged on 77 frames; lighthouse 7.5 caught |
| Layout agent (T104) | one picture or panels; anyone drawn twice | `split_panels` (hosted), `drawn_twice` (warns) | 23 splits all real; 6 copies after the veto, 5 real |

**Re-measure each agent on Super VL** with its own script in
[measurements/2026-10-16/](measurements/2026-10-16/) (`proto_found_sex.py`, `real_t102.py`,
`proto_twice.py`, `real_t104.py`): each runs the agent on the same stored frames, Token Factory only,
with whatever `NEBIUS_MODEL_VISION` the process has. Compare the flags and look at every one.

## How we worked (so the same can be done with the new changes)

1. **A run, then every frame looked at.** Each held-out run (a script nothing was tuned on) gets its
   report (`python -m app.verify.report <id>`), and every drawing is pulled and judged right, weak
   or wrong by eye. Those judgements are now `frame-labels.json`.
2. **The cause in the code, not the symptom.** Each wrong frame is traced to the model and the line
   of code that let it through (the learning log's *Cause*).
3. **Measured free before designing.** A fix is first tried on the stored drawings: `recheck`
   (code-only changes, no model call), `reaudit` or a prototype script (Token Factory only), never
   new drawings. The numbers go in the design doc.
4. **Design, review, code, review.** A design PR with the measurement, a fresh reviewer, then the
   code with tests first and a mutation check (each rule removed, its test must fail), then the real
   code re-measured on the same frames.
5. **Then a held-out run** to see it live, and its frames labelled in turn.

For a model change the order is the same: score the labels with the old model (`--stored`, or a
re-run), score them with the new one, look at every frame whose verdict moved, and file each
difference as a fix (as T106–T108 are).
