# `Panelwise` — Specification (the WHAT)

**Related:** [PLAN.md](PLAN.md) (the HOW) · [TASKS.md](TASKS.md) (the backlog) ·
[docs/design/](docs/design/) (the shapes) · [SCOPE.md](SCOPE.md) (problem, persona, milestones)

Nothing here is new: every requirement restates PLAN.md or an agreed design doc, and names its
source in brackets. Where the sources don't decide something, it is listed under
[Open questions](#open-questions) instead of being decided here.

---

## Overview

Panelwise turns a screenplay into a shot-by-shot storyboard and then into a comic book. A person
uploads a screenplay PDF in the web app; NVIDIA Nemotron on Nebius Token Factory extracts the
characters, props and locations and plans the shots, FLUX.2 [klein] on fal.ai renders one frame per
shot (ComfyUI on a Nebius GPU was cut on 2026-10-19, never built, T003), and every frame is audited before
anyone sees it: **Nemotron 3.5 Super VL describes each frame; Nemotron Super judges it against the
script** and a failing frame is re-rendered. The output is a
storyboard (in the app and as a PDF) and comic pages with speech bubbles lettered from the script's
dialogue (in a reader and as a PDF). [PLAN.md § Summary; docs/nebius-findings.md § The vision
decision, option A; verify.md §8]

**The rule everything below serves (PLAN.md Non-negotiable 1):** a storyboard frame or comic panel
never shows a character, prop, line of dialogue or event that is not in the screenplay. Every panel
traces back to a verbatim source span, and every audit verdict is logged. A failed hard check
withholds the frame only when it is on the rule ladder, `AUDIT_WITHHOLD_CHECKS` (code default: every
hard check; hosted: `drawn_sex,no_character,split_panels`); a frame that fails any other hard check
is shown marked warned, with the check named, never as passing. [verify.md §4; T094]

### Goals

- **Grounded extraction:** every character, prop and location shown quotes the script verbatim at a
  located page/line span; anything that can't be located is dropped, never shown. Faithfulness and
  recall are reported together. [grounding.md §1, §4]
- **A shot list that covers the whole script:** every element of every scene lands in exactly one
  shot, so no line of dialogue is left without a panel. [shots.md §1, §3]
- **One audited frame per shot,** in a public style, re-rendered on a failed audit within a retry
  cap, with every attempt's description and verdict in an audit log the user can open.
  [PLAN.md Phase 4; verify.md §4]
- **Comic pages** whose every letter is verbatim script text with its span. [comic.md §1]
- **Consistent characters** across panels, drawn only from the script's own words about them.
  [characters.md §1, §3]
- **Stay inside the credits:** a full script under about $0.10 of Token Factory credit (measured on
  the-red-kite, 2026-10-16: about $0.15, at most $0.19; about $0.30 with fal); LLM and image spend
  capped in code. [PLAN.md Non-negotiable 2, § Technical Context]
- **Nemotron visibly load-bearing:** extraction, shot planning and the audit's judgement (which described
  person is which character, whether an object is scripted) run on Nemotron on Token Factory; the
  countable checks and the verdict are code. [RUBRIC.md; verify.md §3, §8]

### Non-goals

Out of scope for this event; written down so nobody quietly builds them. [SCOPE.md § Out of scope]

- Editable panels (redraw one frame with a note), animatics with scratch audio, exporting shot lists
  to scheduling tools.
- Self-hosting an NVIDIA vision model on the Nebius GPU (vision option B): not needed since
  Nemotron 3.5 Super VL on Token Factory describes the frames (T105), and there is no Nebius GPU
  (T003 cut). [docs/nebius-findings.md § The vision decision]
- A multi-provider LLM fallback chain: Token Factory only.
- Private style packs in the demo: the public repo runs everything the demo shows. [PLAN.md
  Non-negotiable 2]
- Any copyrighted screenplay in the repo, the demo or the video.
- Character attributes the script doesn't state (age, gender, ethnicity, skin tone), including
  FrameFlow's "director choices"; appearance notes only ever as explicitly user-entered, labelled
  fields, and not until someone asks. [grounding.md §8; characters.md §8, §10]
- Narration captions from action lines, and sound effects. [comic.md §1, §8]
- Right-to-left reading order. [comic.md §10]
- Scripts without a text layer (scans): refused. [script.md §4]

---

## Actors

### The end user: a writer-director with a script and no storyboard artist

