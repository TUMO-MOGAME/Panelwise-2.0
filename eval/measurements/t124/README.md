# Drawn twice: why the layout agent misses copies, and what would catch them (2026-10-19)

Tumo (via Claude). Free: stored audits only (the local database; two stored Super VL measurements).
No model was asked anything.

## Samples
- **The 17 Oct runs.** gogos-recipe ran with T104 (the layout agent); rooftop-tomatoes ran before it.
  All 39 storyboard attempts, labelled by hand from the two run reports.
- **the-lighthouse-inspector** (Super VL, `eval/measurements/2026-10-17/lighthouse-super-vl.json`):
  25 labelled attempts.
- **the-red-kite** (`eval/measurements/2026-10-18-describer/signature-slot.json`): 3 labelled attempts.

In all, 67 labelled attempts, including 10 drawn twice and 34 right. `rules.py` scores the rules.

## 1. The layout agent (gogos-recipe, the only sample it ran on)
- 1.4 a1: the pair named, but the frame is in 2 panels, so `split_panels` withheld it (by design).
- 3.4 and 5.3: caught (`drawn_twice`; it **warns**, because the ladder doesn't withhold it).
- **2.1 missed:** the describer wrote *the same words* for both children ("a child in a short-sleeved
  shirt and shorts"). The agent said "different faces, hair, and clothing details".
- **1.4 a2 missed:** "one has long loose hair and no bracelet, the other hair tied back". The agent
  argues from small differences the drawing style makes.

## 2. Every copy has an unmatched person
In 9 of the 10 copies, one of the pair is a person the judge matched to no character. So
`unscripted_person` already fails on them (rooftop 6.2 is the exception). It only warns: the hosted
ladder withholds `drawn_sex,no_character,split_panels`.

| Rule | Flags | Copies caught (of 10) | Other wrong | Weak | **Right** |
|---|---|---|---|---|---|
| U: `unscripted_person` (today's check) | 18 | 9 | 4 | 7 | **0** |
| W(0.4): words overlap ≥ 0.4, one of the pair unmatched | 11 | 7 | 2 | 4 | 0 |
| **W(0.5)** | 9 | 7 | 0 | 4 | **0** |
| W(0.8) | 3 | 3 | 0 | 0 | 0 |

The overlap is the Jaccard index of the two `appearance` strings' words, with stop words removed.
The copies' overlaps: 2.1 1.00 · 5.3 0.82 · rooftop 3.1 0.82 · lighthouse 7.3 0.57 · rooftop 6.2 0.54 ·
1.4 a2 0.50 · lighthouse 4.2 0.50. Below 0.5: 3.4 0.00 (the judge matched both; the layout agent
caught it), rooftop 4.3 0.24, red-kite 4.1 0.00. The 2 weak frames at ≥ 0.5 are gogos 5.1 (0.75) and
5.4 (0.50, a young man in Zodwa's place: a real fault).

## 3. U is not safe to withhold on alone
On the 109 labelled frames (re-scored on Super VL, 17 Oct; `labels-super-vl.json`), U flags **11 of
the 40 right frames**. Nearly all are "the cast is drawn; the judge didn't match them", from runs
whose stored extraction predates T101 and T102. On fresh runs (above) U flags none, but a judge miss
is common enough that withholding on U alone would hide right frames.

## Reading
- The misses are the agent's, not the describer's: the describer's own words already say "the same
  person" in 5 of the 7 W(0.5) catches. The layout agent saw two of them and argued them apart.
- A copy is drawn, not described: the judge can't match the second figure to anyone, because the
  script has one of them.
- W(0.5) plus the layout agent catches 8 of 10 copies with no right frame lost. That is 2.1, 1.4 a2,
  3.4, 5.3, rooftop 3.1 and 6.2, lighthouse 4.2 and 7.3; the layout agent's answer on the rooftop,
  lighthouse and red-kite frames is unknown, since it never ran on them. It misses rooftop 4.3 and
  red-kite 4.1.
- Withholding is what makes a catch matter: today every caught copy is shown with a warning.

## 4. The same rule on the old describer (the risk)
The 109 labelled frames' own stored audits (the local database, latest audit per attempt; 680 of
them described by DeepSeek-V4.1-Flash) with the same rule:

| Overlap | Copies (of 6) | Right flagged (of 40) | Other wrong |
|---|---|---|---|
| ≥ 0.5 | 3 | **6** | 10 |
| ≥ 0.6 | 0 | 4 | 2 |
| ≥ 0.8 | 0 | 2 | 1 |

All 6 right frames are "the cast is drawn; the judge didn't match them": DeepSeek's generic
appearances ("a man in a shirt") overlap. The hosted demo describes with Super VL, whose
appearances are longer; the-choir and the judge sample measure the rule there again.

## Files
- `attempts.json`, `checks.json`: the 17 Oct runs' stored attempts (from `frame_audits`).
- `rules.py <repo> <this directory>`: the table in §2.

## Note on the map
`rules.py` counts a person as known when the judge's raw call names any character; the code uses
the accepted and found characters plus the scripted extras (review of #222). Accepted drops a name
outside the shot or refused for its age (both already fail `UNSCRIPTED_PERSON`), so the code can flag
a little more; the extras flag less. `recheck-17oct.txt` is the code's own run on the 17 Oct rows:
6 of 7 copies, no right frame.

## 5. A narrower rule, for the next look (`rules2.py`, free)
Counting a described-alike pair only when **exactly one** of the two is a known character (the
judge matched one figure; the copy is the other):

| Sample | As merged | Exactly one known |
|---|---|---|
| Super VL, stored (67) | copies 7/10, right 0/34 | copies 6/10, right 0/34 |
| 109 labelled, stored DeepSeek-era | copies 3/8, right 6/40 | copies 1/8, right 0/40 |

It would not fix the layout agent's own false calls (the-night-taxi 2.1 on 2026-10-20).
