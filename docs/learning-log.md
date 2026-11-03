# Learning log

What our live runs taught us, one lesson per entry, newest first. Every entry has the numbers it
was seen with, its cause in the code, what we did, and what that measured before and after. Read
it before changing the prompt or the audit; add to it after every live run.

- **How:** run the report (`python -m app.verify.report <project-id>`, free) and save it under
  [eval/runs/](../eval/runs/README.md). Then read its Causes, Characters and Shots and write or
  update entries here.
- **Measure fixes on stored drawings first.** The same prompt and seed give the same drawing, so
  `python -m app.verify.reaudit` tests an audit change with no new drawings: Token Factory calls
  only, two per drawing. Only a prompt or renderer change needs new drawings, and that costs fal
  money (ask first).
- **Format** ([docs/design/learning.md](design/learning.md) §6): `### L<nnn> · <name> · <open |
  fixed | won't fix>`, then Seen, Cause, Action, Measured.

---

### L023 · A girl the script says is a girl, drawn as a boy all through: her sex was in a "Her" · open

- **Seen:** 2026-10-14, the-borrowed-bicycle (held out), [run report](../eval/runs/2026-10-14-the-borrowed-bicycle.md):
  **18 of 18** shown in 19 drawings (`no_character` withheld 1.4's first attempt; its redraw was
  shown). Every drawing looked at: NALEDI (12) is drawn as a boy in about 11 frames (1.1, 1.2, 1.3,
  2.1, 2.3, 3.1, 3.2, 4.1, 4.3, 5.1, 5.2; 1.4's redraw unclear). The extraction gave her no sex, so
  every prompt said "a 12-year-old" and klein drew a boy in dungarees; the sex agent had no script
  sex to check. **4.2** ("They sit up, brown from head to toe") drew a naked muscular adult man
  beside the bicycle: no figure in the prompt (a plural "They" resolves to no one), klein invented
  him, the judge called him a stranger, and `unscripted_person` is off the ladder, so it was only
  warned. Right: 2.2 (the shopkeeper and his newspaper), 3.3 (the puddle), Mr. Kekana in his church
  suit and feathered hat (5.2), 5.4; 5.1 has extra children; 5.5 an empty yard for a line.
- **Cause:** every sign of Naledi's sex is a "her": "NALEDI (12), dungarees, scraped knees, stares at
  it. **Her** little brother TSHEPO (8) …" and "Tshepo sits on the carrier behind **her**, arms
  around **her** waist". `introduced_sex` reads only the introducing sentence and its look; the
  evidence code (T088/T091) chains a next sentence only when it opens with He or She, and no sentence
  opening with "Naledi" holds a pronoun.
- **Action:** T100 (storyboard.md §3.1): a sentence that opens with a possessive Her or His right
  after a character's introducing sentence gives that character's sex, only when the introducing
  sentence holds no other person (named, a sex noun, a person noun, or a him/her/his/them). Measured free on the labels of the 10 labelled scripts with a sample file: **1 candidate (NALEDI), 1 right, 0
  wrong**. Separately, a plural "They" with the shot's own people in the scene draws no one (4.2).
- **Measured:** not yet.
- **Sex labels** (eval/sex-labels.json): `character_sex` right for TSHEPO, SHOPKEEPER and MR. KEKANA,
  a miss for NALEDI; 0 wrong, 0 invented.

### L022 · A bare surname became a second character, with no sex · open

- **Seen:** 2026-10-14, the-lighthouse-inspector (held out), [run report](../eval/runs/2026-10-14-the-lighthouse-inspector.md):
  **26 of 26** shown, every one at its first attempt, every frame looked at: **14 right, 11 weak,
  1 wrong**. The wrong one is **7.5**, Mr. Fortuin drawn as an old woman cranking the lamp. Its cast is
  `FORTUIN`, a second character the extraction proposed beside `MR. FORTUIN` with the same verbatim
  lines (and `NAIDOO` beside `MS. NAIDOO`); the script's cues are always `MR. FORTUIN` and `MS. NAIDOO`.
  `FORTUIN` has no sex, so 7.1 and 7.5 prompted "a person in their 70s". On 7.5 the describer said
  "woman", the judge matched no one, and the presence agent (T099) found her as FORTUIN ("the
  describer's guess of 'woman' is uncertain"): with no sex from the script in its question it had
  nothing to refuse her by, and a found person gets no `DRAWN_SEX` question (by design). Without T099,
  `no_character` would have withheld 7.5 for a redraw. The weak ones: Ms. Naidoo drawn twice (4.2,
  7.3), an extra man on the stairs (4.1), the lens room without its lens (5.1), no rescue boat (8.1),
  props or actions missing (2.2, 6.1, 9.1), empty frames for heard-only speakers (2.3, 7.4), an
  old person of unclear sex (7.1, the same `FORTUIN`). 8.1's prompt reads "An orange a person BOAT":
  the RESCUE of RESCUE BOAT redacted as a word of RESCUE OFFICER.
- **Cause:** grounding keeps every proposed character whose quotes are verbatim; nothing folds a name
  whose words are a proper subset of another's (FORTUIN, MR. FORTUIN) into it. Measured free on every
  stored extraction (newest per script, 10 scripts): only this one has such pairs (2), and the bare
  `FORTUIN` is cast in 2 of its 26 shots.
- **Action:** T101 (grounding.md §3): the measure found a sharper cause. The model named only the bare
  `FORTUIN` and `NAIDOO`; the longer two are `Source.CUE` backfills, because `match_speaker` binds a
  cue only to a name holding all its words. So a bare `CHARACTER` name folds into the one titled
  spelling (a cue, or a model name the script writes) whose words are it plus forms of address
  (`TITLE_WORDS`; never a kinship word: Mama Thembi can be Thembi's mother); none, two (`MR. DUBE`,
  `MRS. DUBE`), a bare cue or a superset name (`THABO DUBE`): no fold. Merged 2026-10-16 (#179,
  #180). T102 (verify.md §3): a person the presence agent finds is asked T095's sex question too,
  and `DRAWN_SEX` fails on the other sex. Still open: redacting a multi-word role name only whole
  (8.1).
- **Measured:** free, 2026-10-15, `ground` replayed on the model entities of all 30 stored
  extractions with a prototype fold: **1 changed**, this one: `MR. FORTUIN` and `MS. NAIDOO` each one
  `Source.MODEL` character with their 3 quotes, recall 2/4 → 4/4, `MS. NAIDOO` female from her own
  pronouns; 29 identical. T102, Token Factory only (2026-10-16): the presence agent run afresh on
  the 77 stored frames it would run on found 36 people the script sexes; asked, 2 the other sex,
  both real (sipho-and-siphokazi 2.1, MAMA THEMBI drawn as a man; the-borrowed-bicycle 4.1,
  NALEDI as a boy), 0 false alarms, 6 questions failed (the model's thinking used its tokens).
  The real code (sex question at 4,096 tokens, 1 of 37 failed): `DRAWN_SEX` fails 4 frames, lighthouse
  7.5 among them (MR. FORTUIN drawn as an old woman, with T101's names), one arguable (the-night-taxi
  2.3, a child who reads as a girl, in a frame wrong anyway).  Live: the next held-out runs.
- **Sex labels** (eval/sex-labels.json): `character_sex` right for MS. NAIDOO and MR. FORTUIN, a miss
  for both duplicates, 0 wrong, 0 invented. The sex agent asked about 32 matched people, every
  answer the script's sex; nothing withheld.

### L021 · The judge leaves a drawn character unmatched, citing their own line · open (T099)

- **Seen:** 2026-10-14, a free what-if (`recheck` with `drawn_sex` plus one rule) on nine stored runs:
  `NO_CHARACTER` would withhold **30** of the frames shown today; every one looked at, **23 had the
  character plainly drawn** (22 at first look; final-whistle 3.3's referee does wear the striped shirt) (Lindi in goal with her gloves, Siphokazi smiling, Thabo laughing in the
  taxi). In nearly all of them the describer saw the person and the judge called them no character,
  often with the character's own line as the support (the-night-taxi 2.4: support "Thabo laughs.").
  The other candidate rules measured worse or no better: `setting` 3 real of 8 (EXT bakery scenes
  drawn inside; the false alarms indoor places that look open: a covered platform, the tunnels, a
  bait shack), `unscripted_object` 0 of 2 (a police baton on a belt, a knife on a workbench),
  `unscripted_person` 114 frames (L020).
- **Cause:** the judge does the matching and the stranger rules in one answer; on a person whose look
  doesn't spell out the quote's details it leans to "no character", even when it quotes that
  character's line.
- **Action:** T099, the presence agent: when the judge matched none of the drawn characters, a vision
  question per character ("which numbered person, if any, is this character?"); a found person
  counts for `NO_CHARACTER` only. Design: verify.md §3.
- **Measured:** prototype on the 30 stored frames (Token Factory, two runs): 18 and 16 of 23 false
  alarms found, 2 and 3 of 7 real misses wrongly found. The real code on the same frames (#172): 17
  of 23 and 3 of 7. Live, 2026-10-14, the-lighthouse-inspector (held out, `drawn_sex,no_character`):
  the agent ran once in 26 shots (7.5) and found a person the describer called a woman for the
  bare `FORTUIN` (a duplicate of MR. FORTUIN), a wrong frame shown (L022); `no_character` withheld nothing.

### L020 · Every stranger withheld the frame, so right frames were hidden · open (T094, T095 in review)

- **Seen:** 2026-10-13, market-day (held out), [run report](../eval/runs/2026-10-13-market-day.md): **0 of 15** accepted, 44 drawings.
  Every stored attempt pulled from Storage and looked at: about 12 of the 15 final drawings are right
  (Auntie Precious's floral headscarf and glasses, Yusuf's apron over a football shirt, Kamo with the
  newspaper); the judge matched the shot's own characters in nearly every attempt; every refusal was
  `UNSCRIPTED_PERSON` over market shoppers klein added. the-night-taxi (held out,
  [report](../eval/runs/2026-10-13-the-night-taxi.md)): 10 of 20, the 10 withheld all over people (klein's extras, Bongani drawn
  three times for "He stops, frowns, and laughs", the judge missing an obvious match), 0 wrong in the
  accepted. Free what-if on the stored audits of nine runs: accepting an attempt whose only hard
  failure is `UNSCRIPTED_PERSON` takes 144 of 216 shots to about 203 (crude: it also holds age refusals).
- **Cause:** the audit's rule that every person traces to the script fights the image model: klein
  draws places as they look, full of people, and fal's klein takes no negative prompt.
- **Action:** Tumo's call (2026-10-13): drop the rules and bring them back one at a time. T094 (the
  rule ladder, `AUDIT_WITHHOLD_CHECKS`), T095 (the sex agent, `DRAWN_SEX`, the first rule back),
  T096 (an appositive sex noun, "A boy …, THABO (9)"): #166 design merged; #167 and #168 code in
  review.
- **Measured:** market-day again with no rule withholding ([report](../eval/runs/2026-10-13-market-day-2.md)): **16 of 17** shown in 17
  drawings, 9 right, 5 weak, 2 split panels (L015), none the wrong sex or age. The sex agent's
  prototype on stored drawings: 175 people asked, 12 flagged, every one a real error, 0 false alarms.
  load-shedding with only `drawn_sex` withholding ([report](../eval/runs/2026-10-13-load-shedding-2.md)): **18 of 18** shown in 19 drawings;
  3.1's first attempt drew Pieter as a girl and was withheld and redrawn as a boy; every frame looked
  at, 13 right, 5 weak (1.3 a split panel, 5.3 an extra man), none the wrong sex (the last run had
  Fatima and Nomsa as boys). T091 gave all 7 learners a sex this time (1 of 7 before).

### L019 · A character the shot's own action names is left out of its cast · open

- **Seen:** 2026-10-13, stormwater (Katlego's T090 sample, held out), [run report](../eval/runs/2026-10-13-stormwater.md). 3.1's action
  is "Mr. Van der Merwe climbs down with a crowbar and a torch", but the shot's cast is SIBUSISO and
  REFILWE: the prompt draws two figures, and the old man klein drew (attempt 2) failed as a
  stranger; 3.1 withheld. 3.2 ("Mr. Van der Merwe levers up the … MANHOLE COVER") has no cast at
  all. And the prompt reads **"a person der a person climbs down"**: the name is redacted word by
  word, and the lower-case "der" breaks the run.
- **Cause:** the planner may only list characters the extraction says are in the scene
  (`_allowed`: `scene_index in entity.scenes`), and the extraction's `scenes` are incomplete.
  Measured free on the stored plans of the seven read scripts: **45 times in 266 shots** a shot leaves out a
  character its own action line names, **38** of them because the planner was never offered
  the character, 7 because the model left an offered one out. `_redact` joins only capitalised
  name words, so "Van der Merwe" is two runs.
- **Action:** T092 (shots.md §3): after the model, a shot's cast gains every character a
  covered action line names as a figure (a Title-case name, or an UPPER-case introduction with its
  "("; never a possessive like "the Lionesses' goalkeeper", never a scoreboard's "LIONESSES 1");
  a name's lower-case particle (van, der, de…) joins its run. Prototype on the same plans: 40
  characters added in 28 of 181 shots, every one read: 38 people the line puts there (final-whistle
  5.4 "The Lionesses pile on top of Lindi. Palesa holds up the gloves", lost-property 12.2 "Mr. Dube
  winds his pocket watch"), 2 groups (EAGLES, LIONESSES: L017). On-screen speakers missing from a
  cast (12 more) are left alone: a shot of the listener is the planner's choice.
- **Measured:** T092 built (#161 design, #163 code). Free, the real code on the same stored plans:
  the same 40 characters in the same 28 shots as the prototype; stormwater's rebuilt prompts read
  "a person climbs down" and "a person levers up the heavy steel MANHOLE COVER". Live: not yet (a
  stored plan keeps its cast; the next upload is re-planned).

### L018 · T088 keeps a sex only when the model claims one, and on a new script it claimed none · open

- **Seen:** 2026-10-13, load-shedding (Katlego's T090 sample, held out: no fix was designed on it),
  [run report](../eval/runs/2026-10-13-load-shedding.md). The extraction gave **no sex to any of the six learners**, though the script
  states each one plainly: AYANDA "chews her pencil", FATIMA "calculator lined up with her ruler",
  NOMSA "praying with her eyes closed", JABU "covers it with his arm", PIETER "pulls his hood down",
  LUCKY "looks at his paper". Two accepted frames draw girls as boys: **1.2** (Nomsa praying, and
  Pieter's hood on a girl) and **2.4** (Fatima, 16). final-whistle ([run report](../eval/runs/2026-10-13-final-whistle.md)) missed the
  REFEREE ("blows his whistle").
- **Cause:** T088 keeps a sex only when the extraction model claims a `sex_word` *and* the script's
  own subject pronouns support it. Here the model claimed nothing (and "she" for MS. MOLEFE, which
  is a pronoun, not a claim), so the evidence code, which found the right sex for every one of
  them, was never asked.
- **Action:** none yet; proposed as T091 (not yet in TASKS). Measured free on every labelled stored extraction: the
  evidence alone (`_pronoun_evidence`, every quote one sex), with today's sex winning where it has
  one:

  | script | today | evidence alone |
  |---|---|---|
  | load-shedding (held out) | 1 of 7 | **7 of 7** |
  | final-whistle (held out) | 4 of 5 | **5 of 5** |
  | lost-property | 6 of 12 | 9 of 12 |
  | sipho-and-siphokazi | 3 of 5 | 5 of 5 |
  | the-red-kite, the-bread-van | 3 of 3, 3 of 5 | 3 of 3, 3 of 5 |

  **0 wrong and 0 invented** in all 37 labels (RIGHT 20 → 32). Still missed: THEO, PRIYA, TEBOGO,
  OFFICER MOLOI, the TAXI DRIVER.
- **Measured:** T091 built (#158/#159). Live, 2026-10-13, stormwater (held out, after T091,
  [run report](../eval/runs/2026-10-13-stormwater.md)): **1 of 3** (MR. VAN DER MERWE, by his title), 0 wrong; REFILWE and SIBUSISO
  missed, and **all 5 wrong accepted frames** are theirs: Refilwe (11) drawn as a boy (1.2, 6.2),
  Sibusiso (20s) as a young woman (3.3, 4.1, 5.2). T091 finds neither, as designed: Refilwe's only
  pronoun is "She drops to her knees", a next-sentence She after her own speech (a speech breaks
  the chain; a next-sentence She alone keeps nothing without a claim), and Sibusiso's "climbs out
  of the hole with Biscuit inside his overalls" has another name (the dog's) between him and his.
  **A speech by the character itself keeps the chain: measured, not built** (Tumo, 2026-10-13).
  Token Factory, two fresh extractions of each of six labelled scripts (about 38,000 tokens), the
  raw proposals kept and grounded three ways: today; with "he"/"she" counted as claims; and with
  that plus a speech by the character not breaking the He/She chain. **All three: 56 right, 0
  wrong, 10 missed**, the same misses. The model does claim REFILWE "she", SIBUSISO "he" and PRIYA
  "she", but T088's chain also needs the sentence before to hold no other possible owner, and
  REFILWE's introduction "… runs down the pavement holding an empty lead" has "the". Loosening that
  means guessing which nouns can be people, which is where wrong sexes come from.

### L017 · A team or a crowd is extracted as a character, and its name is blanked in the prompt · open

- **Seen:** 2026-10-13, final-whistle (held out), [run report](../eval/runs/2026-10-13-final-whistle.md). LIONESSES, EAGLES, CROWD and
  STRIKER are characters in the extraction. The prompt redacts every character's name, so 2.1 reads
  "The a person' a person, in red, breaks through and shoots" and 5.2 "The a person build a wall"
  (drawn as two boys at a brick wall); 5.4 "The Lionesses pile on top of Lindi" is drawn as boys,
  though the script says "A girls' team"; 5.3 failed "none of CROWD in frame"; and in T087's re-judge of these drawings the judge
  matched drawn men to "EAGLES" and "STRIKER".
- **Cause:** the extraction treats any capitalised name that acts as a character; nothing marks a
  group, so it is redacted, counted as a figure and checked like a person.
- **Action:** none yet. To look at first: what the extraction returns for these (a group kind, or
  no character at all) and how many samples have one.
- **Measured:** not yet.

### L016 · A pronoun's action goes to whoever the prompt draws · open

- **Seen:** 2026-10-12, the-bread-van, second run ([run report](../eval/runs/2026-10-12-the-bread-van-2.md)). Accepted **5.3** draws
  THEO saluting: the script's "He salutes and goes." is DANIEL leaving, but the shot's characters
  are NOMSA and THEO, and the prompt keeps the sentence with its "He". Attempt 1 of **1.3** draws a
  round biscuit stuck to THEO's cheek: "Biscuit opens both." is the dog.
- **Cause:** the prompt replaces names with "a person" and keeps action sentences whole, so a
  sentence whose subject is a pronoun or an unintroduced name is read by klein as being about
  whoever is drawn. The audit can't see it: a salute is no object and no person.
- **Action:** T093, for a He or She (below). First considered: drop an action sentence
  whose subject is a pronoun or a name not in the shot's drawn cast. That needs a new resolver:
  T088's `_pronoun_evidence` only links a pronoun to a name opening the sentence before it, so
  it doesn't cover 5.3 (its "He" follows a line of dialogue), and "Biscuit opens both." has no
  pronoun at all.
  Counted free on the stored plans of the seven read scripts (2026-10-13), each action sentence
  of a prompt that opens with He, She, They, His or Her, by the figures the prompt draws: **54**;
  16 safe (the one drawn figure, or exactly one of several, has that sex), **12 in a shot that draws
  no figure** (stormwater 6.4 "He looks at the ball. He puts it in his pocket.": klein drew a man
  three times, the judge never matched him to MR. VAN DER MERWE, withheld), **2 against the only
  drawn figure's sex** (the-bread-van 1.2, whose He is THEO, whom T092 now casts; lost-property 2.3,
  "He peers at the ledger", MR. DUBE with only ZANELE drawn), 24 ambiguous (several figures, or a
  sex unknown).
  **T093** (storyboard.md §3.1): a He or She in a shot that draws no one is the one cast person of
  that sex, all sexes known; one against every drawn figure's known sex is left out.
- **Measured:** free, T093's real code on the stored plans with T092's casts: 4 shots now draw
  the pronoun's person (stormwater 2.3 and 6.4 MR. VAN DER MERWE, load-shedding 5.4 MS. MOLEFE,
  the-red-kite 5.4 MOKGOSI) and 1 sentence is left out (lost-property 2.3); each read against the
  script, all right. Not covered: the-bread-van 5.3 (DANIEL's "He salutes and goes." on a drawn
  THEO: the sex agrees). Live: not yet.

### L015 · klein draws two panels in one frame · open

- **Seen:** 2026-10-12, while looking at every frame the L014 what-if would accept: the-bread-van
  (second run) 1.3 attempt 1, sipho-and-siphokazi 6.1 attempt 1 and lost-property 11.5 attempt 1
  are each two side-by-side panels, the shot's people split across them (11.5 with a different
  cast in each half).
  Again on 2026-10-13: load-shedding 1.3 (the lights on, then dark), accepted.
- **Cause:** klein, on a "storyboard sketch" prompt, sometimes lays out a strip of panels. The
  describer lists the people of both halves as one frame, so nothing checks the layout.
- **Action:** parked (Tumo, 2026-10-13). fal's klein takes no negative prompt, so a fix means
  rewording every style's positive words, which changes every drawing; and splits are rare (about 4
  in some 500 stored drawings), so two test runs (about 80 drawings) could not show a change. A
  describer question ("one picture or several panels?") is the measurable route, on the four
  stored splits and as many whole frames, if it comes back.
- **Measured:** 2026-10-16, a vision question ("one picture or several panels; anyone drawn twice?")
  on every stored attempt with two or more people (332, the newest run of 11 scripts; Token Factory
  only): **23 splits, every one looked at, all real**, far more than the 4 seen by eye. Three
  were shown (market-day 4.2 and 5.2 warned, the-red-kite 5.2 passed). T104 (verify.md §3): a
  `SPLIT_PANELS` check and a `DRAWN_TWICE` check from that question, hard, on the ladder by
  Tumo's call.

### L014 · Painted lettering and everyday objects hold back most shots · open

- **Seen:** 2026-10-12, measured free on the stored audits of five runs with today's code
  (`recheck`), then counting the shots that would have an accepted attempt if `unscripted_object`
  and `text_in_frame` only warned (people stay hard):

  | run | today's code | objects and lettering warn |
  |---|---|---|
  | the-bread-van, second run | 3 of 20 | 9 |
  | the-bread-van, first run | 2 of 19 | 5 |
  | lost-property (held out) | 9 of 49 | 33 |
  | sipho-and-siphokazi | 14 of 30 | 26 |
  | the-red-kite (T079 + T080) | 19 of 21 | 20 |

  On lost-property klein paints "LOST PROPERTY" as LOST POVERTY, LOST PORRY, LOST PPARERERY on
  almost every sign, and each fails `text_in_frame`.
- **Cause:** every word klein paints is checked against the script, and klein can't spell. Every
  unscripted everyday object (a bag, a pen in a hand, a plate) fails the frame too.
- **Action:** none yet. Every one of the **46** newly accepted drawings was looked at: **34
  right**, **12 wrong**, and every wrong one is wrong in its *people*, never in an object or a
  lettering: 7 girls drawn as boys (sipho-and-siphokazi 2.2, 2.4, 4B.1, 4B.3, 6.1 SIPHOKAZI;
  lost-property 11.1 AMAHLE, 3.2 PRIYA), two split panels (L015: lost-property 11.5, the-bread-van
  1.3), MR. DUBE drawn young (lost-property 12.2), THEO at a steering wheel holding Biscuit as a
  soft toy (the-bread-van 3.1), and a rowboat for Sipho's fishing boat (sipho 5.2). So L009 again:
  relaxing objects is safe only where people are checked. The stored extractions of the two older
  runs have no sex (they predate T088); T088 now finds SIPHOKAZI and AMAHLE, not PRIYA (L010).
- **Measured:** live, 2026-10-13, on two held-out scripts (Katlego's T090 samples, nothing tuned on
  them): load-shedding **12 of 18** accepted ([report](../eval/runs/2026-10-13-load-shedding.md)), final-whistle **17 of 22**
  ([report](../eval/runs/2026-10-13-final-whistle.md)); 29 of 40 together. Every accepted frame looked at: load-shedding 9 right, 2
  wrong (girls drawn as boys, L018), 1 split panel (L015); final-whistle 13 right, 4 weak or wrong
  (the Lionesses drawn as boys and team names blanked, L017; a crowd's chant drawn as one man).
  The warned frames show misspelt boards (FINAL MEATHS EXAM, 2 – son 1) with their warning.
  Of the 11 withheld shots, 9 are refused over a person and none over an object or lettering;
  2 ended in an audit error (load-shedding 5.2, final-whistle 5.3).
  stormwater (held out, after T091): **17 of 21** ([report](../eval/runs/2026-10-13-stormwater.md)); 8 right, 4 weak (1.1 no dog, 1.3
  a child of no clear sex, 4.4 a dry tunnel, 5.3 the ball in the wrong hand), 5 wrong, all in their
  people's sex (L018). Klein's misspelt lettering ("Only the arswerts", "MH. NOVE AC HOSE") warned;
  the 4 withheld shots are refused over a person (3.1, 6.1, 6.4) or the setting (5.1), none over an
  object or lettering.

### L013 · The place's own things fail: bread in a bakery, a van's dashboard inside the van · fixed (T086, measured free)

- **Seen:** 2026-10-12, the-bread-van (a test script Claude wrote for pronouns, not held out),
  [run report](../eval/runs/2026-10-12-the-bread-van.md). In failures: `food · never set dressing` 26 (bread loaves, loaves of bread, dough in INT.
  NOMSA'S BAKERY), `vehicle · never set dressing` 14 (rearview mirror, dashboard, headrests, car
  seats in INT. VAN - MOVING), held objects 10 (`held, so not set dressing`: 4 a steering wheel as a
  vehicle, 6 others, a steering wheel and a broom).
- **Cause:** `verify/audit.py` never lets food or a vehicle be set dressing (`_NEVER_DRESSING`), and
  T083's `named_in_scene` reads only the scene's action text and the object's own noun. The
  heading's place (BAKERY, VAN) is never asked, and a driver holding the van's wheel is a held object
  like any other.
- **Action:** none yet. To consider, measured free with `recheck`: a scene whose location is itself
  a vehicle (VAN, CAR, BUS, TAXI, BOAT, TRAIN) treats that vehicle's parts as the place's structure;
  food a heading's place sells or makes stays a question for Tumo (T072 made food always scripted).
- **Measured:** live, 2026-10-12, the-bread-van second run ([run report](../eval/runs/2026-10-12-the-bread-van-2.md)): `food · never set dressing` 26 → 0 and `vehicle · never set dressing` 14 → 8 (left: a car in the street, seat belts, a door handle; `held, so not set dressing` 10 → 1, a baking tray). Food still fails as `not in the script` 13 times (a tray of buns, baskets of bread at the spaza shop, where the heading names no bakery).

### L012 · The judge puts a character's name on someone it can't check · partly fixed (T086; T087 measured and parked)

- **Seen:** 2026-10-12, the-bread-van, [run report](../eval/runs/2026-10-12-the-bread-van.md): **1 of 19 shots accepted.** `unscripted_person` failed 35
  attempts, "a child" 21 times, in shots that have THEO, aged 9. Of the judge's 24 matches to THEO, 17
  were a person described as no child (an adult seen from behind, an adult man, an adult woman), and
  in 13 of those a drawn child was left unmatched and failed as a stranger. Counted the same way on
  every stored run with a child character: at most 1 such match a run on the eight runs since T074
  (0 on six, 1 on two; the-red-kite and lost-property). Two more attempts (4.2, 4.3) were `ERROR`: the judge didn't call each
  described person once. And DANIEL (40s) was drawn and matched as "an old man" (3.2, 3.3).
- **Cause:** klein drew Theo in a t-shirt, not his look "in pyjamas and a school jersey". The judge
  is told (T080) that a person whose look plainly contradicts a character's is not that character,
  so it moved the name to a person whose look it can't see, and code never checks that the matched
  person's age fits the introduction's.
- **Action:** none yet. To consider, measured free with `recheck`: a code age check (a character
  introduced under 13 matched to a person described as an adult, old or a teenager fails as that
  character; one introduced as an adult matched to "a child" too; "old" for a character under 50);
  and whether clothing of the moment ("in pyjamas") should be a reason to refuse a match at all.
- **Measured:** live, 2026-10-12, the-bread-van second run ([run report](../eval/runs/2026-10-12-the-bread-van-2.md)): of the judge's 19 matches to THEO, **0** went to a person described as no child (17 of 24 on the first run), and DANIEL drawn "an old man" now fails on his age (T086). But the judge now leaves the drawn boy unmatched instead: "a child" fails `unscripted_person` 17 times, and AUNTIE BETTY (4.1 attempt 3) and NOMSA (5.2 attempt 3) were left unmatched as "an old woman" and "an adult woman" in attempts whose only hard failure that was. **3 of 20 accepted** (1 of 19 on the first run). T087 next.
  **T087 measured, parked (Tumo, 2026-10-13):** each stored description judged again with today's
  sentence and with "clothing is no contradiction; only age, sex or a fixed trait (hair, build, a
  beard)" (Token Factory, judge only; re-judged on the stored descriptions, so not the live counts).
  Shots accepted, today's code: the-bread-van 8 → 9 and 5 → 5;
  held out, final-whistle 15 → 17 and load-shedding 13 → 13. The judge flips both ways on the same
  drawings (a lone boy in a THEO-only shot matched in one arm, refused in the other), so most of
  it is noise; the one steady gain is COACH DLAMINI matched in tracksuit-less drawings (3 times),
  and one loss is bad (final-whistle 5.4's boys for the Lionesses excused). A code rule matching
  the only unmatched child to the only child character gained a shot a run but accepted a Lerato
  with shoulder-length hair (the script gives braids). Neither is built.

### L011 · A stranger excused by a line of dialogue · fixed (measured free)

- **Seen:** 2026-10-12, lost-property (held out: no fix was designed on it), [run report](../eval/runs/2026-10-12-lost-property.md). Of 12
  accepted shots, three show a person the shot doesn't have, and the audit's hard
  `unscripted_person` passed each one:
  - **7.4:** the prompt draws one figure, Officer Moloi. The frame has three people: an old man
    (matched to Moloi), "an adult man seen from behind, walking away" (matched to TEBOGO, a character
    of the shot whom the prompt didn't draw), and "a small distant adult figure", supported by
    "Somebody might have." (dialogue).
  - **10.3:** "an adult bent forward at the waist in the far background", supported by "Sorry, my
    friend. He's already got a home." (dialogue).
  - **10.2:** "an adult standing small in the distance" and "a child, tiny and partly visible",
    both supported by "A pigeon glares at him." ("him" is Koos).
- **Cause:** a person's support is checked to be a verbatim quote of the shot's text. That text
  includes the shot's dialogue. T072 refuses a support that **names** a shot character, but "him"
  names no one. A line someone says puts nobody on screen, as verify.md §3 already says for things
  (`named_in_scene` reads only action text). In 7.4, matching a figure to TEBOGO is what the design
  allows (he is in `shot.characters`, addressed in the dialogue), though the prompt drew only
  Moloi.
- **Action:** T084 (verify.md §3): an unmatched person's support must be found in the shot's own
  action text, and must have no `he`, `him` or `she`. Whether a character the prompt didn't draw may
  be matched (7.4's TEBOGO) is still a separate question.
- **Measured:** free, `recheck` on every stored audit with T084's code. lost-property 12 → 9 shots
  with an accepted attempt: 7.4, 10.2 and 10.3 now fail `unscripted_person`. **Not designed on:**
  sipho-and-siphokazi (2026-10-11) 12 → 11 (9.3, an old woman for Siphokazi excused by "He takes the
  tide book from her"; 6.1, a man excused by another shot's quote), the-red-kite runs 35 → 33, 16 → 15
  and 10 → 9 (strangers excused by "my girl", "Is that my good shirt you are flying?" and "He
  switches off the soldering iron."), every other project unchanged. Every newly failed attempt was
  read; none is a person the shot's action introduces. Still to see: a new drawing run on the
  held-out script.

### L010 · T082 finds a sex for a third of the characters on a script it wasn't designed on · improved (T088)

- **Seen:** 2026-10-12, lost-property (held out), [run report](../eval/runs/2026-10-12-lost-property.md). Scored free on the run's own stored
  extraction against `eval/sex-labels.json`: **WRONG 0, INVENTED 0**, RIGHT 6 (Zanele, Mr. Dube,
  Grace, and Officer Van Wyk, Sam and the Announcer, whom the script never sexes; Marmalade, the
  cat, isn't labelled), **MISS 6** (Priya, Koos, Tebogo, Amahle, Officer
  Moloi, the sleeping commuter). So 3 of the 9 characters whose sex the script states got it.
  Two misses reached the board: **4.1** draws Priya as a young man (the describer: "a teenager
  with dark hair") and **6.2** draws Amahle (8) as a boy ("child, a young boy"), and both were
  accepted. The describer wrote "a teenager" and "a young boy"; with no
  `sex (from the script)` line, the judge matched them to the girls.
- **Cause:** T082 fails closed on purpose (storyboard.md §6, grounding.md §3): "she"/"he" count
  only in the introducing sentence, "her"/"his" only inside the introduction's own look, and
  `sex_word` is a noun (woman, fisherman…), never a pronoun. Here the sex sits outside all three:
  "She spots the hand-painted sign" (Priya, shot 3.3, after her introducing sentence in 3.1), "He
  wears headphones" (Koos, the sentence after his), and only "his"/"her" outside a look for Tebogo
  ("at his feet"), Amahle ("her mother's scrubs"), Moloi ("(closing his notebook)") and the
  sleeping commuter ("under his newspaper"). None of them has a sex noun or a title.
- **Action:** none yet. The six misses are the held-out test set, so no fix is tuned to them: a
  fix is designed on the samples' own patterns and scored here again, separately. The rule that
  WRONG and INVENTED stay at 0 holds.
- **Measured:** T088 (2026-10-12, #149 design, #150 code), Token Factory, three extractions of each
  sample: **WRONG 0, INVENTED 0** in all twelve; lost-property 6 → 7 of 12 a run, the-bread-van 2 → 3 of
  4 (DANIEL), sipho-and-siphokazi every extracted person (SIPHO, SIPHOKAZI). The model's `sex_word` was
  right for every person; only the quotes it gave were bad, so it is now a claim the script's own
  subject pronouns must support. Still missed: PRIYA, TEBOGO and KOOS (no claim, or "She" only after
  her speeches), MOLOI (a parenthetical), THEO, the sleeping commuter. Held-out script next.
  Live, 2026-10-12, the-bread-van second run: NOMSA, DANIEL and AUNTIE BETTY right, 0 wrong, **3 of 5** found: THEO missed again, and TAXI
  DRIVER (labelled now: "leans on his taxi", a possessive outside a look).
- **Before T088:** this is the held-out baseline: 3 of 9 found, 0 wrong. Also 2026-10-12, the-bread-van
  (Claude's test script, every sex stated the conventional way; [run report](../eval/runs/2026-10-12-the-bread-van.md)): Nomsa (her look) and Auntie
  Betty (the title) right, **Theo and Daniel missed** ("sleeps across his feet", "He stretches"), 0
  wrong. T085's code-only design was stopped on review: surface rules can't tell whose "his" or "her"
  it is ("Siphokazi takes his hand", "Sipho turns to her"). The Token Factory
  measurement on the three samples (several extractions each) is still to run.

### L009 · Object failures were catching wrong people by accident · open

- **Seen:** 2026-10-11, measuring T083 with `recheck` on the stored audits of
  [sipho-and-siphokazi](../eval/runs/2026-10-11-sipho-and-siphokazi.md). Of the attempts T083
  turns from fail to accepted, three show Siphokazi wrong: 4B.1 attempt 3 and 8.2 attempt 1 as a
  boy, 5.1 attempt 3 as a grown man hauling the rope she grabs in the script. Their scripted things
  (4B.1's compass, radio, taped photograph and wheel) or everyday background used to fail as
  objects, and that alone kept the wrong person off the board.
- **Cause:** with no sex in the prompt or the spec (L002), the judge can't refuse a girl drawn as
  a boy; a strict object check withheld such frames for an unrelated reason.
- **Action:** T083 waits for T082 before it goes live (merge order T082, then T083), so a wrong
  sex is refused for its own reason. Lesson: when a strict check is relaxed, look at every frame
  it lets through, not only the count.
- **Measured:** T083's first version on the stored audits (`recheck --target storyboard`):
  sipho-and-siphokazi 7 → 13 of 30 shots with an accepted attempt, the-red-kite 16 → 19 of 21; of
  the 10 flipped attempts looked at as drawings, 7 correct (the-red-kite 2.1, 2.2, 3.1, 4.4; sipho
  4A.1, 7.1, 9.2) and 3 wrong, all the wrong sex (sipho 4B.1, 5.1, 8.2). After the code review's
  stricter matching (a part is named by its whole only), sipho is 7 → 12: 4B.1's "steering
  wheel" is no longer excused, so that wrong frame stays withheld; 5.1 and 8.2 still pass.

### L008 · The word budget drops what the characters do · open

- **Seen:** 2026-10-11, sipho-and-siphokazi,
  [run report](../eval/runs/2026-10-11-sipho-and-siphokazi.md). Shot 2.1's prompt keeps the
  setting ("A tin-roofed shack… Buckets of sardines on ice. A calendar… curls on the wall.") and
  the two ages, but not the line that says what they do ("SIPHOKAZI (17)… counts coins onto the
  counter. MAMA THEMBI (60s)… watches her…").
- **Cause:** `build_frame_prompt`'s 55-word budget (`storyboard/prompt.py` `_fit`) keeps the
  action parts in order and cuts from the end, so a shot whose text opens with setting loses its
  people's actions first.
- **Action:** none yet. To consider: rank a sentence that names a visible character before one
  that doesn't when cutting.
- **Measured:** not yet.

### L007 · The audit is the expensive part of a run · open

- **Seen:** 2026-10-11, the-red-kite and sipho-and-siphokazi,
  [run report](../eval/runs/2026-10-11-the-red-kite.md) and
  [run report](../eval/runs/2026-10-11-sipho-and-siphokazi.md). the-red-kite: 38 audits, 143,679
  prompt and 80,697 completion tokens. sipho-and-siphokazi: 82 audits, 295,459 prompt and 190,974
  completion tokens, about 2,300 completion tokens an audit.
- **Cause:** two Token Factory calls an audit (the describer, then the judge), and up to 3
  drawings a shot.
- **Action:** none yet. Size the hosted demo's `LLM_MONTHLY_TOKEN_CAP` (T030) from these numbers:
  a 30-shot script at 3 attempts can use about 500,000 tokens.
- **Measured:** not yet.

### L006 · A storm doesn't support lightning · open

- **Seen:** 2026-10-11, the-red-kite and sipho-and-siphokazi,
  [run report](../eval/runs/2026-10-11-the-red-kite.md) and
  [run report](../eval/runs/2026-10-11-sipho-and-siphokazi.md). the-red-kite 3.2 withheld for
  "lightning bolts" in a storm; sipho-and-siphokazi's `nature · unscripted` (23 failures) includes
  "lightning bolt" and "storm clouds".
- **Cause:** the judge reads weather as an event (T072) but not what the event shows.
- **Action:** none yet (docs/HANDOFF.md §6 step 6).
- **Measured:** not yet.

### L005 · Everyday things of a place fail as unscripted · open

- **Seen:** 2026-10-11, sipho-and-siphokazi and the-red-kite,
  [run report](../eval/runs/2026-10-11-sipho-and-siphokazi.md) and
  [run report](../eval/runs/2026-10-11-the-red-kite.md). sipho-and-siphokazi, in failures:
  `other · unscripted` 36 (pen, rope, life ring, wristwatch), `nature · unscripted` 23 (grass,
  moon, rocks), `food · never set dressing` 8 (apples, a basket of food, a bowl of fruit).
  the-red-kite: 3 of its 5 withheld frames (a picture frame, a toaster, a mug).
- **Cause:** the judge calls a thing set dressing only when the heading's location would hold it,
  and code never lets food, vehicles, animals or weapons be set dressing
  (`verify/audit.py` `_NEVER_DRESSING`).
- **Action:** T083 (Tumo's call, 2026-10-11): an everyday thing nobody holds and the script
  doesn't mention (other, nature, furniture, sign) warns as `background_object` instead of
  withholding. (docs/HANDOFF.md §6 step 3: a judge wording that called everyday things set
  dressing gained nothing and let a wrong person through; this is a code rule instead.)
- **Measured:** with T083, sipho-and-siphokazi 7 → 12 of 30 and the-red-kite 16 → 19 of 21 shots
  with an accepted attempt (`recheck`, stored audits); see L009 for the wrong-sex frames it let
  through, and L003.

### L004 · Painted text the script didn't write · open

- **Seen:** 2026-10-11, sipho-and-siphokazi,
  [run report](../eval/runs/2026-10-11-sipho-and-siphokazi.md): `text_in_frame` failed 42 attempts and withheld 12
  shots in the end: boat names, shop signs ("MILK", "Café"), numbers ("7.5.82", "9:15").
  `signature` warned on 55 attempts.
- **Cause:** klein letters signs and hulls on its own; only legible words the script didn't
  write fail (T071).
- **Action:** none yet.
- **Measured:** not yet.

### L003 · Parts of things the shot's text names fail · open

- **Seen:** 2026-10-11, sipho-and-siphokazi: `vehicle · never set dressing` 31 failures (boats,
  boat masts, a dashboard). Shot 1.1's text is "a single row of forty-year-old wooden
  fishing-boats", and its frame's "fishing boats" passed while its "boat masts" failed.
- **Cause:** `verify/audit.py` `part_of_prop` (T078) counts a part only of an extracted prop of
  the shot, and never of a vehicle, animal, weapon or food. The judge called the masts set
  dressing, which a vehicle never is.
- **Action:** T083: an animal, vehicle, weapon or food the scene's action text names is scripted
  (its own noun, or a part's whole: `boat masts`); everyday unheld background objects warn
  (Tumo's call). The rule over all categories was measured first and rejected: it excused
  "small pills", "power lines" (the script's washing lines) and "tripod stand".
- **Measured:** `recheck` on the stored audits: sipho-and-siphokazi 7 → 12 of 30 shots, the-red-kite
  16 → 19 of 21. 2 of the 9 newly accepted attempts are wrong-sex frames (L009), so T083 goes
  live after T082. Held out (earlier the-red-kite runs, stored verdicts from older code): 12 → 18
  and 15 → 16. Not yet on a script T083 wasn't designed from (held out).

### L002 · No sex from the script: wrong people drawn, and one accepted · open

- **Seen:** 2026-10-11, sipho-and-siphokazi: 7 of 30 accepted. The report's Characters table
  gives no sex for any of the five characters. `unscripted_person` failed 28 attempts: "an old
  man" 10, "a teenager" 8, "an adult man" 6. **8.3 was accepted (warn) with an old woman and a
  boy** where the script has Sipho (50s) taking the tide book from Siphokazi (17).
- **Cause:** `storyboard/prompt.py` `introduced_sex` (T079) reads only "she"/"he" in the
  introducing sentence and "her"/"his" in its look. Here: `SIPHOKAZI (17), in a school jersey…
  MAMA THEMBI (60s), the shop's owner, watches her…` (no pronoun of their own), and `a
  salt-and-pepper-bearded fisherman… This is SIPHO (50s).` (the noun is in the sentence before).
  With no sex, the judge (T080) can't refuse a wrong one, so 8.3 passed. Also seen: that
  introduction reaches the prompt as "This is a person (50s)".
- **Action:** T082 (planned; Tumo chose, 2026-10-11): code rules for a title (MAMA, MR, MRS…) and
  a sex noun in the introduction (fisherman, woman, girl…), plus a grounded extraction field
  whose quote code checks.
- **Measured:** not yet. Re-extract (Token Factory) and re-audit the stored drawings, then one new
  run (about $0.40 on fal, ask first).

### L001 · Lerato drawn as a boy · fixed

- **Seen:** 2026-10-11, the-red-kite before T079: klein drew Lerato as a short-haired boy in 9 of
  11 accepted frames (storyboard.md §8), and 1.3 was an empty roof.
- **Cause:** the prompt gave her age (T074) but no sex or look.
- **Action:** T079 (#127, #128): the sex from the introduction's pronouns and the look verbatim;
  T080 (#129, #130): the judge refuses a wrong sex or look, and a frame with none of the drawn
  people fails.
- **Measured:** after, 2026-10-11 ([run report](../eval/runs/2026-10-11-the-red-kite.md)): 16 of
  21 accepted (15 of 22 before), Lerato a girl with braids in every frame looked at, 1.3 shows
  her.