[SCOPE.md § Who it's for]

1. Signs in to the web app (Supabase Auth). [deploy.md §1, §4; T009]
2. Uploads a screenplay PDF.
3. Sees the scenes, characters and locations, each with its verbatim quote and page/line span; then
   the shot list. [DEMO.md golden path 3–4]
4. Watches frames render, one per shot; opens the audit log to see why each frame was accepted,
   re-rendered or withheld. [DEMO.md 5–6]
5. Exports the storyboard PDF; switches to the comic reader; exports the comic PDF. [DEMO.md 7–8]
6. Clicks any frame, panel or bubble to see the script lines it came from. [DEMO.md 9]

**Success, in their terms:** a frame they can hand to a crew without checking it against the script
first, because nothing in it was invented.

### The hackathon judges

Judges score from the public repo, the hosted demo and a video of 3 minutes or less, between 1 and
15 Dec 2026, with no live pitch. [RUBRIC.md; DEMO.md; event.toml]

- They sign in with a **seeded judge account** whose project is already rendered, so they see a
  full storyboard and comic without spending credit or waiting on a GPU. [DEMO.md § Fallbacks; T030]
- The hosted demo stays up, free and unrestricted, until 15 Dec, behind spend caps and upload
  limits so a judge can't drain the credit. [DEMO.md § Fallbacks; deploy.md §1; T030]

**The rubric** (Devpost, four criteria, equal weights of 25; `event.toml [rubric]`, mapped to
evidence in [RUBRIC.md](RUBRIC.md)):

| Criterion | What it asks of this spec |
|---|---|
| Technological Implementation | Nebius Token Factory and Nemotron used effectively: extraction, shot planning, the frame description (Nemotron 3.5 Super VL) and the audit judge on Nemotron; rendering by FLUX.2 [klein] on fal.ai, since Token Factory serves no image model (findings U5) |
| Design | a complete product experience, not a proof of concept: US1–US3 in the web app, both PDFs, the audit log |
| Potential Impact | evidence it works for the persona, on public-domain or self-written scripts: faithfulness, recall and frame-audit accuracy numbers (T032; the audit on 109 hand-labelled frames, T124) |
| Quality of the Idea | a non-obvious use of Nemotron: grounding enforced in code, Nemotron as the judge of an image-audit loop |

**Honesty rule for every claim a judge reads:** the audit is two steps on two models. Since
2026-10-17 the *describe* step runs on `nvidia/Nemotron-3.5-Super-VL` with thinking off (T105,
findings U8); before that no Nemotron model on Token Factory accepted images (findings U7) and it
ran on `deepseek-ai/DeepSeek-V4.1-Flash`. The judge never sees the image. The approved wording is
*"Nemotron 3.5 Super VL describes each frame; Nemotron Super judges it against the script."*
Never "Nemotron vision auditor", which suggests one model does both. [verify.md §8;
docs/super-vl-migration.md; RUBRIC.md]

---

## User stories

Priorities follow PLAN.md § Build phases: US1 is Phase 3 on its own and is the MVP (**P1**); US2,
US3 and US4 are all Phase 4 (**P2**); US4 was cut on 2026-10-19 (T025). US5 is a **stretch**
(Katlego, 2026-10-17): built only after the submission path is safe, never on it. Within P2,
STATUS.md's timeline built US2 in week 3 and US3 in week 4 (see Open questions).

Each scenario becomes an acceptance test ([docs/testing-strategy.md](docs/testing-strategy.md));
a task's `Verify:` line names the scenario it satisfies.

### US1 — Turn a screenplay into a grounded storyboard (P1)

**As a** writer-director, **I want** to upload my screenplay and get a storyboard with one frame
per shot, **so that** my crew can see the film before it is shot, without a storyboard artist.

[PLAN.md Phase 3; SCOPE.md week 2; T005–T009; script.md, grounding.md, shots.md]

```
Scenario: A screenplay becomes a storyboard
  Given a signed-in user and a self-written screenplay PDF with a text layer
  When  they upload it
  Then  the scenes, characters and locations appear, each with a verbatim quote and its page/line span
  And   the shot list appears, every shot citing the lines it covers
  And   one frame per shot renders in a public style
  And   the storyboard exports as a PDF
```

- **Scenario: every frame traces to the script** — Given a rendered storyboard, when the user
  clicks a frame, then the verbatim script lines it came from and their page/line span are shown.
  [PLAN.md NN1; DEMO.md 9; shots.md §3 `source`, `span`]
- **Scenario: an entity the script doesn't support is dropped** — Given the model proposes a
  character whose quotes can't be located in any single script element, when extraction runs, then
  that entity is dropped with a reason and never shown; an entity with one bad quote keeps its
  located ones. [grounding.md §4]
- **Scenario: the report shows what was missed, not only what was right** — Given an extraction,
  when it finishes, then faithfulness (grounded ÷ proposed) and recall (speaking cues found by the
  model ÷ speaking cues) are reported together, and speaking characters the model missed are still
  added to the cast from their cues. [grounding.md §3–§4]
- **Scenario: no line of the script is left without a shot** — Given a scene of *n* elements, when
  shots are planned, then each element is in exactly one shot, in order, even when the model's
  proposed ranges overlap, leave gaps or run out of bounds (they are repaired and counted). A scene
  with no elements gets one shot citing its heading. [shots.md §3–§4]
- **Scenario: a shot can't smuggle in a character** — Given the model names a character or prop not
  extracted for that scene, when the shot is built, then the name is dropped, never drawn, and
  counted in the plan report. [shots.md §3, §8]
- **Scenario: the time of day comes from the script** — Given a scene headed `CONTINUOUS` after a
  night scene, when its shots are planned, then their time of day is the resolved night, not the
  model's guess. [shots.md §2–§3]
- **Scenario: a scanned PDF is refused** — Given a PDF with no text layer, when it is uploaded, then
  parsing fails with "no text layer", never an empty screenplay that looks like success. Likewise a PDF with no scene
  headings, or a malformed PDF. [script.md §4]
- **Scenario: a failed model call fails loudly** — Given one extraction chunk's or one scene's
  shot-planning call fails after its repair retry, when the job runs, then the whole job fails
  naming the chunk or scene; no partial storyboard with a silent gap is shown. [grounding.md §4;
  shots.md §4]
- **Scenario: a script too long for the budget is refused before it costs anything** — Given a
  script that needs more than the extraction chunk limit, when it is uploaded, then extraction is
  refused before any model call is made. [grounding.md §4]

**Acceptance criteria:**
- [ ] Every entity, shot and frame shown carries a verbatim quote or source text located to a
  page/line span.
- [ ] Faithfulness and recall are shown for every extraction.
- [ ] Every scene element is covered by exactly one shot.
- [ ] Only public styles are used; the storyboard exports as a PDF.
- [ ] Progress survives an API restart (a `Job` row in Postgres). [deploy.md §3, §5]

### US2 — Audit every frame against its shot before anyone sees it (P2)

**As a** writer-director, **I want** each frame checked against its shot and re-rendered when it
shows something the script doesn't, **so that** I can trust a frame without checking it myself.

[PLAN.md Phase 4; SCOPE.md week 3; T010, T020, T021; verify.md]

```
Scenario: A frame that matches its shot is shown, with its audit
  Given a rendered frame for a shot
  When  the vision model describes it, blind to the shot, and Nemotron judges the description against the shot's grounded spec
  And   every hard check passes
  Then  the frame is shown (PASS, or WARN if only soft checks failed)
  And   the audit log holds the description, the judgement, every check and the verdict
```

- **Scenario: an unscripted person triggers a re-render** — Given a frame with a person the judge
  can't match to one of the shot's characters and who has no verbatim support in the shot's source,
  when it is audited, then the verdict is `FAIL` (`unscripted_person`) and the shot is re-rendered
  with a new deterministic seed. Two people called as the same character count the same way.
  [verify.md §3 checks, §4]
- **Scenario: an unscripted animal or weapon, or the wrong setting, fails** — Given a frame
  showing an unscripted animal or weapon, or an exterior in an `INT` scene, when it is audited, then
  the verdict is `FAIL` (`unscripted_object`, `setting`). Any other unscripted object, and any
  letters or text, only warn (`background_object`, `text_in_frame`; T083, T089). [verify.md §3]
- **Scenario: "supported by the script" needs a verbatim quote** — Given the judge says an unnamed
  person or object is supported but its `support` quote is not found in the shot's source or
  entities' quotes (or, for set dressing, the scene heading), when checks run, then it counts as
  unscripted. [verify.md §3]
- **Scenario: a quality miss is logged, not blocking** — Given a frame that only misses a character,
  has day light in a night scene, or is framed two or more steps off, when it is audited, then the
  verdict is `WARN`, the frame is shown, and the soft checks are logged and visible. Transitional
  times (dawn, dusk) and `unclear` always pass. [verify.md §3]
- **Scenario: a frame that keeps failing is withheld, shown as a text card** — Given a shot whose
  three renders (the first plus two re-renders) all fail a hard check on the withhold ladder
  (`AUDIT_WITHHOLD_CHECKS`), when the loop ends, then no frame is
  shown; the storyboard shows a text card with the shot's verbatim source, its span and "Frame
  withheld: failed audit (unscripted person)" (naming the failed check), and the user can ask for
  another attempt, audited the same way. [verify.md §4–§5]
- **Scenario: an audit that can't run never passes a frame** — Given the describer or judge call
  fails, or the judgement skips, repeats or mis-indexes a described person or object, when the
  audit runs, then the audit is `ERROR`, it is logged, and the frame is withheld. [verify.md §3–§4]
- **Scenario: the describer can't just agree** — Given any audit, when the vision model is called,
  then its request carries the image and a neutral instruction and no shot details. [verify.md §3,
  §9]
- **Scenario: the audit log is visible in the app** — Given a storyboard in which a frame was
  re-rendered, when the user opens the audit log, then each attempt shows the vision model's
  description, Nemotron's verdict and each check. [DEMO.md 6; T021]
- **Scenario: the renderer fails** — Given the renderer errors, when a frame is rendered, then the frame
  job fails (`FAILED`); nothing is shown unaudited. [verify.md §4]

**Acceptance criteria:**
- [ ] No frame is displayed unless its audit is `PASS` or `WARN`, or it failed only hard checks off
  the withhold ladder (shown marked warned, the checks named); no state transition skips the audit.
- [ ] At most 3 renders per frame by default; every attempt, pass or fail, is a row in the audit log.
- [ ] Every audit decision is Nemotron's or code's; the vision model only describes.
- [ ] Frame-audit accuracy is measured on a labelled set and reported in the README: 109 frames
  labelled by hand (T124, `eval/measurements/t124/`); T049's injected set was closed 2026-10-12.
  [verify.md §9]

### US3 — Lay the script out as comic pages with speech bubbles (P2)

**As a** writer-director, **I want** the same script as comic pages with the dialogue in speech
bubbles, **so that** I get a second, readable form of the story that is held to the same rule.

[PLAN.md Phase 4; SCOPE.md week 4; T011, T022–T024; comic.md]

```
Scenario: A shot plan becomes comic pages
  Given a planned and audited script
  When  the user opens the comic
  Then  pages show one panel per shot in plan order, sized by story beat
  And   each line of dialogue the shot covers is in one bubble or caption, lettered byte for byte as the script has it, with its span
  And   the pages read in the web reader and export as one PDF
```

- **Scenario: dialogue is lettered verbatim, never cut** — Given a panel with more dialogue than
  fits, when it is laid out, then the panel grows (up to three relayouts, then a tier of its own);
  text never drops below 28 px and is never truncated, paraphrased or dropped; if it still can't
  fit, the comic job fails naming the shot. [comic.md §4 step 5, §8]
- **Scenario: voice-over and off-screen speech** — Given a line with extension `V.O.` (including
  `V.O./CONT'D`), then it is a caption box with no tail; with `O.S.`, `O.C.` or `OFF`, then an
  off-panel bubble whose tail points to the panel edge; any other extension is ordinary speech.
  [comic.md §3]
- **Scenario: only the script's words are on the page** — Given any comic page, then action lines,
  parentheticals and sound effects are not lettered, and the scene caption on a scene's first panel
  uses only the heading's location and, when it has a real clock, its time (`CONTINUOUS` is never
  lettered). [comic.md §1, §3]
