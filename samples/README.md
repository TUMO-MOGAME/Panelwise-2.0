# `samples`

Sample screenplays. Public-domain or self-written scripts only; never a copyrighted script, not
even an excerpt.

Each sample is a source file in a small subset of [Fountain](https://fountain.io)
(`<name>.fountain`) and the PDF built from it (`<name>.pdf`): US-letter, 12 pt Courier, standard
screenplay columns, 54 lines a page, a title page, page numbers, and (MORE)/(CONT'D) where a speech
runs over a page. Rebuild the PDFs after editing a source:

```bash
cd services/api && uv run python -m tools.build_samples
```

It prints what the real parser (`app.script.parse_pdf`) reads back. The gate's
`tests/samples/test_samples.py` checks that each committed PDF is a fresh build of its source and
that the table below matches what the parser reads.

## The samples

All thirteen are original and licensed under Apache-2.0 like the rest of the repo
([LICENSE](../LICENSE)): the first three written for this repository by Katlego (via Claude) on
2026-09-30, the other ten on 2026-10-13 (T090; see [The second set](#the-second-set-t090)). Place names
(Park Station, Pretoria, Mngazana, Hole in the Wall) are real places; every character and event is
invented.

| Sample | Shape | Pages | Scenes | Speaking characters |
| --- | --- | --- | --- | --- |
| [`the-red-kite`](the-red-kite.fountain) | Demo script: a girl, her grandfather and a kite | 5 | 5 | 3 |
| [`lost-property`](lost-property.fountain) | Larger cast, for recall: one night in a station's lost-property office | 10 | 12 | 11 |
| [`sipho-and-siphokazi`](sipho-and-siphokazi.fountain) | Deliberately awkward formatting | 6 | 11 | 4 |
| [`the-night-taxi`](the-night-taxi.fountain) | A taxi driver gets a boy home at night; moving-vehicle headings | 4 | 6 | 4 |
| [`market-day`](market-day.fountain) | Two rival spice sellers and a flood; dawn to dusk, no scene numbers | 4 | 5 | 3 |
| [`the-lighthouse-inspector`](the-lighthouse-inspector.fountain) | An inspector, a keeper and a boat adrift; radio V.O., `(CONTINUED)` | 4 | 9 | 4 |
| [`the-borrowed-bicycle`](the-borrowed-bicycle.fountain) | Two children, a borrowed bicycle with no brakes | 4 | 5 | 4 |
| [`rooftop-tomatoes`](rooftop-tomatoes.fountain) | A pensioner and a skater share a roof; a two-hander | 4 | 7 | 2 |
| [`load-shedding`](load-shedding.fountain) | An exam by candlelight; seven speakers in one room | 4 | 5 | 7 |
| [`gogos-recipe`](gogos-recipe.fountain) | A mother and son learn a grandmother's recipe; a phone V.O. | 4 | 5 | 4 |
| [`stormwater`](stormwater.fountain) | A dog lost in a storm drain; sequential scene numbers from the source | 4 | 6 | 3 |
| [`the-choir`](the-choir.fountain) | A new singer learns to blend in; a monologue split with (MORE) / (CONT'D) | 5 | 6 | 5 |
| [`final-whistle`](final-whistle.fountain) | A girls' soccer final; `SMASH CUT TO:`, `CUT TO:`, a group cue (CROWD) | 4 | 6 | 5 |

Pages include the title page. Scenes and speaking characters are what `parse_pdf` reads, which is
not always what the source says: see [Parser findings](#parser-findings).

### `the-red-kite` — the demo script

Four script pages. LERATO (10) flies a red kite from a tin roof; her grandfather MOKGOSI mends
radios in his workshop below. The string snaps in a storm, and she finds the kite at night on a
streetlight. Clear, drawable props (the red kite with yellow ribbons, a spool of blue string, a
soldering iron, a torch, a black umbrella), a day-to-night change, and one of everything the
pipeline has to handle:

- `INT.` and `EXT.` headings, times `DAY`, `CONTINUOUS`, `LATER`, `NIGHT`;
- parentheticals, `(O.S.)` and `(V.O.)` cues (the V.O. is a radio announcer, heard, never seen);
- a speech split across PDF pages 4 and 5 (printed 3. and 4.) with (MORE) / `LERATO (CONT'D)`;
- `FADE IN:` / `FADE OUT.`, scene numbers at both edges of each heading.

### `lost-property` — the larger cast

Nine script pages, twelve scenes, eleven speaking characters (ZANELE, MR. DUBE, PRIYA, KOOS, TEBOGO,
OFFICER MOLOI, OFFICER VAN WYK, GRACE, AMAHLE, SAM and a station ANNOUNCER heard in V.O.), plus
characters who never speak: a ginger cat called Marmalade, a sleeping commuter, a pigeon. A
student's lost violin, a toy giraffe called Gerald and an unclaimed cake turn up over one rainy
night, ending at dawn. No scene numbers. Characters are introduced in capitals with an age, two
cues share the word OFFICER, and several characters are referred to in action before
they speak, which is what a recall measurement (T032) needs.

### `sipho-and-siphokazi` — the tricky one

A fisherman, SIPHO, and his niece, SIPHOKAZI, sheltering from a storm with her grandmother's tide
book. Built to find the parser's edges:

- two cues where one name is a prefix of the other (SIPHO / SIPHOKAZI), and a nickname (Kazi) used
  only in dialogue;
- hyphenated compounds that break at the hyphen at the end of a line, in action (`sea-` / `green`)
  and in dialogue (`south-` / `westerly`);
- six scenes with no dialogue at all;
- an `INT./EXT.` heading, a heading with two dashes (`INT. SIPHO'S HOUSE - KITCHEN - NIGHT`), a
  heading with no time (`INT. BAIT SHOP`), `--` as the time separator, scene numbers `4A` / `4B`;
- `(CONTINUED)` / `CONTINUED:` page furniture, two parentheticals that wrap (three and four lines), a
  shouted all-caps line of dialogue (`NO! THE ROPE!`), a cue typed with `(CONT'D)`, and
  `SMASH CUT TO:`, `MATCH CUT TO:`, `CUT TO BLACK.`

### The second set (T090)

Ten short scripts (three script pages each, four for `the-choir`) written to the conventions of a
spec screenplay, so the pipeline sees the shape it will see from real writers, not only edge cases:

- **Scene headings** as `INT.` / `EXT.` / `INT./EXT.` + location + a time the parser knows
  (`DAY`, `NIGHT`, `DAWN`, `DUSK`, `MORNING`, `AFTERNOON`, `EVENING`, `SUNSET`, `CONTINUOUS`,
  `LATER`, `MOMENTS LATER`); a sub-location after a second dash (`BLOCK OF FLATS - ROOF - DAY`);
  a new heading for every change of place or time, never a bare `LATER` line.
- **Action** in the present tense, in paragraphs of at most four lines; a speaking character's
  name in capitals with an age the first time they appear (`THABO (9)`), and key props in
  capitals on first sight (`TROPHY`, `MANHOLE COVER`), which is what extraction and the frame
  prompts lean on.
- **Dialogue** with short lowercase parentheticals, the standard extensions `(V.O.)` (a radio, a
  phone) and `(O.S.)`, and one long speech the builder splits across a page (`the-choir`).
- **Transitions** used sparingly: `FADE IN:` / `FADE OUT.` or `FADE TO BLACK.`, with `SMASH CUT TO:`
  and `CUT TO:` once each in `final-whistle`.
- **Page furniture** varied over the set: scene numbers at both edges, none, numbers from the
  source (`#1#` … in `stormwater`), and `(CONTINUED)` / `CONTINUED:` (`the-lighthouse-inspector`,
  `load-shedding`).

Every place name (Bree Street, Orlando East, Hillbrow) is a real place; every character and event
is invented. Each script is one location-light story with clear, drawable props and at most seven
speakers, so a full storyboard run costs about what `the-red-kite` does. Nine of the ten (all but
`the-choir`) have had live runs as held-out scripts for the frame audit, 13–17 Oct
([eval/runs/](../eval/runs/README.md)); their faithfulness and recall numbers belong here once
measured.

## Parser findings

Found by these samples on 2026-09-30. Items 1–4 are fixed by T039 (lane `script+grounding`); every
sample now parses with all of its source's scenes (12, 11, 5), action paragraphs (50, 31, 21) and
parentheticals (13, 3, 4).

1. **`INT./EXT.` headings were not recognised** — fixed. `SCENE_HEADING_RE` accepted `INT/EXT` and
   `INT/EXT.` but not `INT./EXT.`, the form most screenwriting software writes, so scene 3 of
   `sipho-and-siphokazi` was read as an action line inside scene 2 (10 scenes, not 11).
2. **A blank line between two action paragraphs was sometimes lost** — fixed. pdfplumber's layout
   text used `y_density=13` points a row; a screenplay's lines are 12 points apart, so a one-line
   gap sometimes rounded away and two paragraphs parsed as one `Action` (2 of 21 breaks in
   `the-red-kite`, 6 of 50 in `lost-property`, 5 of 31 in `sipho-and-siphokazi`). `parse_pdf`
   now reads 12 pt rows.
3. **A heading with two dashes split at the first** — fixed.
   `INT. SIPHO'S HOUSE - KITCHEN - NIGHT` now gives location `SIPHO'S HOUSE - KITCHEN`, time
   `NIGHT` (the last segment is the time when it is a known time), and
   `INT./EXT. SIPHO'S BAKKIE - MOVING - DAY` gives `SIPHO'S BAKKIE - MOVING`, `DAY`.
4. **A parenthetical that wraps was read as dialogue** — fixed. Both speeches in
   `sipho-and-siphokazi` (three and four lines) now have their parenthetical, and dialogue text
   without it ([docs/design/script.md](../docs/design/script.md) §4).
5. **A line-break hyphen stayed in the element text** (`sea- green`, `south- westerly`) — fixed by
   T048. Grounding joined it in the script's raw lines, but the model was shown the element text
   and copied `sea- green`, which was then not located (2 of 36 quotes in the 2026-09-30 T039 run
   of `sipho-and-siphokazi`), and comic lettering showed the space. The parser now joins a dash
   run that touches the word before it with no space (`sea-green`, `south-westerly`,
   `nineteen-ninety-something`, and `nine-fifteen` in `lost-property`); a spaced dash
   (`LOST PROPERTY - PLATFORM 9`) keeps its space ([docs/design/script.md](../docs/design/script.md)
   §3). Live after T048, two runs: faithfulness 0.846 (11/13; 33/34 quotes) and 0.944 (17/18;
   39/40 quotes), recall 4/4 both; the `sea-green` quote was copied joined and located.

Handled correctly: (MORE) / (CONT'D) splits, `(CONTINUED)` / `CONTINUED:`, page numbers,
transitions, `4A` scene numbers, a heading with no time (`None`, not an invented `DAY`), `--` as
the separator, the shouted all-caps dialogue line, and SIPHO / SIPHOKAZI kept apart as cues.

## Live runs on the real account (2026-09-30)

Nemotron 3.5 Lightning on Token Factory (`nvidia/Nemotron-3_5-Lightning`, thinking off), one
extraction chunk per sample, 1,400–2,900 tokens in and 550–2,400 out a run.

### `the-red-kite`, before T039

| Check | Command | Result |
| --- | --- | --- |
| Shots | `uv run python -m app.shots.run ../../samples/the-red-kite.pdf` | 19 shots over 5 scenes; **every element in exactly one shot: yes**; 0 ranges repaired; 0 character and 4 prop names dropped as not in their scene. Planning 4,244 in / 1,377 out, extraction 1,389 in / 749 out, 0 reasoning tokens |
| Grounding, run 1 | `uv run python -m app.grounding.run ../../samples/the-red-kite.pdf` | faithfulness **0.625** (5/8 entities, 11/26 quotes located); recall **0.000** (0/3 speakers) |
| Grounding, run 2 | same | faithfulness **0.143** (1/7 entities, 8/30 quotes located); recall **0.000** (0/3 speakers) |

Every character still reached the shot plan (the cue fallback adds LERATO, MOKGOSI and RADIO
ANNOUNCER from their cues), and nothing ungrounded was kept. But the cause of the low numbers was
visible in the raw model output: **Lightning started almost every dialogue quote with the
speaker's cue line** (`"LERATO\nI promise."`, `"MOKGOSI (smiling)\nAnd we watch the sky."`). The
cue is not inside the dialogue element's span, so `locate` rejected the whole quote, and a
character quoted only through dialogue was dropped from the model's list.

### Grounding before and after T039, all three samples

`uv run python -m app.grounding.run ../../samples/<name>.pdf`. "Before" is `main` at `68c4cd8`,
"after" is T039 (prompt asks for dialogue quotes without the cue or parenthetical; the filter
strips a leading line that is that same speech's own header; 12 pt rows; the heading and
parenthetical fixes). One run each; Lightning at temperature 0 still varies run to run.

| Sample | Faithfulness before | after | Recall before | after |
| --- | --- | --- | --- | --- |
| `the-red-kite` | 0.333 (2/6; 7/27 quotes) | **1.000** (7/7; 29/29 quotes) | 0/3 | **3/3** |
| `lost-property` | 0.793 (23/29; 79/87 quotes) | **0.846** (22/26; 77/81 quotes) | 10/11 | 10/11 |
| `sipho-and-siphokazi` | 0.333 (5/15; 13/45 quotes) | **0.750** (12/16; 34/36 quotes) | 0/4 | **4/4** |

With the new prompt Lightning mostly leaves the cue out, so most of the gain is the prompt. In a
diagnostic run over all three samples, 2 of 166 quotes still led with a header — both with the
speech's own parenthetical (`"(reading)\nThree umbrellas. …"`) — and the filter kept them at that
speech without it. What still fails: names the script never writes (`NOTEPAD`, `GURGLE`: dropped),
a model paraphrase (`"He plays a VIOLIN."`: dropped), finding 5 above, and the ANNOUNCER in
`lost-property`, a V.O. voice the model doesn't list (added from its cue, not counted to recall).

### Animals and other names (T051, 2026-10-01)

`uv run python -m app.grounding.run ../../samples/lost-property.pdf`, Lightning. The extraction
now carries a grounded `species` for an animal character and `other_names` for a character or prop
([docs/design/grounding.md](../docs/design/grounding.md) §3), so frame prompts can draw MARMALADE as
a cat and redact the toy giraffe's name, "Gerald" (T052).

| Prompt | Runs | MARMALADE `species` | "Gerald" in the giraffe's `other_names` |
| --- | --- | --- | --- |
| first wording ("list any other name … such as a nickname or the name of a pet or a toy") | 5 | `ginger cat` 5/5 | 1/5 (the model also invented a "GERRY THE GIRAFFE", dropped: not in the script) |
| final wording ("a name someone gives a pet, a toy or a vehicle, even if only in dialogue") | 4 | `ginger cat` 4/4 | **4/4** |

On the other samples (final wording, one run each) no character got a species and faithfulness and
recall were unchanged (`sipho-and-siphokazi` 0.929, 4/4; `the-red-kite` 1.000, 3/3). SIPHOKAZI's
nickname "Kazi" isn't captured; it is only ever spoken, and dialogue never enters a frame prompt.

### Frame prompts with labels (T052, 2026-10-01)

`uv run python -m app.storyboard.prompts ../../samples/lost-property.pdf`, Lightning, 4 runs, 50
shots each: every script part cited, 0 extracted names in any prompt, MARMALADE drawn as "the
ginger cat" and never counted as a figure, and the toy as "the giraffe". In **1 of the 4 runs
"Gerald" reached a prompt** ("a person dances with Gerald"): that run's extraction didn't give the
giraffe its other name, and a name the extraction never reports can't be redacted, the residual
risk storyboard.md §3.1 records. The other 3 runs had no "Gerald" or "Marmalade" anywhere.