- **Scenario: a withheld panel still carries its dialogue** — Given a panel whose frame was withheld
  by the audit, when the page is rendered, then the panel shows the comic's withheld card ("Frame
  withheld: failed audit (<failed hard checks>)" and the script page/lines), its bubbles are still
  placed, and the card does not repeat the source text. [comic.md §4 step 6]
- **Scenario: bubbles don't hide the speaker and read in order** — Given an accepted frame, when
  bubbles are placed, then they sit in low-detail areas away from the speaker's third, never
  overlap, and follow reading order; the speech tail points at the speaker's position from the
  audit. [comic.md §4 steps 7–8]
- **Scenario: every bubble traces to the script** — Given the comic reader, when the user clicks a
  bubble or panel, then the reader shows the page and lines it came from. [comic.md §6; DEMO.md 9]
- **Scenario: no crop cuts anyone out** — Given a panel of any shape, when its frame is made, then
  it is rendered and audited at exactly the panel's size, never cropped from the storyboard frame.
  [comic.md §3, §8]

**Acceptance criteria:**
- [ ] Every `Dialogue` of every shot is in exactly one bubble or caption whose text equals it and
  whose span is its span; no other text appears except heading-built scene captions.
- [ ] Panels are rendered through the same audit as US2; a withheld frame is never drawn.
- [ ] Pages are 1988 × 3075 px; the reader, the PDF and the layout JSON agree. [comic.md §2, §6]

### US4 — Keep each character looking the same from panel to panel (P2; cut 2026-10-19, T025)

**Not built.** A character's look comes from the script's own words in every frame prompt (T079);
T012's design (characters.md) stays, unbuilt. The story below is kept as designed.

**As a** writer-director, **I want** a character to look the same in every frame and panel, **so
that** the crew and the reader can follow who is who.

[PLAN.md Phase 4; SCOPE.md week 3; T012, T025; characters.md]

```
Scenario: A reference portrait keeps a character consistent
  Given a character the script describes in an action paragraph
  When  their portrait is rendered from those quotes, with every name redacted, and passes its audit (exactly one person, no text)
  Then  the portrait is used as an image reference in every frame the character appears in
  And   the character is recognisably the same across panels
```

- **Scenario: an undescribed character stays undescribed** — Given a character the script never
  describes (for example one known only from a dialogue cue), when their portrait is made, then it
  uses a neutral prompt with nothing inferred, and the app says "the script doesn't describe
  <NAME>". [characters.md §3 rule 3]
- **Scenario: only action lines describe a character** — Given quotes about a character located in
  dialogue or a scene heading, when the portrait prompt is built, then those quotes are excluded, and
  no age, gender, ethnicity or skin tone is added unless those words are in a quote. [characters.md
  §3 rule 2]
- **Scenario: no name reaches an image model** — Given "NANDI (60s, oilskin coat) pours tea", when it
  enters an image prompt, then it reads "a person (60s, oilskin coat) pours tea"; another
  character's name becomes "another person". This holds for every portrait and frame prompt.
  [characters.md §3 rules 1–2, §9]
- **Scenario: a portrait that keeps failing is withheld** — Given three portrait renders that fail
  their audit, when the loop ends, then the portrait is withheld, that character's frames render
  without a reference, and the app says so. [characters.md §4]
- **Scenario: a crowded shot** — Given a shot with three or more characters, when references are
  chosen, then only two get one (speakers first, by first speech), placed left and right, and the
  frame's provenance says the rest come from the prompt alone. [characters.md §4]
- **Scenario: the GPU box is missing the reference nodes** — Given ComfyUI lacks the IP-Adapter
  nodes or models, when a frame job starts, then it fails naming what is missing; it never silently
  renders without references. [characters.md §4]

**Acceptance criteria:**
- [ ] No image prompt contains any character's name token.
- [ ] Portraits are used as references only when audited `READY`.
- [ ] Undescribed characters are flagged in the UI.

---

### US5 — Listen to the comic (stretch)

**As a** reader of the comic, **I want** to hear it read aloud in a voice I choose, **so that** I
can follow the comic by ear as well as by eye.

[docs/design/narration.md; T113. Stretch: off without `ELEVENLABS_API_KEY`; built only after the
submission path is safe. Revised 2026-10-20 (Katlego): one voice of four, chosen by the reader]

```
Scenario: The comic is read aloud in reading order
  Given a finished comic and narration turned on
  When  the reader chooses a voice and presses Listen
  Then  every lettered line is spoken in reading order, byte for byte as lettered
  And   every line and every scene caption is in the chosen voice
  And   the line being read is highlighted, and the page turns when the next line is on it
```

- **Scenario: nothing is spoken that isn't lettered** — Given any comic, when it is narrated, then
  the spoken text is exactly the lettering's (no action lines, no speaker names, no summary, no
  audio tags, a whispered or shouted balloon's text unchanged), so every clip traces to its line's
  verbatim span. [narration.md §1; PLAN.md Non-negotiable 1]
- **Scenario: the reader chooses the voice** — Given narration turned on, then the reader offers
  four voices, two female and two male; whichever is chosen reads the whole comic. Nothing about a
  character picks a voice. Given a voice already made for this comic, then Listen plays it without
  a new call. [narration.md §1, §3]
- **Scenario: narration is off without its key** — Given no `ELEVENLABS_API_KEY`, then the reader
  shows no voices and no Listen control, and every other behaviour is as before. [narration.md §4]
- **Scenario: the month's narration is spent** — Given the month's characters would pass
  `NARRATION_MONTHLY_CHARACTER_CAP`, when narration is asked for, then it is refused before any call.
  [narration.md §4; limits.md §4]

**Acceptance criteria:**
- [ ] Every clip's text equals its lettering's text.
- [ ] Every clip of a narration is in the voice the reader chose, one of the four.
- [ ] A line already spoken in a voice is never paid for again.
- [ ] Without the key the app behaves exactly as before.

---

## Acceptance criteria (system-level)

- [ ] **Non-negotiable 1:** every storyboard frame and comic panel traces to a verbatim source span;
  every audit verdict is logged; nothing unscripted is shown. [PLAN.md]
- [ ] **Credits:** a full script costs under about $0.10 of Token Factory credit (measured: about
  $0.15, at most $0.19); LLM and image spend are capped in code; one frame renders in seconds, not minutes. [PLAN.md NN2, §
  Technical Context]
- [ ] **Honest wording** in README, the Devpost story, the video and the app: Nemotron 3.5 Super
  VL describes each frame; Nemotron Super judges it. [verify.md §8; docs/super-vl-migration.md]
- [ ] **Public repo runs the demo:** everything the demo shows runs from the public repo with public
  styles; the repo carries an OSI licence (Apache-2.0). [PLAN.md NN2, § Technical Context]
- [ ] **Samples:** only public-domain or self-written screenplays in the repo, demo and video.
  [PLAN.md § Technical Context; SCOPE.md]
- [ ] **Hosted demo** on Vercel + Render + Supabase, with a seeded judge account whose project is
  pre-rendered, spend caps and upload limits, up until 15 Dec 2026. [deploy.md; DEMO.md; T030]
- [ ] **Measured:** faithfulness, recall and frame-audit accuracy numbers in the README. [T032 extraction, T124 audit]
- [ ] **Submission:** a video of 3 minutes or less, submitted on Devpost by 29 Oct 2026 (deadline
  30 Oct 10:00 PDT). [PLAN.md § Summary; event.toml]

---

## Open questions

Undecided in PLAN.md and the design docs; listed here so no implementer decides them silently.

1. **Unaudited frames at the US1 checkpoint.** PLAN.md makes US1 (storyboard) demoable before US2
   (the audit), but verify.md says a frame is never shown without a `PASS` or `WARN` audit. Until
   T020 lands, are US1 frames shown (labelled unaudited), or does the US1 checkpoint wait for the
   audit? **Moot:** T020 is built; every frame is audited.
2. **Order within P2.** PLAN.md puts US2, US3 and US4 in one phase. If time runs short, which is
   cut or thinned first? (2026-10-18: US2 and US3 are built; US4's portraits, T025, are proposed for
   cutting, waiting on Tumo, with consistent looks carried by T079's look prompts. MILESTONES.md
   week 3.) **Decided 2026-10-19:** T025 is cut; T079's look prompts carry the looks.
3. **Which styles stay private** (STATUS.md § Open decisions): **decided 2026-09-30 by the user**:
   none. `clean` (the default), `ink` and `pencil` are public in `styles/`; `classic` is dropped
   (storyboard.md §8, §10).
4. **Spend cap and upload limit values** for the hosted demo: PLAN.md sets the goal (about $0.10 a
   script) but not the caps, nor how many extra attempts a user may ask for on a withheld frame or
   portrait. **Decided** (Tumo, 2026-10-10; limits.md): one judge account, 3 uploads a day, 15
   pages a script, `LLM_MONTHLY_TOKEN_CAP` 2,800,000 tokens and `IMAGE_MONTHLY_GENERATION_CAP` 800
   drawings a month; "Try another render" spends from the same caps.
5. **Frame-audit accuracy bar.** No target is agreed. T049 was closed 2026-10-12; the audit is
   scored on 109 hand-labelled frames (T124): 38 of 57 wrong frames withheld, 1 of 40 right ones.
   (If recall is poor, the remedy is decided: a new describer prompt or model, or option B; verify.md §8.)
6. **Who can see a project.** Row-level security for projects, Storage and the `Job` table:
   **decided in T009** (deploy.md § Row-level security): RLS on with no policies, a private bucket,
   and the API enforces ownership.
7. **Sound effects** from all-caps action ("DOORS SLAM."): a styling choice, decided with a sample
   page in hand (comic.md §10, T023). Until then, none.
8. **Dual dialogue** isn't parsed, so simultaneous speeches read as sequential bubbles (script.md
   §10, comic.md §10). Fix only if a sample needs it.
