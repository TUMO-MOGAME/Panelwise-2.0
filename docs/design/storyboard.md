# Design — `storyboard` (frames, styles, the image chain, the storyboard PDF)

**Status:** built (T003 and T025 cut 2026-10-19) · **Owner:** Katlego (Claude) · **Tasks:** T008 (styles, redaction, prompts and a
prompt-printing CLI), T026 (the fal.ai renderer, Storage, the storyboard job: §3.5;
T021's loop is merged), T027 (the PDF and JSON, after T026) · **Spec:** [SPEC.md](../../SPEC.md) US1 (script → grounded storyboard)

---

## 1. What this covers

Turning a `ShotPlan` (shots.md) into a **storyboard**: one frame per shot, rendered by FLUX.2 [klein] 4B on
fal.ai (§3.5; FLUX.1 [schnell] before 2026-10-11; ComfyUI on a Nebius GPU, T003, cut 2026-10-19) in a **style**, audited by verify.md's loop before anyone sees it, stored in
**Supabase Storage**, and exported as one **PDF**. It owns four things:

1. **The frame prompt**: built only from the shot's grounded fields (§3.1). This is where
   Non-negotiable I is enforced on the *input* to the image model; verify.md enforces it on the
   output.
2. **The style registry**: public styles in `styles/`, an optional private pack from
   `PANELWISE_PRIVATE_STYLES`, the same validation for both.
3. **The renderer**: verify.md's `RecordingRenderer` Protocol, implemented on fal.ai (§3.5; the only
   renderer: ComfyUI, T003, was cut 2026-10-19); each render stored by a content
   address, which is also the render cache.
4. **The storyboard document**: the page layout and the PDF, with the withheld-frame text card.

**Not covered:** the audit, the re-render loop, the frame state machine and the `frame_audits`
table (verify.md, T020/T021); reference portraits and IP-Adapter (characters.md, T025: cut
2026-10-19); comic pages (comic.md, which calls this renderer at panel size); the `Job` table, the `frames` table and the web screens
(docs/design/web.md: T009, T053, T043, T044, T046, T047, T040–T045); spend caps (T030).

## 2. Reference material

| Kind | Where |
| --- | --- |
| Code ported from | FrameFlow `services/api/app/services/`: `storyboard_service.py` (prompt assembly, `_setting`, `_ANGLE_WORDS`), `storyboard_styles.py` (the style dataclass, the three drawn styles and their A/B notes), `image_provider.py` (`ComfyUIImageProvider`: submit, poll `/history`, queue-aware deadline, cancel, `/view`), `image_postprocess.py` (`storyboard_grayscale`), `storyboard_document.py` (A4, two 16:9 frames a page, spec line under each). What is dropped and why: §8 |
| What FrameFlow learned | CLIP can't read negation ("no borders" drew borders); the setting reads best as "inside \<place\>, \<time\>" straight after the framing; SDXL-Turbo tints pencil frames sepia whatever the prompt says, so grayscale is a pixel pass; a free-text frame description is where invention lived (shots.md §8) |
| Inputs | `ShotPlan`, `Shot`, `Framing` (shots.md §6); `Screenplay`, `Scene`, `Action`, `Dialogue`, `Span`, `normalise` (script.md §6); `Extraction`, `Entity`, `Quote` (grounding.md §6) |
| Contract this provides | verify.md §6 `RenderedFrame` and `Renderer`, verbatim (built in `app/verify/model.py`, PR #22) |
| Contract this calls | verify.md §6 `render_until_accepted`, `seed_for`, `Audit`, `FrameOutcome`, `FrameState`, `Check`, `Verdict` |
| Character rules | characters.md §3 rules 1–3 (no names in prompts; only the script's words; undescribed stays undescribed) and its redaction |
| Hosting | deploy.md §1 (Supabase Storage for images), §6 (env), §10 (local Storage: decided here, §8) |
| ComfyUI | none (T003: cut 2026-10-19; never built) |
| Visual reference | none committed: T027 shipped without committing its PDF pages as PNGs (`docs/design/reference/storyboard/` doesn't exist) |
| Fonts | **Courier Prime** Regular and Bold (SIL OFL 1.1), committed under `services/api/assets/fonts/` with their licence: the screenplay's own typeface, and the PDF prints script text verbatim |

## 3. Domain model

```mermaid
classDiagram
    class Style {
        +str key
        +str label
        +str description
        +str medium
        +str finish
        +float|None emphasis
        +str negative
        +bool grayscale
        +bool default
        +StyleOrigin origin
    }
    class StyleRegistry {
        +Mapping~str,Style~ styles
        +str default
        +get(str|None) Style
        +public() tuple~Style~
    }
    class FramePrompt {
        +tuple~PromptPart~ parts
        +int trimmed
        +text() str
    }
    class PromptPart {
        +PartKind kind
        +str text
        +Span|None span
    }
    class FalRenderer {
        +Style style
        +AssetStore store
        +Screenplay screenplay
        +Extraction extraction
        +str model
        +int max_words
        +float timeout_s
        +render(Shot, int, int, int, int) RenderedFrame
        +record(tuple~int,int~, int) RenderRecord
    }
    class RenderRecord {
        +tuple~int,int~ shot
        +int attempt
        +str key
        +str asset
        +FramePrompt prompt
        +bool cached
        +float|None seconds
    }
    class AssetStore {
        <<Protocol>>
        +exists(str) bool
        +get(str) bytes
        +put(str, bytes, str) None
        +signed_url(str, int) str
    }
    class Storyboard {
        +str style
        +int width
        +int height
        +tuple~StoryboardFrame~ frames
        +int renders
        +int cached
    }
    class StoryboardFrame {
        +tuple~int,int~ shot
        +FrameState state
        +str|None asset
        +str|None prompt
        +int|None seed
        +int attempts
        +Verdict verdict
        +tuple~Check~ noted_checks
    }
    class StoryboardPage {
        +int number
        +int scene_index
        +tuple~Block~ blocks
    }
    class Block {
        +tuple~int,int~ shot
        +int y
        +Rect|None frame_rect
        +str title
        +str span_label
        +str|None audit_line
        +tuple~SourceLine~ source_lines
        +bool continued
    }
    StyleRegistry --> Style
    FramePrompt --> PromptPart
    FalRenderer --> Style
    FalRenderer --> AssetStore
    FalRenderer --> RenderRecord
    RenderRecord --> FramePrompt
    Storyboard --> StoryboardFrame
    StoryboardPage --> Block
```

`FalRenderer` (§3.5) implements verify.md's `RecordingRenderer`; `RenderedFrame` is verify.md's, unchanged.
`FrameState`, `Verdict` and `Check` are verify.md's. `Rect` is `(x, y, w, h)` in page pixels.

### 3.1 The frame prompt (Non-negotiable I on the input)

`build_frame_prompt` is a **pure function** of the shot, the screenplay, the extraction and the
style. Its script text comes **only from the shot's own scene heading and the elements the shot
covers**. It takes no free text: not the shot's `rationale` (shots.md: never used in a prompt), not a
user's note, not any model's prose. Two inputs are model-proposed and code-filtered, and the prompt
narrows them further: `shot.characters` (shots.md filters them to entities present in the scene;
`COUNT` below keeps only those the covered elements show on screen) and the extraction's names (used
only to **remove** words, by redaction). A prompt is an ordered tuple of **parts**, each tagged with
where it came from; `text()` joins them with `", "` (comma phrases, the way CLIP reads captions:
FrameFlow's finding).

**Order**, fixed: `STYLE`, `FRAMING`, `SETTING`, `TIME`, `COUNT`, then for each visible character in turn its `AGE` (T074) and `LOOK` (T079), `PLACEMENT`, then one `ACTION`
part per covered `Action` element, **in element order**. The scene-level parts lead because a text encoder that
truncates drops the tail.

| `PartKind` | Origin | Text | `span` |
|---|---|---|---|
| `STYLE` | the style (§3.2) | `medium` (weighted by the renderer when `emphasis` is set), then `finish` | `None` |
| `FRAMING` | a fixed table in code, keyed by `shot.framing` | `wide` → "wide shot", `medium` → "medium shot", `close_up` → "close-up", `extreme_close_up` → "extreme close-up", `over_shoulder` → "over-the-shoulder shot", `pov` → "point-of-view shot", `insert` → "close-up insert shot" | `None` |
| `SETTING` | this scene's heading | `inside` / `outside` / `at` (from `scene.int_ext`: `INT`, `EXT`, `INT_EXT`) + `scene.location`, **redacted, then** lower-cased | this scene's heading span |
| `TIME` | `shot.time_of_day` (resolved, shots.md) | lower-cased; omitted when `None` | the heading span of the scene that **supplied** the clock (`time_source`, below) |
| `COUNT` | code, from `visible_characters(shot, screenplay, extraction)` (below) | 1 → "one figure", 2 → "two figures", 3 → "three figures", 4 → "four figures", ≥ 5 → "a group of figures"; omitted at 0 | `None` |
| `AGE` (T074, T079) | `introduced_age(character, screenplay)` for each `visible_characters` member, in their order; one part per character whose introduction gives an age | `(10)` → "a 10-year-old", `(70s)` → "a person in their 70s"; **T079:** with the sex the introduction's pronouns give (`introduced_sex`, below; **T082:** `character_sex`, which adds a sex title and the extraction's grounded `sex_word`, all agreeing; and when the script gives a sex but no age, a `SEX` part in its place: "a female person" or "a male person", which claim no age (an unaged character may be a baby: `(5 months)` gives no age); cited with `Entity.sex_quote`'s span, or, for a title, the span of the character's first located quote, where the script names them): "a 10-year-old girl" / "boy" under 18, "a 30-year-old woman" / "man" from 18, "a woman in her 70s" / "a man in his 70s" (the first number in the parenthesis after the character's name where an `Action` line introduces it: `LERATO (10), braids…`, `NANDI (60s, oilskin coat)`); omitted when the script gives none | that `Action` element's span |
| `LOOK` (T079) | `introduced_look(character, screenplay)` for each `visible_characters` member, right after its `AGE` | the introduction's own description, verbatim, redacted: the parenthesis's items after the age (`NANDI (60s, oilskin coat)` → "oilskin coat") and the comma phrase right after the parenthesis (`LERATO (10), braids tied back, grips…` → "braids tied back"; `MOKGOSI (70s), reading glasses pushed up on his forehead, solders…` → that phrase), joined by ", "; a phrase over 8 words, or one with no comma closing it before the sentence ends, is left out (it is an action, not a look: `AMAHLE (8), who is wearing pyjamas … crying.`); omitted when nothing is left, and when the shot covers that introducing line (its `ACTION` part already says it, word for word). **Not a fixed part:** looks give way to the budget (Word budget, below) | that `Action` element's span |
| `PLACEMENT` | characters.md `FrameReferences.placement`, which must be one of `PLACEMENT_PHRASES` (a closed set owned here: `{"one figure on the left, one on the right"}`; anything else is a `ValueError`), and is accepted only when `visible_characters` has exactly two members (else `ValueError`), so it can never contradict `COUNT` | the phrase; never emitted: T026's renderer passes `None` (T025, which would pass it, was cut 2026-10-19) | `None` |
| `ACTION` | a covered `Action` element's text | verbatim, whitespace collapsed, redacted | the element's span |

- **The heading span** of a scene is `Span(scene.span.page, scene.span.line_start,
  scene.span.line_start)`: the heading line (`Scene.span` itself runs to the scene's last element).
- **`time_source(scenes, scene_index) -> int | None`** returns the index of the scene whose own
  `absolute_time` `resolve_times` used: this scene when its heading has an absolute time, else the
  nearest earlier one that does, else `None`. So a `CONTINUOUS` scene's "night" cites the earlier
  heading that says NIGHT. The image uses a borrowed clock and the comic caption doesn't (comic.md
  §3) because they answer different questions: the caption quotes *this* heading's words, while the
  image must not draw a night scene in daylight (shots.md §2: the reason `resolve_times` exists).
- **`visible_characters(shot, screenplay, extraction)`**: the members of `shot.characters`, in that order, that the
  covered elements put on screen. A character is on screen if a covered `Dialogue` cue resolves to
  them with `match_speaker` and its extension, upper-cased, contains none of `V.O.`, `O.S.`, `O.C.`,
  `OFF` (comic.md's list), or if one of their name tokens (below, `other_names` included) appears in
  a covered `Action` text. A planner-listed character the covered text never shows is not counted,
  and neither is an off-screen or voice-over speaker. **Listeners (T079):** when the covered
  elements put no one on screen but one of them is a line spoken off screen, by anyone (a
  `RADIO ANNOUNCER (V.O.)` the planner doesn't list too: the T079 review), the planner's other
  characters (not that speaker, no animal) are on screen: someone hears the line. On 2026-10-11
  the-red-kite's shot 1.3 was only `MOKGOSI (O.S.)`'s line, so the prompt asked for no one and
  klein drew an empty roof, where the planner had Lerato. **People only (T052):** the signature becomes
  `visible_characters(shot, screenplay, extraction)` (the screenplay for pairing, below), it skips every *animal* (below), and it detects an
  action-line mention with that one character's labels (its name and paired other names). `COUNT`
  and `PLACEMENT`'s "exactly two" both use it, so a cat is never a figure; the action line that
  names it already says "the cat" after redaction.
- **A sex noun in the introduction's appositive (T096).** `introduced_sex` also reads the
  introducing sentence up to the name (the sentence starts after the last `. ! ?` before it). When it
  opens with `A` or `An`, then at most three words, then a sex noun (`SEX_WORDS` less the pronouns:
  boy, girl, man, woman, …; never a possessive, "A boy's teacher"), then **nothing, or the noun's
  own describing phrase**: at most six words, no `(`, opening with `in`, `with`, `wearing`,
  `dressed`, `of` or `from`, and holding no second sex noun, no him/his/her, no conjunction
  (`and`, `or`, `but`, `who`, `whose`, `that`, `which`, `while`) and no other person noun (`baby`,
  `child`, `kid`, `toddler`, `infant`, `teenager`, `friend`, `people`, `person`, `family`)
  (code review of #168), up to a comma directly before the name and its `(` ("A boy in a too-big school blazer, THABO (9)", "A small
  boy, KAMO (7)"), that noun's sex is one more of the introduction's sources, and the one-sex rule
  still holds (a noun and a pronoun that disagree give None). The bounds keep a clause about someone
  else out: "A man helps a girl, AMA (7)" and "A boy, THABO (9), and a girl, AMA (7)" give AMA
  nothing (a safe miss). **The invariant** (below) gains a fourth key: a sex noun of that sex before
  the name in the introducing line. **Measured** free on the eight read samples: 2 found, both right
  (THABO, KAMO, the scripts it was found on), 0 wrong, and a looser form (the article anywhere in the
  sentence, no bounds after the noun) finds the same two. Not covered: "His young colleague, SIBUSISO
  (20s)" (no sex noun), "A WOMAN WITH A PRAM" (the noun is the name: L017).
- **A Her or His opening the next sentence (T100; learning-log L023).** `introduced_sex` also
  reads the sentence right after the introducing one, in the same `Action` element, when that
  sentence opens with exactly `Her` or `His` (capitalised, as a sentence opens; `HER` or a later
  `her` is never read) used as a possessive: `His` always, `Her` only when a word follows it, after whitespace alone
  ("Her, then silence." owns nothing), that is not one of grounding's `NOT_POSSESSED` (made public from `_NOT_POSSESSED`, exported by
  `app.grounding`; "Her to …", "Her a …" and a bare "Her." own nothing, as in grounding's `_owned`).
  `His` gives male and `Her` female, one more of the introduction's sources under the one-sex rule.
  **Where the sentences are:** the introducing sentence runs from the character's `NAME (…)` to the
  first `SENTENCE_END` (grounding's, which doesn't stop at "Mr.", "Dr." and the like) in the
  element's text after the name's match; the next sentence is the text after that boundary, up to
  the next `SENTENCE_END` or the element's end. No boundary inside the element (the introducing
  sentence is its last) gives nothing.
  **Only when the introducing sentence is about this character alone**, read from just after its
  parenthesis to that boundary: no other character's name word (`_other_names`), no capitalised
  word at all (a name the script never introduced or cued: "greets Dr. Dube"; found writing
  T100's tests), no next introduction (`_NEXT_INTRODUCTION`), no `SEX_WORDS` word (man, woman, boy, girl, he, she, …), no
  `CONFLICT_WORDS` word (him, her, his, hers), no `them`, no T096 `_PERSON_NOUNS` word (child,
  baby, friend, people, person, family, …), and no article or determiner (the, a, an, this, that,
  these, those, another, some: it may bring in anyone no list holds, "hands the clerk a coin",
  "pats a dog"; code review of T100). Words are read in any script's letters ("greets Émilie"). This is a positional test on the untruncated text, not
  on `introduced_sex`'s cut `rest`: in the NALEDI line the next introduction `TSHEPO (` lies past
  the boundary, so it doesn't count. So "MAMA (60s) hugs SIPHO. His …", "NANDI (60s) waves to
  THABO (9). His …", "SAM (40) kisses the woman. Her eyes close." and "NALEDI (12) hands the man a
  coin. His hand shakes." give nothing (a safe miss), and a `Her`/`His` further on, or after a line
  of dialogue, is never read.   "NALEDI (12), dungarees, scraped knees, stares at it. Her little brother TSHEPO (8) …" gives
  NALEDI female; the next sentence's own introduction (TSHEPO) doesn't matter, since its `Her` opens
  it. **Measured** free on the labelled read scripts (`eval/sex-labels.json`, the 10 with a sample
  file; the held-out ones never opened): **1 candidate** (a sentence opening `Her`/`His` right after
  a sentence introducing one character) in all 10, **NALEDI, right; 0 wrong**. The-borrowed-bicycle
  had Naledi drawn as a boy in about 11 of 18 frames, her prompts saying only "a 12-year-old".
  **The invariant** is unchanged: its introducing line is the whole `Action` element, whose `Her` or
  `His` already keys the sex (`keyed`'s pronoun of the introducing line).
- **A He or She with no one drawn, or against everyone drawn (T093; learning-log L016).** The
  prompt keeps action sentences whole, so a sentence whose subject is only a pronoun is drawn on
  whoever klein draws.
  - **Sentences.** `pronoun_sentences(text)` reads the text `build_frame_prompt` emits for an
    element: `script(element.text)`, redacted and whitespace-collapsed. It splits it at
    `SENTENCE_END`, the pattern grounding's `_pronoun_pieces` uses (`. ! ?` then whitespace, never
    after `Mr.`, `Mrs.`, `Ms.`, `Dr.`, `St.`), made public by `app.grounding` (renamed from
    `_SENTENCE_END`, the one object both use), and the pieces joined by one space give the text back.
    A piece **opens with a pronoun** when its first word is exactly `He` or `She` (redaction can't
    add or remove one: its labels are "a person", "the <species>", "it"); its sex is male or female.
    Anything else is no pronoun opening and is always kept as it is: "Then he…", "They…", "His…", a
    piece opening with a quote mark (`"He…`), and a He that doesn't follow whitespace after a full
    stop (`"Go." He nods.` is one piece, opening with `"`).
  - **Two rules**, both needing every sex they read to be known (`character_sex`), so an unknown
    sex changes nothing. They use `_shown_characters`, today's `visible_characters` body (Listeners
    included), so nothing calls itself: `visible_characters` returns `_shown_characters`' result
    when it is not empty, else `(pronoun_figure(...),)` when that is a name, else `()`.
  - **Rule 1: no one on screen, one person of that sex in the cast.** When `_shown_characters`
    returns no one (Listeners included: a shot whose only other cast member is the off-screen speaker
    is still no one) and every pronoun-opening piece of the covered `Action` elements gives the same
    sex, `pronoun_figure` is the person with that sex among the shot's candidates: `shot.characters`,
    no animal, no speaker the shot hears off screen (T079's `heard`). It names them when exactly one
    candidate has that sex and every candidate's sex is known; else None. They are drawn like any
    visible character (`COUNT`, `AGE` or `SEX`, `LOOK`), and the audit's `on_screen` (from
    `visible_characters`) includes them, so the hard `NO_CHARACTER` now applies to that shot: a
    frame where the judge matches no one to them is withheld, as for any drawn character.
    stormwater 6.4, "He looks at the ball. He puts it in his pocket.", cast MR. VAN DER MERWE:
    before T093 the prompt drew no figure, klein drew a man three times and the judge never matched
    him (withheld); now "one figure, a man in his 50s, orange overalls".
  - **Rule 2: figures drawn, none of that sex.** When `visible_characters` (its final result) is
    not empty, every visible person's sex is known and none has a piece's sex, that piece is left
    out of the `ACTION` parts: it is about someone the frame doesn't draw. Only that piece goes; in
    a shot with a He and a She piece and only a man drawn, the She piece alone is left out. An
    element's kept pieces become one `ACTION` part per run of consecutive kept pieces, each the
    one-space join of its run (a substring of the collapsed redacted element: the invariant holds),
    with the element's span; parts follow ascending element index, runs in sentence order, so read
    together they follow the script. An element whose every piece is left out gives no `ACTION`
    part (as an empty text does today), and that adds nothing to `trimmed`; a prompt may end with
    no `ACTION` part at all. The Word budget then works on these parts as before: whole parts
    dropped from the tail, the first kept part cut; `trimmed` counts parts, so a split element can
    add more than one. lost-property 2.3, "He peers at the ledger over his spectacles." with only
    ZANELE drawn (the He is MR. DUBE, who speaks before her) → left out. The audit's
    `shot_action_text` still holds the left-out piece: it is only where a stranger's support is
    looked for, and a support quoting it names someone the frame doesn't draw, which T084 already
    refuses (it has a he/she).
  - **Not covered:** a pronoun that agrees with a drawn figure but means someone else (the-bread-van
    5.3, DANIEL's "He salutes and goes." on a drawn THEO), His/Her/They openings, a pronoun inside a
    sentence. **Measured free** on the stored plans of the seven read scripts, with T092's casts:
    of 52 He/She-opening sentences, 5 resolved (stormwater 2.3 and 6.4 ×2 to MR. VAN DER MERWE,
    load-shedding 5.4 "She blows out the last candle." to MS. MOLEFE, the-red-kite 5.4 "He switches
    off the soldering iron." to MOKGOSI) and 1 left out (lost-property 2.3), each read against the
    script: **all 6 right**; 2 left as they are (a cast person of unknown sex, or no cast) and 44
    kept as they were (the prototype did not leave out off-screen speakers;
    the code PR re-measures with the real rule).
- **Entity quotes from outside the shot never enter a prompt.** A character's introduction ("NANDI
  (60s, oilskin coat) pours tea…") or a prop's first mention carries that moment's event, so quoting
  it into another shot draws an event this shot doesn't have. A quote located *inside* a covered
  element is already in the prompt as that element's `ACTION` text. (T082: a `SEX` part cites a
  quote that may lie outside the shot, but only its keyed sex enters the prompt, never its words.)
  A character's look reaches
  the frame through the introduction's `AGE`/`SEX` and `LOOK` parts (above); T025's reference
  portraits (characters.md) were cut 2026-10-19.

**The invariant** (tested, §9): for every part whose `span` is not `None`, that span is this scene's
heading span, the heading span of `time_source`'s scene (only for `TIME`), the span of the `Action`
element that introduces a visible character (only for `AGE`, T074: its text is "a <n>-year-old" or "a person
in their <n>s", and `<n>` stands in that element in a parenthesis right after that character's name: an
age is who the character is, not another moment's event, as a borrowed clock is when; T079: with the
sex word `introduced_sex` reads there, the code's fixed vocabulary keyed by the script's own pronoun
(**T088:** any `sex_quote` holding a `SEX_WORDS` word or `his`, `her`, `him` or `hers` of that sex (`CONFLICT_WORDS`): T088's evidence (grounding.md §3) may name the sex only by a possessive; **T082:** or keyed by a word of the character's name (a title), or of `Entity.sex_quote`, a located Action
quote; **T096:** or a sex noun before the name in the introducing line: the invariant test checks that the sex word of every `AGE` and `SEX` part is keyed by a word in one of
those four); `SEX` (T082), whose span is `Entity.sex_quote`'s (a located Action quote, which may lie outside the
shot) or, for a title, the character's first located quote's, and whose text is the code's fixed "a female
person" / "a male person": like `AGE`'s phrase, it is outside the substring test, and only the keyed sex, never
the quote's words, enters the prompt;
and `LOOK`, whose text is exactly what `introduced_look` reads there, a verbatim piece of that
element: a look is who the character is too, while the rest of that line, its action, stays out),
or the span of an element
the shot covers; and the part's text (after the `SETTING` part's leading preposition) is, under `normalize_for_grounding`, a substring of `redact(text,
redaction_labels(extraction, screenplay))` applied to that heading or element text (`redact_all`
before T052). Every part whose `span` is `None` is from the fixed tables
above or the style. So a prompt says nothing that isn't in this shot's lines or its heading, except
the style's medium words, the code's fixed framing, preposition, count and placement vocabulary, and
an age's number in its fixed phrase,
none of which names a person, prop or event.

- **Parentheticals never enter a prompt.** `Dialogue.parenthetical` ("beat", "without turning") is
  a delivery note, not a picture; it isn't part of `Dialogue.text`, its line lies outside the
  element's span (script.md's parser), and it isn't in the shot's `source`, so it could not be traced
  to the span a prompt part cites.
- **Dialogue text never enters a prompt.** Speech isn't visible, and words in a prompt are how
  letters appear in the art (verify.md's hard `TEXT_IN_FRAME`). The speakers are drawn because they
  are counted (`COUNT`).
- **Movement never enters a prompt.** A still can't show a pan; FrameFlow's movement words
  ("handheld", "tracking with the subject") read as motion blur. Movement is printed under the frame.
- **Names never enter a prompt** (characters.md rule 1). Every script-derived part is redacted
  **before** any lower-casing, with `redact(text, redaction_labels(extraction, screenplay))` (T052;
  `redact_all` before it), which follows characters.md rule 2's matching:
  - **Name tokens** are the words of `normalise(name)` for every `CHARACTER` entity in the extraction,
    **minus `NAME_STOP_WORDS`**, a fixed list of words that are not names on their own (`THE`, `A`,
    `AN`, `OLD`, `YOUNG`, `LITTLE`, `BIG`, `MR`, `MRS`, `MS`, `MISS`, `DR`, `SIR`, `LADY`, `MAN`,
    `WOMAN`, `BOY`, `GIRL`, `STRANGER`, `OFFICER`, `NURSE`, `DOCTOR`). A cue like `THE STRANGER` thus
    has no name token and nothing is redacted for it; "The kettle screams." stays as written.
  - A **maximal run** of name tokens (with an optional possessive `'S` on its last token), in UPPER
    or Title case at word boundaries, becomes one `a person` (`a person's` for a possessive): "NANDI
    MOLEFE pours" → "a person pours", "NANDI'S KITCHEN" → "a person's kitchen".
  - **A name's lower-case particle joins its run (T092).** A maximal sequence of one or more words
    of `NAME_PARTICLES` (`van`, `der`, `de`, `du`, `da`, `von`, `le`, `la`, `del`, `dos`, `den`,
    `ter`, `bin`), each written in lower case, each upper-cased in the `tokens` the call uses, and
    each separated from its neighbours by whitespace only, joins a run **only when it sits between
    two name words**: a name word before it and a name word after it, whitespace on both sides. It
    is added to the run upper-cased, so `label` receives it like any token. "Mr. Van der Merwe climbs
    down" → "a person climbs down" (before T092, "a person der a person"; learning-log L019, added by
    #160); "Jan van der Merwe" (two particles) → "a person". A particle with no name word before it
    stays: for a character `LE ROUX`, "the house of le Roux" → "the house of le a person". So does
    one at the end of the text or after a `.` or `,` ("Thabo. de Wet" breaks at the full stop), and
    a lower-case particle that is no token of the call's names. The one realistic false join is a
    particle word between two names that are both tokens ("Jabu bin Lindi" when BIN is some name's
    token); accepted.
  - **A name as a figure (T092).** `named_as_figure(text, tokens)` is true when **some** run of
    `tokens` in `text` is a figure run, and one figure run is enough among possessive or capitals-only
    runs ("Jabu's paper. Jabu covers it" is true). Runs are found by the **same run-finder `_redact`
    uses** (a small refactor: `_name_runs(text, tokens) -> list[tuple[int, int]]`, the first and last
    word of each run, particles joined, before `_redact` consumes a possessive `'s` or joins a
    title), so the two can never disagree. A run is a figure run when it is not possessive and:
    - **Title case:** some word of the run, particles aside, differs from its own upper case
      ("Lindi", "Van Wyk", "McDONALD"); decided on the run itself, never on a title before it
      (`_title_start` is not part of the run), so "Mr. Dube winds his watch" is Title case and
      "Mr. DUBE winds his watch" is not; or
    - **an introduction:** every word UPPER case and the run's last word followed by `[ \t]*\(`
      ("AYANDA (17)", "AYANDA(17)"; a newline before the `(` does not count).
    - **Possessive:** any of `_APOSTROPHES` (`'`, `’`, U+02BC) immediately after the run's last word,
      with or without an `s` after it: "Jabu's paper", "NANDI'S", the plural "The Lionesses'
      goalkeeper". An apostrophe inside a run (`O'BRIEN`) is not possessive. **Accepted:** a closing
      single quote after a name ("calls 'Lindi' over") reads as possessive, so it names no figure.
    The shot planner (shots.md §3) uses it to add the characters an action line puts on screen:
    "Lindi rolls the ball out to Palesa." names both; "The Lionesses' goalkeeper" and "The
    scoreboard is a blackboard: LIONESSES 1 - EAGLES 1." name no figure.
  - **Labels, not only "a person" (T052).** Redaction covers every character's name **and its
    `other_names`**, and every prop's `other_names` (a prop's own name, "VIOLIN", is a thing to draw
    and stays). `redaction_labels(extraction, screenplay)` gives **token → label**, inserted in rank
    order (persons, animals, named props, `it`; extraction order within each), and a token is placed
    at the position of the label that wins it; `redact` gives a run the label of its token that comes
    first:
    - **Animals.** A character is an animal when it has a `species`, or when `match_speaker` binds
      its name to an animal's name (so a CUE backfill or a second entry of the same cat, which has
      no species of its own, is still the cat). Its label is `the <species>`, lower-cased.
    - **Persons.** Every other character: `a person`, as before.
    - **Named props.** A prop's label is `the <prop name>`, lower-cased, with a leading
      `a`/`an`/`the` stripped from the name. The definite article throughout means no
      `a`/`an` rule and no plural problem ("the umbrellas"), and it reads as the thing already
      in the frame, not a second one.
    - **Fallback `it`.** A label whose words include any name token of any character or other name
      ("NANDI'S UMBRELLA" → would be "the nandi's umbrella") is `it` instead, so a lower-cased
      label can never carry a name past `names_in`.
    - **Pairing.** An other name gets its entity's label only when it shares a **scene** with
      that entity: some scene whose heading or elements mention the other name as a whole word
      also mentions the entity's name, its species, or holds one of its located quotes. On
      `lost-property`, "Gerald" and "giraffe" share scenes 6 and 11, so Gerald → `the giraffe`.
      An unpaired other name is still redacted, to `it`: the model's pairing is otherwise
      unverified (grounding.md §8), and `it` adds no person and no thing. An other name claimed by
      two paired entities follows **Conflicts** below.
    - **Conflicts.** A token claimed by several entities takes, in this order, a person's label, then
      an animal's, then a prop's, then `it`; between two of the same kind, the earlier entity in
      `extraction.entities`. A run's label is the highest-ranked of its tokens' labels by the same
      order. **Accepted:** a run that mixes a person and an animal ("Nandi Marmalade") is one
      `a person`, and the cat is lost from that line.
    - "Even Marmalade comes back to the doorway" → "Even the cat comes back…"; "Amahle dances with
      Gerald" → "a person dances with the giraffe"; "Marmalade's tail" → "the cat's tail".
      **Known cost:** an appositive repeats the species, "A ginger cat, MARMALADE, sleeps" → "A
      ginger cat, the cat, sleeps"; the definite article keeps it one cat in English, and the
      audit catches a frame with two (an unscripted animal is `UNSCRIPTED_OBJECT`).
    A possessive keeps its `'s` (`a person's`, `the cat's`), except `it`, whose possessive is `its`
    ("Gerald's leg", unpaired → "its leg").
    Every label word is `a`, `person`, `the`, `it`, `its` or a word the script itself writes (the species
    is in the entity's own description; a prop name is found in the script), so the invariant below
    still compares against the same redaction (`cites_this_shot` and `build_frame_prompt` call the
    same `redact` with the same labels), and `names_in` checks every labelled name and other name.
  - **A title goes with the name it precedes** (T050). One or more of `TITLE_WORDS` (`MR`, `MRS`,
    `MS`, `MISS`, `DR`, `SIR`, `LADY`, `OFFICER`, `NURSE`, `DOCTOR`: the stop words that are forms
    of address), each in UPPER or Title case and separated from the next by whitespace, directly
    before a name run, join that run: "MR. DUBE" → "a person", "Officer Van Wyk's" → "a person's".
    Only the abbreviations `MR`, `MRS`, `MS`, `DR` may carry a `.`: "…the OFFICER. Moloi turns" is
    a sentence end, so the title stays and only "Moloi" is redacted. Before T050 the title stayed
    ("MR. a person"). A title with no name run directly after it is left alone ("the OFFICER",
    "Mr. Nobody" when NOBODY isn't a name, the "MR." of "MR. AND MRS. DUBE").
  - Speaking characters are always in the extraction (grounding.md backfills every cue as a
    `Source.CUE` entity), so every speaker's name is covered. **Residual risk:** a named person who
    never speaks and whom extraction missed isn't known to be a name, so it is not redacted. §9 pins
    this with an adversarial fixture; §8 records it.
  Redaction only removes words (characters.md rule 2). Besides it, a script span undergoes only
  whitespace collapsing and lower-casing for `SETTING` and `TIME`. **`TIME` is not redacted**: its
  text is `absolute_time`'s word, a closed vocabulary (`ABSOLUTE_TIMES`) that names no one, and a
  character named DAWN must not turn the clock into "a person" (PR #27 review). The invariant
  checks it against the unredacted heading and the vocabulary.
- **Undescribed stays undescribed** (characters.md rule 3): nothing about how anyone looks is added
  unless the covered text says it.
- **Parentheses are sent as written.** FLUX reads no weight syntax, so a screenplay's parentheses
  ("NANDI (60s, oilskin coat)") are never re-weighted and nothing is escaped (§3.5).
- **No negations** (FrameFlow's finding: "no borders" drew borders). What must not appear is kept
  out by not being said, and caught by the audit. The style's `negative` goes to the negative prompt,
  which only subtracts.
- **Word budget.** `max_words` (the workflow's, §6) counts **whitespace-separated words** of
  `text()`, a deliberately conservative proxy for the encoder's token limit (the default 55 for
  CLIP's 77 tokens, kept for klein: §10). The **fixed parts** (`STYLE`, `FRAMING`,
  `SETTING`, `TIME`, `COUNT`, `AGE`, `SEX` (T082), `PLACEMENT`) are never dropped; **`LOOK` parts (T079)** are kept
  only while the fixed parts and the kept looks leave at least 12 words (`_ACTION_FLOOR`) for the
  `ACTION` parts, dropped from the last character back, so a look never fails a render (at 55 words
  a two-character the-red-kite shot's fixed words with looks reached 64); if they alone exceed `max_words`,
  `build_frame_prompt` raises `PromptError` naming the shot (a style or location too long for the
  encoder is a configuration error, surfaced as the renderer's failure, never a silently truncated
  prompt). Otherwise, over budget, whole `ACTION` parts are dropped from the **tail** backwards,
  never the first; if still over, the first `ACTION` part is cut to its longest prefix that fits and
  ends at a sentence end (`.`, `!`, `?`), else at a word boundary, and dropped altogether if not even
  one word fits. `trimmed` counts dropped and cut parts. Cutting only removes script words; what's
  left is a verbatim prefix, and a returned prompt never exceeds `max_words`.

### 3.2 Styles

A style is **how** a frame is drawn, never **what** is in it. One TOML file per style, the file stem
is the key (`[a-z0-9-]+`):

```toml
# styles/clean.toml
label = "Clean sketch"
description = "Pencil storyboard at full size. Keeps a wide shot as one panel inside the location."
medium = "storyboard sketch, pencil drawing"
finish = "grayscale, monochrome, loose linework, plain background"   # T074: "plain background"
# emphasis = 1.3     # optional: a weight on `medium`, not applied on fal.ai (FrameFlow's `ink` and `pencil` used 1.3)
negative = ""         # optional: negative prompt (subtractive only)
grayscale = true      # the pixel pass after rendering (FrameFlow's image_postprocess)
default = true        # exactly one PUBLIC style sets this
```

- **Public** styles are the files in the repo's `styles/` (`services/api/styles`, the root `styles` a symlink to it since T063); **private** ones are the `*.toml` files in
  the directory `PANELWISE_PRIVATE_STYLES` names (unset or empty → none). `origin` is set by where a
  file was loaded from, never by the file.
- **`load_styles` fails the start-up** (`StyleError`, naming the file) when: a field is missing,
  unknown or mistyped; a private key repeats a public one (a private pack can't shadow a public
  style); there is no public style; not exactly one style sets `default`, or the one that does is
  private (the demo must run on public styles, PLAN.md NN2); `medium`, `finish` or `negative`
  contains `(`, `)` or `:` (weight syntax is the renderer's); or `medium` or `finish` contains a **subject word**: a
  whole-word, case-insensitive match against a fixed list in code (`person`, `people`, `man`, `men`,
  `woman`, `women`, `boy`, `girl`, `child`, `children`, `figure`, `figures`, `crowd`, `character`,
  `face`, `portrait`, `animal`, `text`, `letters`, `words`, `caption`, `logo`, `sign`, `signature`,
  `watermark`). The list can't prove a style is content-free; it stops the obvious ways a style could
  put someone in the frame, and the audit catches the rest regardless of style.
- The same checks apply to private styles. A private style is never needed for anything the demo
  shows (PLAN.md NN2); the hosted API never sets `PANELWISE_PRIVATE_STYLES` (T030 verifies).

### 3.3 Frames, renders and storage

- **Storyboard frame size**: **1280 × 720** (16:9: a storyboard frame is a frame of the film). Comic
  panels call the same renderer at their rect's size (comic.md §4 step 6).
- **Draw size.** `fal_draw_size` (§3.5) scales the requested width × height down (never up) to at
  most 1,000,000 px, each side floored to a multiple of 16. The drawn image is scaled to **cover** the
  requested size and centre-cropped by at most the rounding excess (never a composition crop), so
  `RenderedFrame.width × height` is exactly what was asked.
- **Post-processing**, after the resize: the style's grayscale pass (`ImageOps.grayscale` then
  `autocontrast(cutoff=0.5)`, FrameFlow's), and PNG encoding. **The audit sees exactly the pixels
  that are shown and stored**; nothing touches a frame after it is audited.
- **The render key** is `sha256` of the canonical JSON (sorted keys, no whitespace) of `{"model":
  FAL_MODEL, "request": <the fal body>}` (§3.5), then, each after a `"\x1f"`: the **requested**
  `<width>x<height>`, `RENDER_VERSION` (a constant bumped whenever `fit` or a post-processing pass
  changes), and the post-processing step (`grayscale` or `none`). The requested size is in the key because two
  requests can round to one draw size (a comic rect and 1280 × 720), and the stored PNG is the
  fitted one. Model, prompt, seed, draw size and steps are all in that body, so every input that
  changes the pixels is in the key.
- **Storage paths**: `frames/<render key>.png` for every rendered attempt (the `frame_audits.frame_asset`
  column, verify.md §6, points at it, including attempts that failed their audit);
  `storyboards/<document key>.pdf` for an export (built on demand by T027's
  `GET /projects/{id}/storyboard/pdf`, web.md §6; the key is §3.4's). Paths are content addresses:
  the same inputs always land at the same path, so a `put` is idempotent.
- **The store is the render cache.** Before calling fal.ai, the renderer checks `exists(frames/<key>.png)`;
  a hit is read back and returned with no fal call (`RenderRecord.cached`). A failed job's
  already-rendered frames therefore cost nothing when the job is run again. There is no other image
  cache (no Redis, no disk cache: §8).
- **`StoryboardFrame`** is the storyboard's view of verify.md's `FrameOutcome`, built by `frame_of`
  from the outcome and the `RenderRecord` of its **last** attempt (`outcome.audits[-1].attempt`;
  `None` only when no audit exists, i.e. the renderer failed on the first attempt): `asset` is the accepted
  frame's storage path (`None` unless `PASSED` or `WARNED`); `prompt` (the text actually sent, as in `RenderedFrame.prompt`: `FramePrompt.text()`, plain, §3.5; the
  record keeps the tagged `FramePrompt`) and `seed` are the last attempt's, which
  for a `PASSED` or `WARNED` frame is the accepted one; `attempts` = `len(outcome.audits)`;
  `verdict` is the last audit's; `noted_checks` are the last audit's failed checks: the failed
  **hard** checks for a `WITHHELD` frame (what its card names), the failed **soft** checks for a
  `WARNED` one (a note under the frame), empty otherwise, all in `Check` enum order.

### 3.4 The document

- **Page**: A4 portrait at 150 dpi, **1240 × 1754 px**; margins **90 px**; content width **1060 px**;
  the frame is drawn at **880 × 495** (16:9, 1280 × 720 scaled), centred in the content width, so
  two shots of up to three source lines share a page (at 1060 × 596 every block took a page of its
  own, half of it blank; T027, 2026-10-10); **40 px** between blocks.
- **Scenes start a new page.** Header, from the top margin: `STORYBOARD` (Bold 22 px, one line),
  8 px, then the scene's heading **as printed in the script** (the line of `Screenplay.text` at
  `heading_span`, numbered as every span is, by `text.split("
")`: never `splitlines()`, which also
  breaks on a form feed or ` ` and would shift the line; not `Scene.heading`, which the parser
  normalises) (Bold 26 px, 34 px line pitch), wrapped to the content
  width like source text (below), then 12 px, a 2 px rule, and 24 px: `22 + 8 + 34 × lines + 38` px
  in all. Footer, above the bottom margin: a 1 px rule, 8 px, then (Regular 18 px, 24 px pitch)
  `Panelwise · <style label> · page <n> · A vision model describes each frame; Nemotron audits it
  against the script.`, wrapped to the content width; it grows upwards. The layout reserves the
  footer's height as wrapped for `page 999`, so a page number never moves a block.
- **A block per shot**, in plan order (`Block` fields in brackets):
  - the frame box (`frame_rect`; `None` on a continuation);
  - `title` (Bold 24 px): `<Scene.number>.<Shot.number>  <FRAMING> / <MOVEMENT>`, e.g. `12A.3  CLOSE
    UP / STATIC` (the script's own scene number, a string; the shot number is shots.md's, 1-based;
    enum values upper-cased, `_` as space). On a continuation: `<Scene.number>.<Shot.number> (cont.)`;
  - `span_label` (Regular 20 px, right-aligned on the title's line): `p.<page> l.<line_start>–<line_end>`,
    or `p.<page> l.<line>` for a one-line span, exactly as the web's `SpanRef` prints it;
  - `audit_line` (Regular 20 px): `Audit: pass` or `Audit: warn (<noted checks>)`; `None` for a
    withheld frame (its card says it) and on a continuation;
  - `source_lines` (Regular 22 px, 30 px line pitch): the shot's **`source`, verbatim**. Each of its
    lines (one per covered element, shots.md) is wrapped on whitespace to the content width
    separately, so element breaks are kept; a word wider than the line keeps a line to itself.
    Wrapping splits on whitespace and rejoins with one space, so a run of spaces letters as one
    (typography, not wording: every word, in order, as comic.md §4 step 5 letters).
    **Never truncated, never folded to ASCII** (FrameFlow folded em dashes and curly quotes for its
    base-14 fonts; with a TrueType font nothing needs folding).
    **Speakers (T103):** the PDF printed a speech with no name ("…glow blue." then "Load shedding.
    Thank you, Lord.", whose?), while the web's frame sheet shows each dialogue part under its
    speaker (web.md §4.4 step 3, `SourceBlock`, `sourceBlocks` in sheet.ts). So the lines come from
    the shot's covered elements (`Shot.elements` in its scene), in order:
    - an `Action` element: its text, each of its `\n`-separated lines wrapped as above, no speaker;
    - a `Dialogue` element: a **speaker line** when its label differs from the previous element's
      label (the web's rule: the label is `cue`, or `cue (extension)` when it has one, the extension
      stored without brackets; an `Action` element's label is none, so an action between two
      speeches of one cue prints the cue again), then its text, each `\n`-separated line wrapped as
      above. The speaker line is the label wrapped with the **Bold 22 px** font (a cue wider than the
      content width wraps to several speaker lines, a *speaker run*), drawn Bold at the same 30 px
      pitch. The parenthetical is left out, as on the web (it is not in `source`). An empty speech
      text wraps to one empty line (`wrap`'s `[""]`), so a speaker line is never a block's last.
    - **Fallback:** when the shot has no elements (a heading-only shot: shots.md gives it
      `source = scene.heading`) or the covered elements' texts joined by `\n` are not exactly
      `source` (a plan stored before a parser change), or an element index is out of range, the lines are `source`'s, as before T103, with
      no speaker lines. An export never fails over speakers.

    The speaker line is the script's own text (the cue line inside the speech's span); writing the
    extension as `(V.O.)` is typography, not new words, so nothing is invented (Non-negotiable I).
    Each line is a `SourceLine(text, speaker, of)`: `speaker` True for a speaker line, `of` the
    speech's label on its speech lines (None on action and fallback lines). Every line counts 30 px
    in the height.
  - Heights: frame 495, 12, title line 34, audit line 30 when present, 8, then 30 per source line
    (a continuation has no frame and no 12).
    `y` is the block's top, in px from the page top.
- **Fitting**: a block goes on the current page if it fits between the header and the footer; else a
  new page (same scene header). A block taller than an empty page puts its frame and as many source
  lines as fit on that page and continues the rest at the top of the next, `continued = True`.
  T103, when a block continues: the lines placed are the `room` that fit (at least one: on an
  empty page `room` is `max(1, …)`, so the loop always advances), less any speaker run they end
  on, which moves to the next page with its speech; when the lines that fit are all one speaker
  run, they stay (the one case a speaker line ends a page). When the continuation's first line is
  a speech line (`of` set), the speaker run for `of` is repeated above it, Bold, counted in the
  height: the continued speech is never left without its speaker. (A repeated run is one cue's
  few lines and a page holds about fifty, so a continuation always places a speech line.) Two
  guards make the loop finish whatever the input: the run is repeated only when the page just
  placed held a speech line (a cue taller than a page would otherwise lay out the same page
  forever), and a block whose lines all fit at the cut (only possible with `room` 0, under a
  heading taller than the page) is placed whole rather than continued with nothing.
- **Withheld card** (verify.md §4), in the frame box: white, 4 px `#808080` border, centred text in
  Regular 26 px, wrapped to 800 px (the 880 px box less 40 px a side, so no line crosses the
  border; 1000 px did, in the live run of 2026-10-10): `Frame withheld: failed audit (<checks>)` (the `noted_checks`
  names, lower case, `_` as spaces, joined by `, `; `audit error` for an `ERROR` verdict;
  `Frame withheld: failed audit` alone if a row's audit names neither, never an empty `()` and
  never a failed export), then
  `Script ` and the span as `span_label` prints it. The shot's `source` is printed under it as under every
  frame, so the card with its block shows exactly what verify.md §4 asks: the verbatim source, the
  span and the reason.
- **Failed card** (T027): a frame that ended `FAILED` (its renderer raised, or a restart cut it off,
  `frames.failure`) has no picture and no audit to show. Its frame box draws the withheld card's
  box and type with `Frame not drawn: the renderer failed` (`render`) or `Frame not drawn: the job
  was interrupted` (`restart`), then `Script ` and the span as `span_label` prints it; `audit_line` is
  `None`; the source is printed under it as under every frame. A failed row with no `failure`
  (none is written today) says `Frame not drawn` alone.
- **From the rows** (T027): the document is built after the job, from the project's `frames` rows
  and their `storyboard` audits (verify.md §6), not from the job's in-memory `Storyboard`.
  `frames_from_rows` gives one `StoryboardFrame` per row: `attempts` is the row's `attempt`; the
  verdict, seed and noted checks come from the row's audit at that attempt, the noted checks exactly
  as `frame_of` picks them (hard failures for `WITHHELD`, soft for `WARNED`, in enum order); a row
  with no audit at its attempt (a frame that failed before its audit) has verdict `ERROR` and no
  seed; `prompt` is `None` (rows don't keep the text sent); `failure` is the row's.
- **Style**: the footer's `<style label>` is the registry's default style, the one `fal_factory`
  draws every frame in (§3.5); `create_app` loads the styles at startup whether or not `FAL_KEY` is
  set, so a storyboard drawn earlier can still be exported.
- **Document key**: `sha256` of the canonical JSON (sorted keys, no whitespace) of
  `{"version": DOCUMENT_VERSION, "project": <id>, "style": [<style key>, <style label>], "frames": [[scene_index,
  shot_number, state, asset, verdict, [noted checks], failure], …]}` in plan order. Every input that
  changes the pages is in it (a project's screenplay and plan never change after planning; the
  footer prints the label, so a private style relabelled under the same key is a new PDF), so a
  second Export of the same storyboard is a store hit; "Try another render" changes a row and so
  the key. Bump `DOCUMENT_VERSION` whenever the layout or drawing changes.
- **Delivery**: `GET /projects/{id}/storyboard/pdf` builds the PDF if `storyboards/<key>.pdf` doesn't
  exist (reading the accepted frames' PNGs from the store), stores it, and answers a signed URL
  (an hour), as the comic's PDF is served (comic.md §4a). The web route relays that JSON and the
  Export button opens the URL, so the PDF never passes through a Vercel function (whose response
  limit is about 4.5 MB; a 20-shot storyboard is several MB). Not a `307`: the button fetches the
  route, and a fetch can't follow a redirect to Storage's origin.

### 3.5 The renderer: FLUX.2 [klein] 4B on fal.ai (T026; fal decided 2026-10-09, klein 2026-10-11)

**Decided by Tumo, 2026-10-09; Katlego approves with this PR.** The default renderer was FLUX.1
[schnell] (Apache-2.0) on **fal.ai** (klein since 2026-10-11, below), behind verify.md's `RecordingRenderer`. ComfyUI on a Nebius
GPU (T003) stayed an **optional** backend, for a demo session or the video,
not the default (cut 2026-10-19; never built). Why (the research, 2026-10-09, sources in §8):

- **Nebius Token Factory serves no image model** (re-checked 2026-10-08: `flux-schnell`, `flux-dev`,
  `sdxl` answer 404).
- **A Nebius GPU** (L40S, $1.55/h on demand, $0.74/h preemptible, billed per second, disk billed
  while stopped) would cost about $2,500 to keep up until 15 Dec, so it would be started per session
  and judges would meet cold starts. Whether the hackathon credit covers AI Cloud at all is
  unconfirmed.
- **Cloudflare Workers AI's FLUX.1 [schnell]**, the interim idea in docs/HANDOFF.md §8, takes only
  `prompt` and `steps` (its schema sets `additionalProperties: false`): **no seed, no size**. That
  breaks `seed_for(shot, attempt)` and comic panels at their rect.
- **fal.ai's FLUX.1 [schnell]** takes a `seed`, a custom `image_size` (`{width, height}`) and
  `output_format: "png"`, at **$0.003 per megapixel, rounded up**. It is always on, with nothing to
  start or stop.

"Runs on Nebius" is still met by every Nemotron call on Token Factory (deploy.md §1).

- **The model (Tumo, 2026-10-11): FLUX.2 [klein] 4B, `fal-ai/flux-2/klein/4b`.** On the-red-kite with
  3 attempts a frame and T074–T078's audit it accepted 15 of 22 frames, where schnell at 1 attempt
  accepted 3 of 21: klein drew the ages right, cluttered less, and its stray writing was mostly
  its signature (T077's soft check). `FAL_MODEL` still selects any fal model; schnell remains one
  setting away.
- **One call per attempt.** `POST https://fal.run/{FAL_MODEL}` (default `fal-ai/flux-2/klein/4b`), the
  synchronous endpoint, with `Authorization: Key {FAL_KEY}`. The body is the canonical request:
  `{"prompt": <text>, "image_size": {"width": dw, "height": dh}, "seed": <seed>,
  "num_inference_steps": 4, "num_images": 1, "output_format": "png"}` (fal's OpenAPI schema for
  `fal-ai/flux/schnell`, read 2026-10-09). The answer's `images[0].url` is fetched (`GET`, same
  client) for the PNG; `images[0].width/height` must each be the asked side or up to 31 px more,
  else `RendererError`: klein draws in multiples of 32 (1280 × 720 comes back 1280 × 736), and
  `fit` crops that excess, as it crops the multiple-of-16 rounding below.
- **Draw size, priced to one megapixel.** fal bills each started megapixel, so a frame is drawn at
  `fal_draw_size(width, height)`: scaled down (never up) so that `dw × dh ≤ 1,000,000`, each side
  rounded **down** to a multiple of 16. 1280 × 720 draws as is (921,600 px), and a 1748 × 986 comic
  panel draws at 1328 × 736. The PNG is then fitted to exactly the requested size by §3.3's `fit`
  (cover, centre-crop by at most the rounding excess) and post-processed (the style's grayscale).
  **Every drawing costs about $0.003–0.004.**
- **The prompt sent** is `FramePrompt.text()`, plain: FLUX reads no ComfyUI weight syntax, so nothing
  is escaped and the style's `emphasis` is not applied. The request has no negative prompt, so
  the style's `negative` is not sent (§3.1's "no negations" already keeps what must not appear out of
  the prompt; the audit catches the rest). `RenderedFrame.prompt` is exactly this text. The word
  budget stays `COMFYUI_MAX_WORDS` (55), whatever its name says: raising it for FLUX's text encoder is
  §10's open question, not this change.
- **The render key** (§3.3) is the sha256 of the canonical JSON of `{"model": FAL_MODEL, "request":
  <the body above>}`, then the requested `<width>x<height>`, `RENDER_VERSION` and the post-processing
  step, each after a `"\x1f"`. The store is the cache, as §3.3 says: `exists(frames/<key>.png)` →
  read back, no fal call, `RenderRecord.cached`. A re-run of a script costs nothing for frames it
  already drew.
- **Failures.** A network error, a 429 or a 5xx is retried twice (1 s, then 2 s), then
  `RendererError`. Any other 4xx (a refused key, a rejected body) is `RendererError` at once, naming
  the status and model, never the key or the prompt. `FAL_TIMEOUT_S` (default 60) is httpx's
  per-phase timeout, per try; there is no total deadline beyond three tries. A read timeout on a call
  fal.ai finished is retried and billed again: bounded (at most 3 drawings × 3 redraws × 3 tries per
  attempt) and accepted. `RendererError` → verify's `FAILED` for that frame; the storyboard goes
  on unless the renderer looks down (§4 Failure paths, T066).
- **No failure is silent** (found in the first live run, 2026-10-10: a frame failed and nothing said
  why). Each retry is logged at `WARNING` with the model, the try and the status (or the
  exception's type); `build_storyboard` logs the `RendererError` of a frame that fails at `WARNING`
  with its message. Never the key, the URL's query or the prompt.
- **The cache covers redraws.** Before any call, the keys of all three redraw seeds are checked in
  order; the first stored one is the drawing (a stored drawing was never flagged). So a shot whose
  first seed was flagged costs nothing on a re-run either.
- **Fail closed on the safety result.** An answer whose `has_nsfw_concepts` isn't a non-empty list of
  booleans is `RendererError` (never assumed clean), and a drawing that is uniformly black is treated
  as flagged even when the field says it isn't. A black frame is never stored.
- **CPU work off the event loop.** `fit`, the post-processing and the PNG encoding run in
  `asyncio.to_thread`, as the comic's Pillow work does.
- **A frame fal's safety checker flags never reaches the audit.** The checker is always on for an
  account without fal's authorization to disable it, and a flagged image comes back **black**, with
  `has_nsfw_concepts[0]` true. T062 showed the audit passes a frame that contradicts nothing (a
  black frame has an "unclear" setting and no people), so a black frame must not be returned. The
  renderer redraws with derived seeds `(seed + k × 0x9E3779B1) mod 2³²`, k = 1, 2, which keeps the
  attempt deterministic; the seed actually drawn is the one in the request, the render key and
  `RenderedFrame.seed`. If all three are flagged, `RendererError` ("fal.ai's safety checker blocked
  every drawing of this shot"). Prompts are only the script's own grounded words (§3.1), so a flag
  should be rare.
- **Privacy.** Each prompt (the redacted, grounded script words of one shot: no character names,
  §3.1) is sent to fal.ai. The README says so (T033).
- **Concurrency** `FAL_CONCURRENCY`, default **2**: fal.ai's limit for a new account (2 requests at
  once, rising with purchased credit up to 40; a request over the limit is queued, and its wait counts
  against `FAL_TIMEOUT_S`). The first live run sent 4 at once on a new account and one frame failed
  after its three tries. At 2 a 21-shot storyboard renders in about the time of eleven shots; raise it
  when the account's limit is higher.
- **Cost of the sample:** the-red-kite (21 shots) costs $0.06–$0.19 for the storyboard (1–3
  attempts), the same again for its comic, plus the audit calls. T030's spend cap covers fal.ai too.

**The rendering stage in the job** (`run_job(…, factory)`, web.md §6): progress 60 at its start,
`60 + round(40 × settled / shots)` as frames settle (written with `GREATEST`, so it never moves
back), 100 with `DONE`. `build_storyboard` runs with concurrency `settings.fal_concurrency`
(`FAL_CONCURRENCY`, above). A progress write that fails is logged and skipped: it never fails a shot.

**The job's failure copy.** A `StoryboardError` (the renderer looks down, §4 Failure paths) fails
the upload's job at stage `rendering` with `RENDER_STAGE_FAILED`; web.md §4.1a's
`failed`/`rendering` row shows it verbatim. Anything else in the stage is web.md §4.1's
`UNEXPECTED`. A frame that failed on its own is not a job failure (T066): the job ends `DONE` and
the frame shows its failed card with "Try another render" (web.md §4.3).

**The app's factory.** `create_app(fal=True)` (the module's `app`, never a test's) sets
`app.state.renderer_factory` when `FAL_KEY` and the store are set and the public styles load (the
image ships them since T063: `services/api/styles`, with the repo-root `styles` a symlink to it, deploy.md §6;
a key set with styles that don't load is logged as an error at start-up and the app runs with no
renderer, never half-configured): `fal_factory`'s `lambda screenplay, extraction: FalRenderer(style=<the registry's default>, store=…,
screenplay=…, extraction=…, client=<the app's shared httpx2 client>, key=FAL_KEY, model=FAL_MODEL,
max_words=COMFYUI_MAX_WORDS, timeout_s=FAL_TIMEOUT_S)`, a fresh renderer
per job or attempt, as verify.md §6 says. Without `FAL_KEY` it stays `None`: "Try another render"
and "Make the comic" answer 503 `renderer_unavailable`, as today, and the storyboard job skips the
RENDERING stage (planned is done, as before T026).

## 4. Flow

```mermaid
sequenceDiagram
    participant J as Storyboard job
    participant V as render_until_accepted (verify.md)
    participant R as FalRenderer
    participant P as build_frame_prompt
    participant T as AssetStore (Supabase Storage)
    participant F as fal.ai (FAL_MODEL)
    participant L as frame_audits log (T021)
    J->>R: factory(screenplay, extraction), in the registry's default style
    par each shot in plan order (≤ concurrency at once)
        J->>V: shot, width 1280, height 720, log = _log
        loop attempt 1 .. max_renders
            V->>R: render(shot, attempt, seed_for(shot, attempt), 1280, 720)
            R->>P: shot, screenplay, extraction, style, max_words
            P-->>R: FramePrompt
            R->>R: fal_request per redraw seed; render key of each
            R->>T: exists(frames/key.png)? (each redraw's key, in order)
            alt cached
                T-->>R: PNG
            else not cached
                R->>F: POST fal.run/{FAL_MODEL}; GET images[0].url
                F-->>R: image (flagged or black → the next derived seed)
                R->>R: fit to 1280×720; grayscale; PNG
                R->>T: put(frames/key.png)
            end
            R-->>V: RenderedFrame (prompt = the text sent)
            V->>V: describe, judge, checks, verdict (verify.md)
            V->>J: _log(audit)
            J->>L: log(audit, renderer.record(audit.shot, audit.attempt).asset)
        end
        V-->>J: FrameOutcome (PASSED / WARNED / WITHHELD / FAILED)
    end
    J->>J: the renderer down (§4 Failure paths) → StoryboardError; else Storyboard, FAILED frames included
    J-->>J: Storyboard (the PDF is built on demand by T027's endpoint, not here)
```

- **The job** calls `build_storyboard(…, concurrency=settings.fal_concurrency)`; one synchronous fal call per
  drawing (§3.5).
- **The writer and its hooks** (T021). `build_storyboard` takes T021's `FrameWriter` (verify.md
  §6) and, for each shot, calls `frame_hooks(writer, renderer, shot)` to get the `(log, on_state)`
  pair it passes to `render_until_accepted`: `log` writes each attempt's `frame_audits` row with the
  path `renderer.record(shot, attempt).asset` (the renderer records an attempt before returning it,
  so the lookup can't miss), and `on_state` writes the shot's `frames` row, with the asset only on a
  `PASSED` or `WARNED` terminal state. "Try another render" uses the same `frame_hooks`, so every
  `frames` row is written by one path and the asset rule is stated once.
- **Seeds** are verify.md's `seed_for(shot, attempt)`; the renderer never picks one. FrameFlow's
  random regenerate seed is gone: an attempt is reproducible, and "another attempt" is the next
  attempt number.
- **Concurrency** defaults to 2 (`FAL_CONCURRENCY`): fal.ai's limit for a new account (§3.5); two lets
  shot *n + 1* render while shot *n* is audited.
- **Frame state** is verify.md §5's state machine, unchanged; this design adds no states. Only a
  `PASSED` or `WARNED` frame's image appears in the storyboard, the JSON or the PDF.
- **ComfyUI calls** (T003): cut 2026-10-19; never built.

**Failure paths:**

- **A renderer error** (fal.ai unreachable, a rejected request, a render error, a timeout,
  a drawing the safety checker blocked) → `RendererError` → verify.md's `FAILED` for **that frame**
  (`failure` `render`), logged with the renderer's message; **the storyboard goes on** with the
  other shots, and the job ends `DONE` with the failed frame on the board, its card offering "Try
  another render" (T066, 2026-10-10: in the first live runs a single passing error stopped the whole
  storyboard three times). No fallback provider and no placeholder image (§8).
- **The renderer looks down** → no new shot starts, the shots in flight are **awaited**, not
  cancelled (their drawings and audits are paid for; their rows are kept), then the job fails with
  `StoryboardError` (`RENDER_STAGE_FAILED`). "Down" is: **no frame drawn yet** (no shot has
  reached `AUDITING`, which only a drawing does: a frame still being judged counts as drawn) and
  **`min(3, shots)` frames `FAILED`**. A wrong key, an account out of credit or an outage fails every shot the same way;
  without this, a 21-shot storyboard would spend half an hour on timeouts to say so. Once one frame
  has been drawn, failures are taken one frame at a time.
- **A prompt whose fixed parts exceed the word budget** → `PromptError`, raised by the renderer as
  `RendererError` → `FAILED`, naming the shot: a configuration error (style or budget), never a
  truncated prompt.
- **An audit error or the last attempt failing** → `WITHHELD` (verify.md): the block shows the card;
  the job succeeds. A withheld frame is information, not a failure.
- **Storage answers 429 or a 5xx (Cloudflare's 520–524 included), or the connection drops** →
  `SupabaseStore` makes the same call again (T070): 3 attempts in all, 1 s then 2 s apart, each
  retry logged as a warning with the operation and the status, never the key or the path. A `put` is safe to
  repeat: an upload that landed before its answer was lost comes back 409, which is success.
- **Storage still failing after the third attempt, or any other 4xx** → `StorageError` → the job
  fails. A frame that can't be stored can't be logged with its asset, and verify.md logs every attempt.
- **An unknown style key** → `StyleError` before anything renders.

## 5. State

The frame's lifecycle is **verify.md §5**, unchanged; not redrawn here. A storyboard is produced by
the upload's `Job` in its `RENDERING` stage (web.md §3, §5); `build_storyboard` reports
`progress(settled, total)` after each frame reaches a terminal state, and the runner maps it into the
job's 60–100 band. The PDF is not part of the job. The style registry is loaded
once at start-up and immutable.

## 6. Contracts

```python
# app/storyboard/styles.py
class StyleOrigin(StrEnum): PUBLIC = "public"; PRIVATE = "private"
@dataclass(frozen=True) class Style: key: str; label: str; description: str; medium: str; finish: str; emphasis: float | None; negative: str; grayscale: bool; default: bool; origin: StyleOrigin
@dataclass(frozen=True)
class StyleRegistry:
    styles: Mapping[str, Style]
    default: str
    def get(self, key: str | None) -> Style: ...        # None → default; unknown → StyleError
    def public(self) -> tuple[Style, ...]: ...          # sorted by key
class StyleError(ValueError): ...
SUBJECT_WORDS: frozenset[str]                           # §3.2's list
PUBLIC_STYLES: Path                                     # services/api/styles, in the API image (T063; deploy.md §6)
def load_styles(public_dir: Path, private_dir: Path | None) -> StyleRegistry: ...

# app/characters/redact.py  (built by T008)
NAME_STOP_WORDS: frozenset[str]                                # §3.1's list
def name_tokens(names: Sequence[str]) -> frozenset[str]: ...   # words of normalise(name), for each name, minus NAME_STOP_WORDS
NAME_PARTICLES: frozenset[str]                                 # T092, §3.1: van der de du da von le la del dos den ter bin (lower case)
def named_as_figure(text: str, tokens: Collection[str]) -> bool: ...   # T092, §3.1: some run of `tokens` in `text` is Title case, or UPPER case followed by "(", and not possessive
def _name_runs(text: str, tokens: Collection[str]) -> list[tuple[int, int]]: ...   # T092: (first, last) word index of each maximal run, particles joined; `_redact` and `named_as_figure` both use it
def redact_names(text: str, character: str, others: Sequence[str]) -> str: ...   # characters.md rule 2: this character → "a person", others → "another person"
def redact_all(text: str, characters: Sequence[str]) -> str: ...                 # every character's name tokens → "a person"
# app/characters/labels.py (T052; its own module because it imports app.grounding, whose filter imports redact.py.
# app/characters/__init__.py must never import labels, or app.grounding -> filter -> app.characters -> labels -> app.grounding cycles)
def animals(extraction: Extraction) -> dict[str, str]: ...                      # character name → species, for every animal (§3.1 Labels: own species, or bound to one by match_speaker)
def redaction_labels(extraction: Extraction, screenplay: Screenplay, only: str | None = None) -> dict[str, str]: ...  # name token → label (§3.1 Labels), in rank order (persons, animals, named props, `it`; extraction order within each); `only` limits it to one character's name and paired other names. The screenplay is for pairing (a shared scene)
# app/characters/redact.py
def redact(text: str, labels: Mapping[str, str]) -> str: ...                    # T052: redact_all's matching (runs, possessives, titles), each run → the label of its token that comes first in `labels` (rank order); a possessive `it` is `its`

# app/storyboard/prompt.py — pure
class PartKind(StrEnum): STYLE = "style"; FRAMING = "framing"; SETTING = "setting"; TIME = "time"; COUNT = "count"; AGE = "age"; SEX = "sex"; LOOK = "look"; PLACEMENT = "placement"; ACTION = "action"   # LOOK: T079
def introduced_years(character: str, screenplay: Screenplay) -> int | None: ...   # T086, pure: `THEO (9)` → 9, `DANIEL (40s)` → 40; None without an introduction. verify's age check reads it
def introduced_age(character: str, screenplay: Screenplay) -> tuple[str, Span] | None: ...   # T074, pure
#   the first Action element, in scene and element order, where `CHARACTER (` follows the name in capitals
#   and the parenthesis opens with a number, an optional `s`, an optional years word (`years old`, `year-old`,
#   `yrs`, `yo`) and then `,` `;` or `)`: ("a <n>-year-old" | "a person in their <n>s", that element's span);
#   `(5 months)`, `(6 weeks)`, `(30s-40s)`, `(early 30s)` give None: a miss draws no age, a wrong one would
#   state one the script contradicts (the T074 review)
#   None when no introduction gives one. Never a word the script doesn't have but the age's own number
#   T079: the phrase carries the sex `introduced_sex` reads: "a 10-year-old girl", "a man in his 70s"
def introduced_sex(character: str, screenplay: Screenplay) -> Literal["female", "male"] | None: ...   # T079, pure
#   T096: a sex noun in the appositive before the name; T100: a possessive Her or His opening the next
#   sentence of the same Action element (SENTENCE_END), read from the untruncated element text, only
#   when the introducing sentence (after its parenthesis, to that boundary) names no one else, holds no
#   SEX_WORDS, CONFLICT_WORDS, them or _PERSON_NOUNS word and no next introduction
# app/grounding: NOT_POSSESSED (public; was filter.py's _NOT_POSSESSED), exported by app.grounding
def title_sex(character: str) -> Sex | None: ...   # T082, pure: the name's first word, upper case, a trailing
#   full stop ignored, looked up in app/characters/sex.py's SEX_TITLES (female: MRS, MS, MISS, MADAM, MADAME,
#   LADY, MAMA, GOGO, OUMA, AUNTIE, AUNT, TANNIE, SISTER, QUEEN, PRINCESS; male: MR, SIR, LORD, BABA, OUPA,
#   UNCLE, OOM, BROTHER, KING, PRINCE): `MAMA THEMBI` → female, `MR. DUBE` → male, `OFFICER MOLOI` → None
#   (OFFICER, DR, NURSE give no sex). A title other than these fails closed (None)
def character_sex(character: str, screenplay: Screenplay, extraction: Extraction) -> tuple[Sex, str] | None: ...
#   T082, pure: the sex every source that gives one agrees on, with its evidence: introduced_sex (T079; the
#   introducing Action element's text), title_sex (the name), the grounded Entity.sex (Entity.sex_quote's text);
#   None when none gives one, or two disagree. With several agreeing, the evidence is the first of sex_quote, the
#   introduction, the name; cut to 160 characters at a word. Each source is a word of the script keyed by the
#   code's fixed vocabulary, so the prompt's "girl" traces to "She", "MAMA" or "her" in the script. `AGE` and
#   `SEX` (§3.1), verify's render_spec and the report (learning.md) use it
#   in that same introducing element: "she"/"he" in the introducing sentence (from the name to the sentence's
#   end or the next `NAME (` introduction) and "her"/"his" inside its `introduced_look`, whole words, any case;
#   one sex only, else None ("watches her" after MAMA THEMBI is Siphokazi, an object: not counted; a later
#   sentence's "She waves" may be anyone). T079 review: the stretch also ends at another character's name
#   (any dialogue cue or `NAME (` introduction, titles aside): `watches SIPHO as he counts` is Sipho's "he";
#   a prop in capitals (RED KITE) is no name
def introduced_look(character: str, screenplay: Screenplay) -> tuple[str, Span] | None: ...   # T079, pure
#   §3.1's LOOK: the parenthesis's items after the age and the comma phrase right after it, each at most 8
#   words, verbatim (whitespace collapsed), joined by ", "; the introducing element's span; None if empty.
#   T079 review: an item with a parenthesis or a number, starting with and/who/then/as/while/but, or naming
#   another character ("Grace's daughter") is no look; nor is anything when the parenthesis doesn't close
#   before the sentence ends
@dataclass(frozen=True) class PromptPart: kind: PartKind; text: str; span: Span | None
@dataclass(frozen=True)
class FramePrompt:
    parts: tuple[PromptPart, ...]
    trimmed: int
    def text(self) -> str: ...                          # ", ".join(p.text for p in parts)
class PromptError(ValueError): ...                      # the fixed parts alone exceed max_words (names the shot)
FRAMING_WORDS: Mapping[Framing, str]                    # §3.1's table
PLACEMENT_PHRASES: frozenset[str] = frozenset({"one figure on the left, one on the right"})
OFF_SCREEN_MARKS: tuple[str, ...] = ("V.O.", "O.S.", "O.C.", "OFF")   # comic.md §3's list
def heading_span(scene: Scene) -> Span: ...             # Span(scene.span.page, scene.span.line_start, scene.span.line_start)
def time_source(scenes: Sequence[Scene], scene_index: int) -> int | None: ...   # the scene resolve_times took the clock from
def visible_characters(shot: Shot, screenplay: Screenplay, extraction: Extraction) -> tuple[str, ...]: ...  # §3.1; people in shot.characters (no animals), same order (T052: the screenplay, for pairing, and the extraction); T093: with no one else on screen, `pronoun_figure`'s person
def pronoun_sentences(text: str) -> tuple[tuple[str, Sex | None], ...]: ...   # T093, pure: `text` (already redacted and collapsed) split at SENTENCE_END, in order (joined by one space they give `text` back), each with the sex of an opening exact "He"/"She", else None
def _shown_characters(shot: Shot, screenplay: Screenplay, extraction: Extraction) -> tuple[str, ...]: ...   # T093: today's visible_characters body, Listeners included
def pronoun_figure(shot: Shot, screenplay: Screenplay, extraction: Extraction) -> str | None: ...
#   T093: only when _shown_characters is empty (never calls visible_characters): the one candidate
#   (shot.characters, no animal, no off-screen speaker of the shot) whose sex every covered He/She piece
#   gives, when every candidate's sex is known (character_sex) and exactly one has it; else None
# visible_characters, T093: _shown_characters' result if not empty, else (pronoun_figure,) if a name, else ()
# build_frame_prompt, T093: a He/She piece whose sex no person of visible_characters' final result has (all
#   their sexes known) is left out; an element's kept pieces become one ACTION part per consecutive run,
#   the one-space join, same span, in element then sentence order; an element with none left gives no part

# app/grounding/__init__.py, T093: SENTENCE_END (filter.py's _SENTENCE_END, renamed and exported; _pronoun_pieces uses it)
def build_frame_prompt(shot: Shot, screenplay: Screenplay, extraction: Extraction, style: Style, *,
                       max_words: int, placement: str | None = None) -> FramePrompt: ...
#   placement must be in PLACEMENT_PHRASES (else ValueError); T026 passes None (T025, which would pass
#   characters.md FrameReferences.placement, was cut 2026-10-19); a placement with len(visible_characters) != 2 is a ValueError;
#   a shot.time_of_day that isn't the absolute time of time_source's heading is a ValueError (the
#   planner copies resolve_times, so any other clock is one the headings don't give)

# app/storyboard/prompts.py — T008's live check (python -m app.storyboard.prompts <script.pdf> [--style KEY])
async def main(argv: list[str]) -> int: ...             # parse, extract, plan; print each shot's parts, kinds and spans
#   run as `sys.exit(asyncio.run(main(sys.argv[1:])))` under `if __name__ == "__main__"`, like app/shots/run.py;
#   max_words = Settings().comfyui_max_words (COMFYUI_MAX_WORDS, T008), the same value fal_factory passes FalRenderer

# app/storyboard/workflow.py — pure (ComfyUI's graph helpers, T003: cut 2026-10-19; never built)
RENDER_VERSION: int = 1
def fit(png: bytes, width: int, height: int) -> Image.Image: ...                  # cover + centre-crop, exact size
def postprocess(image: Image.Image, grayscale: bool) -> Image.Image: ...          # the style's pass: grayscale, then autocontrast(cutoff=0.5)
def png_bytes(image: Image.Image) -> bytes: ...
def render_key(graph: Mapping[str, Any], width: int, height: int, postprocess: str) -> str: ...   # sha256 hex, §3.3; graph is {"model", "request"} (§3.5)

# app/storyboard/render.py
class RendererError(RuntimeError): ...
@dataclass(frozen=True) class RenderRecord: shot: tuple[int, int]; attempt: int; key: str; asset: str; prompt: FramePrompt; cached: bool; seconds: float | None
class RenderRecorder(RecordingRenderer, Protocol):     # what build_storyboard needs: a RecordingRenderer whose records are RenderRecords
    style: Style
    def record(self, shot: tuple[int, int], attempt: int) -> RenderRecord: ...
RENDER_STAGE_FAILED: str = "No frame could be drawn, so the storyboard stopped. Try again in a few minutes by uploading the script again."
# ComfyRenderer (T003): cut 2026-10-19; never built. FalRenderer is the only renderer.

# app/storyboard/fal.py (T026, §3.5)
MAX_PIXELS: int = 1_000_000                              # fal bills each started megapixel
def fal_draw_size(width: int, height: int) -> tuple[int, int]: ...   # scale down to ≤ MAX_PIXELS, each side floored to a multiple of 16
def fal_request(prompt: str, seed: int, draw: tuple[int, int]) -> dict[str, Any]: ...   # the canonical body, §3.5
class FalRenderer:                                      # implements app.verify.RecordingRenderer
    def __init__(self, *, style: Style, store: AssetStore, screenplay: Screenplay, extraction: Extraction,
                 client: httpx2.AsyncClient, key: str, model: str = "fal-ai/flux/schnell",
                 max_words: int = 55, timeout_s: float = 60.0,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None: ...
    async def render(self, shot: Shot, attempt: int, seed: int, width: int, height: int) -> RenderedFrame: ...
    #   prompt → render key → store hit, or fal call (+ redraws on a flag) → fit → post-process → put; records before returning
    def record(self, shot: tuple[int, int], attempt: int) -> RenderRecord: ...     # KeyError if not rendered
def fal_factory(registry: StyleRegistry, store: AssetStore, client: httpx2.AsyncClient,
                settings: Settings) -> RendererFactory: ...   # §3.5 The app's factory; the registry's default style

# app/storage/store.py
class StorageError(RuntimeError): ...
class AssetStore(Protocol):
    async def exists(self, path: str) -> bool: ...
    async def get(self, path: str) -> bytes: ...
    async def put(self, path: str, data: bytes, content_type: str) -> None: ...   # idempotent: an existing path is left as is
    #   SupabaseStore uploads without upsert and treats Supabase's 409 "already exists" as success
    async def signed_url(self, path: str, expires_in_s: int) -> str: ...
    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]: ...   # T122
    #   one link per path, in the order given (a path given twice is signed twice, in its place);
    #   [] for no paths, with no request. SupabaseStore: one POST /storage/v1/object/sign/{bucket}
    #   {"expiresIn": n, "paths": [...]} per 100 paths, the chunks sent in order and their links
    #   joined (100 is our limit, to keep a request small, not Supabase's); the answer keeps the
    #   request's order and its links have signed_url's form (both measured, §9 T122). All or
    #   nothing, as signed_url is today: one missing object fails the whole call. An item whose
    #   "signedURL" is null (its "error" set: a missing object) raises
    #   StorageError("signed_urls: storage could not sign <k> of <n>"), naming no path; T070's retry
    #   applies to each request as to signed_url
class SupabaseStore:                                    # Supabase Storage REST (/storage/v1/object/...), secret key, httpx2
    def __init__(self, *, url: str, secret_key: str, bucket: str, client: httpx2.AsyncClient,
                 max_attempts: int = 3,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None: ...
    #   T070: every operation (exists, get, put, signed_url, signed_urls) is tried up to max_attempts times on
    #   429, 500, 502, 503, 504, 520-524 or an httpx2.TransportError, sleeping 1 s, then 2 s (the
    #   LLM client's policy, app/llm/client.py); any other status is answered at once, as today.
    #   Out of attempts: StorageError("<op>: storage answered <status> after <n> attempts") or
    #   StorageError("<op>: storage unreachable after <n> attempts"); a TransportError never escapes

# app/api/v1/projects.py (T122): the two reads that sign many links sign them in one call
#   read_frames (GET /projects/{id}/frames): every frame in ACCEPTED with an asset, in frames
#   order, through one store.signed_urls(...); each view gets its own link, the others None, as
#   before. read_comic (GET /projects/{id}/comic): [*comic.pages, comic.pdf] through one
#   signed_urls; the last link is the PDF's. A StorageError is 503 storage_unavailable, as before.
#   GET /projects/{id}/storyboard/pdf keeps signed_url (one link). Responses are unchanged.

# app/storyboard/model.py
type Rect = tuple[int, int, int, int]
@dataclass(frozen=True) class StoryboardFrame: shot: tuple[int, int]; state: FrameState; asset: str | None; prompt: str | None; seed: int | None; attempts: int; verdict: Verdict; noted_checks: tuple[Check, ...]; failure: str | None = None   # T027: "render" or "restart" for FAILED, from the row
@dataclass(frozen=True) class Storyboard: style: str; width: int; height: int; frames: tuple[StoryboardFrame, ...]; renders: int; cached: int
@dataclass(frozen=True) class SourceLine: text: str; speaker: bool = False; of: str | None = None   # T103: a speaker line prints Bold; `of` a speech line's label
@dataclass(frozen=True) class Block: shot: tuple[int, int]; y: int; frame_rect: Rect | None; title: str; span_label: str; audit_line: str | None; source_lines: tuple[SourceLine, ...]; continued: bool   # T103: SourceLine, not str
# T103, app/storyboard/document.py: _source_lines(shot: Shot, scene: Scene) -> tuple[SourceLine, ...] (from the
#   covered elements; a Dialogue's speaker run when its label differs from the previous element's,
#   then its text's lines wrapped; an Action's lines wrapped; the fallback to source's lines);
#   DOCUMENT_VERSION 2 -> 3, so every cached PDF is drawn again with its speakers
@dataclass(frozen=True) class StoryboardPage: number: int; scene_index: int; blocks: tuple[Block, ...]
class StoryboardError(RuntimeError): ...

# app/storyboard/build.py
def frame_of(outcome: FrameOutcome, record: RenderRecord | None) -> StoryboardFrame: ...   # pure, §3.3; record = the last attempt's
async def build_storyboard(model: NebiusChatModel, renderer: RenderRecorder, plan: ShotPlan,
                           screenplay: Screenplay, extraction: Extraction, *,
                           writer: FrameWriter,                                # T021's; frame_hooks(writer, renderer, shot) per shot (§4)
                           progress: Callable[[int, int], Awaitable[None]] | None = None,   # (settled, total) after each terminal frame
                           width: int = 1280, height: int = 720, concurrency: int = 2,
                           max_renders: int = 3) -> Storyboard: ...

# app/storyboard/document.py (T027)
DOCUMENT_VERSION: int = 3   # T103
def frames_from_rows(rows: Sequence[FrameRow], audits: Sequence[FrameAuditRow]) -> tuple[StoryboardFrame, ...]: ...   # pure, §3.4 From the rows; audits are the project's storyboard-target rows, any order
def layout_document(frames: Sequence[StoryboardFrame], plan: ShotPlan, screenplay: Screenplay,
                    style: Style) -> tuple[StoryboardPage, ...]: ...   # pure; measures with Courier Prime (the style's label sizes the footer); one block per plan shot (a shot with no frame is a ValueError)
def render_pdf(pages: Sequence[StoryboardPage], frames: Sequence[StoryboardFrame], plan: ShotPlan,
               screenplay: Screenplay, style: Style, images: Mapping[tuple[int, int], bytes]) -> bytes: ...
#   images: PNG bytes of the PASSED/WARNED frames only; Pillow page images, one PDF via save_all
def document_key(project_id: uuid.UUID, style: Style, frames: Sequence[StoryboardFrame]) -> str: ...   # sha256 hex, §3.4
async def export_pdf(store: AssetStore, project_id: uuid.UUID, style: Style, plan: ShotPlan,
                     screenplay: Screenplay, frames: Sequence[StoryboardFrame]) -> str: ...
#   the store path of the project's PDF: a hit on storyboards/<key>.pdf, else the accepted frames read
#   from the store, render_pdf, put. StorageError propagates.
```

**Storyboard JSON**: **not built** (T027, 2026-10-10). It was the `run` CLI's export, and T026 has no
run CLI (§7); the web pages read `frames` rows (web.md §6), and nothing else would call `to_json`.
The shape is kept here for a later export:

```json
{
  "style": "clean", "width": 1280, "height": 720,
  "frames": [{
    "shot": [0, 1], "framing": "wide", "movement": "static",
    "span": {"page": 1, "line_start": 5, "line_end": 9},
    "source": "The kettle screams. NANDI lifts it off the flame.",
    "state": "passed", "verdict": "pass", "noted_checks": [],
    "attempts": 1, "seed": 2718281828,
    "prompt": "storyboard sketch, pencil drawing, grayscale, monochrome, loose linework, wide shot, inside lighthouse kitchen, night, one figure, The kettle screams. a person lifts it off the flame.",
    "frame_url": "https://…/storage/v1/object/sign/panelwise/frames/…png?token=…"
  }]
}
```

`frame_url` is present only for `passed` and `warned`; a `withheld` frame has none. `source` and
`span` are the shot's, so the web app shows "from page 1, lines 5–9" on every frame (SPEC US1).

**Environment** (added to `.env.example` and deploy.md §6: `PANELWISE_PRIVATE_STYLES` and `COMFYUI_MAX_WORDS` by T008, `FAL_*` and Storage by T026):

| Variable | Where | What |
|---|---|---|
| `FAL_KEY` | API, **secret** | fal.ai's API key (§3.5). Unset: no renderer, "Try another render" and "Make the comic" answer 503, the storyboard job ends at planning |
| `FAL_MODEL` | API | the fal model id, default `fal-ai/flux-2/klein/4b` (2026-10-11; `fal-ai/flux/schnell` before) |
| `FAL_TIMEOUT_S` | API | per-call deadline, default 60 |
| `FAL_CONCURRENCY` | API | frames drawn at once, default 2 (fal.ai's limit for a new account); at least 1, or the API refuses to start |
| `COMFYUI_MAX_WORDS` | API | the frame prompt's word budget (§3.1), default 55 (CLIP's 77 tokens; the name predates fal; raising it for FLUX is §10's open question) |
| `SUPABASE_STORAGE_BUCKET` | API | the private bucket for frames and PDFs, default `panelwise` |
| `PANELWISE_PRIVATE_STYLES` | API, optional | a directory of private style TOMLs outside the repo (already in `.env.example`); never set on the hosted demo |

**Workflow**: none (ComfyUI, T003: cut 2026-10-19; never built).

## 7. Structure

| Path | New? | Responsibility | Task |
| --- | --- | --- | --- |
| `services/api/app/storyboard/{__init__,styles,prompt,prompts}.py` | new | §3.1–§3.2, §6; `prompts.py`: `python -m app.storyboard.prompts <script.pdf> [--style KEY]` parses, extracts and plans on the real account and prints every shot's prompt parts with their spans, so the team can read the prompts before any frame is drawn | T008 |
| `services/api/app/storyboard/{model,workflow,render,build}.py` | new | §3.3, §4, §6: `fit`, the render key and post-processing, `RenderRecord`, `build_storyboard`. No separate run CLI: `build_storyboard` writes through T021's writer, so the live check is an upload through the local stack (§9) | T026 |
| `services/api/app/storyboard/document.py` | new | §3.4, §6: `frames_from_rows`, the layout, the PDF, the document key, `export_pdf` (no JSON, no `run`: §6) | T027 |
| `services/api/app/api/v1/projects.py`, `schemas.py`, `app/main.py` | changed | `GET /projects/{id}/storyboard/pdf` (web.md §6); `app.state.styles` loaded at startup (§3.4 Style) | T027 |
| `services/api/app/characters/{__init__,redact}.py` | new | `NAME_STOP_WORDS`, `name_tokens`, `redact_names`, `redact_all` (moved here from characters.md's `portraits.py` so frames can use them before T025) | T008 |
| `services/api/app/storage/{__init__,store}.py` | new | `AssetStore`, `SupabaseStore` (§6 contract; deploy.md §7), built with its first consumer, the upload (web.md §4.1); T026 uses it for frames; T070 retries a transient failure | T053, T070 |
| `services/api/app/storage/store.py`, `app/api/v1/projects.py`, `tests/fakes.py` | changed | `signed_urls` (one batch request per 100 links); `read_frames` and `read_comic` sign in one call | T122 |
| `services/api/app/core/config.py`, `.env.example`, `docs/design/deploy.md` §6 | changed | §6's environment | T008 (`PANELWISE_PRIVATE_STYLES`, `COMFYUI_MAX_WORDS`), T026 (`FAL_KEY`, `FAL_MODEL`, `FAL_TIMEOUT_S`, `FAL_CONCURRENCY`, `SUPABASE_STORAGE_BUCKET`) |
| `styles/*.toml`, `styles/README.md` | new / changed | the styles the team keeps public (§10); the file format | T008 |
| `services/api/app/storyboard/fal.py` | new | §3.5: `FalRenderer`, `fal_draw_size`, `fal_request`, `fal_factory` | T026 |
| `services/api/app/projects/job.py`, `app/main.py` | changed | the RENDERING stage in `run_job` (`factory`), `renderer_factory` from `fal_factory` when `FAL_KEY` is set | T026 |
| `infra/comfyui/workflows/frame.json` | not built | (ComfyUI, T003: cut 2026-10-19; never built) | T003 |
| `services/api/assets/fonts/{CourierPrime-Regular,CourierPrime-Bold}.ttf`, `CourierPrime-OFL.txt` | new | the document's font and its licence | T027 |
| `services/api/app/images/README.md` | kept, marked not built | the provider chain and cache it described are not built (§8); the renderer lives in `storyboard/` | T026 |
| `docs/design/reference/storyboard/*.png` | new | the sample's rendered pages, the visual reference | T027 |
| `services/api/tests/{storyboard,storage,characters}/` | new | §9 | T008, T026, T027 |
| `CHANGES-FROM-FRAMEFLOW.md` | changed | a row per ported file | T008, T026, T027 |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
|---|---|---|
| The model on fal (Tumo, 2026-10-11) | FLUX.2 [klein] 4B: 15 of 22 the-red-kite frames accepted at 3 attempts with the T071–T078 audit | FLUX.1 [schnell] (the 2026-10-09 choice): 3 of 21 at 1 attempt on the same script, adults for children, clutter and painted gibberish; klein on Cloudflare Workers AI (#97/#98): the same model, but fal was already built, gated and live-tested, and `FAL_MODEL` makes the model one setting |
| The renderer (2026-10-09, §3.5) | FLUX.1 [schnell] on fal.ai: seed, any size, PNG, $0.003 per ≤ 1 MP frame, always on | ComfyUI on a Nebius L40S as the default (≈ $2,500 to stay up to 15 Dec, or cold starts for judges; credit coverage unconfirmed: kept optional, T003); Cloudflare Workers AI FLUX.1 [schnell] (no seed and no size in its schema: breaks seeded attempts and comic panels); Nebius Token Factory (no image model, 404 on 2026-10-08). Sources: nebius.com/prices, the Cloudflare model schema, fal.ai's model page and OpenAPI |
| A character's age in the prompt (T074) | an `AGE` part from the script's own introduction (`LERATO (10)` → "a 10-year-old") | only "a person" (before T074): on 2026-10-10 the-red-kite drew Lerato (10) and Mokgosi (70s) as young adults again and again, and T072's audit then withheld those frames; the age in every name's label: "a person in their 70s's workshop"; a gender word: the script's parenthesis doesn't give one |
| A character's sex beyond the introduction (T082; Tumo, 2026-10-11) | `character_sex`: the introduction's pronouns, a sex title, and the extraction's grounded `sex_word`, all agreeing | the introduction alone (T079): on 2026-10-11 sipho-and-siphokazi's Sipho, Siphokazi and Mama Thembi got no sex, were drawn as old men and boys, and 8.3 was accepted wrong (L002); the first source only: a disagreement means one of them misread the script, so none is drawn; "a woman" / "a man" for an unaged character: a baby with no age in numbers would be drawn grown. **Cost:** a first-word title that can be a given name (`KING JONES`, `PRINCE`, `MISS`) sexes that character; `character_sex` drops it when another source disagrees |
| A character's sex and look in the prompt (T079) | the sex word from the introduction's pronouns; the look verbatim from the introduction | the age alone (T074): on 2026-10-11 klein drew Lerato as a boy in 9 of 11 accepted frames, short hair, no braids; a sex word from any pronoun near the name: `watches her` after Mama Thembi is someone else; the whole introducing line: its action (`grips a RED KITE`) is that moment's event |
| A line heard off screen (T079) | its listeners are the planner's other characters | no one (before T079): the prompt asked for nothing and the frame was an empty roof |
| A plain background (T074) | `plain background` in the clean style's `finish` | the scene as it comes: schnell fills a workshop with jugs, books, pots and frames, and the judge withholds the frame for them (13 of 19 withheld frames failed on such objects on 2026-10-10); a per-shot phrase: the style is how every frame is drawn |
| What a frame prompt is made of | tagged parts from the shot's grounded fields, each script part carrying its span (§3.1) | FrameFlow's `storyboard_description` (free text: shots.md dropped it) or its fallback to the scene's first 400 characters of action (a cut mid-sentence, and other shots' events); a model writing the prompt: invention with extra steps |
| Dialogue in the prompt | never; speakers enter as the `COUNT` | the speech text: not visible, and the surest way to get letters in the art (hard `TEXT_IN_FRAME`) |
| Camera movement in the prompt | never; printed under the frame | FrameFlow's movement words: a still can't pan, and "handheld" reads as blur |
| Entity quotes | only as the covered elements' own text; nothing from outside the shot; appearance comes from the introduction's `AGE`/`SEX` and `LOOK` parts (T074, T079; T025's portraits were cut 2026-10-19) | a character's first descriptive quote or a prop's first mention: each is an introduction that carries its own moment's event ("pours tea") into a shot that doesn't have it, which the audit then fails (`UNSCRIPTED_OBJECT`). **Cost:** a dialogue-only shot is drawn from its setting, time, figure count and its speakers' age, sex and look alone |
| A sentence whose subject is only He or She (T093; Tumo, 2026-10-13) | drawn on the one cast person of that sex when no one else is on screen; left out when no drawn figure has that sex; every sex known, else nothing changes. **Consequence:** the pronoun figure is on screen for the audit, so `NO_CHARACTER` (hard) now applies to those shots | dropping every pronoun-subject sentence: 44 of the 52 measured are about the drawn figure, and the shot's action would go; resolving a pronoun across dialogue to its speaker or listener: "Keep it. You earned it." / "He looks at the ball." needs who is spoken to, which the script doesn't mark (L016's T088 note); asking the describer or judge who did what: an audit can't see a salute |
| Figure count | `visible_characters`: planner characters the covered elements show on screen. Loose on shared name tokens ("JOHN SMITH"/"JOHN DOE") and possessives ("reads NANDI's letter"); both only change the count word | `len(shot.characters)`: the planner lists who it thinks fits, and `V.O.`/`O.S.` speakers aren't in the frame. **Known effect:** verify.md's soft `MISSING_CHARACTER` checks `shot.characters`, so a shot with an off-screen speaker ends `WARNED` with a `missing_character` note; accepted (it's soft and true), see §10 |
| Unextracted names | accepted residual risk, pinned by a test | redacting every ALL-CAPS word: sound effects and emphasis ("SLAM", "NOW") are written the same way and would become "a person" |
| Over-long prompts | drop whole parts from the tail, then cut the last kept part at a sentence end or word | cutting mid-word or mid-quote at random; letting the encoder truncate silently (it drops the end, whatever is there) |
| Names | redacted in every script part with `redact`: a person → "a person", an animal → "the <species>", a named prop's other name → "the <prop>", else "it" (T052; `redact_all`, "a person" only, before it) | names in the prompt: characters.md rule 1 |
| Style format | one TOML per style, stdlib `tomllib`, validated at start-up | FrameFlow's Python dict: a private pack would have to be code, imported from outside the repo |
| Public / private split | two directories, same validation, private can't shadow or be default | a `private = true` flag in the file: one directory, so a private file could land in the public repo by accident |
| FrameFlow's `classic` style | dropped | it kept a pre-styles cache key and its prompt used the negations CLIP can't read ("no borders", "Do not add characters") |
| FrameFlow's `fast` draft (draw small, upscale) | dropped | a CPU-time saving measured on SDXL-Turbo on a laptop; its other effect, stopping a close subject being drawn twice on an off-native canvas, was to be ComfyUI's `draw_size`'s job (T003: cut 2026-10-19) |
| Image providers | one: fal.ai (§3.5) | FrameFlow's chain: A1111 WebUI (not deployed), Gemini (paid, not Nebius), and the labelled mock image (a placeholder, AGENTS.md §2a: a job without a renderer fails loudly instead) |
| Image cache | the content-addressed Storage path is the cache | FrameFlow's disk record/replay cache (a dev tool whose key named a Gemini model even for ComfyUI images) and Redis (gone: deploy.md); tests use a fake renderer, so replay mode has no job left |
| Model choice | `FAL_MODEL`, in the render key (§3.5) | FrameFlow's "first checkpoint ComfyUI lists": changes the pixels without changing any key |
| Seeds | verify.md's `seed_for(shot, attempt)` | FrameFlow's per-subject hash plus a random regenerate seed: not reproducible |
| Size mismatch between request and model | draw at ≤ 1 MP in multiples of 16 (`fal_draw_size`, §3.5), cover-resize, crop only the rounding | drawing at the requested size (off-native sizes duplicate subjects: FrameFlow saw a close subject drawn twice) |
| Grayscale | a pixel pass before the audit, per style | in the prompt (SDXL-Turbo ignores it); after the audit (the audit would judge different pixels than are shown) |
| PDF | Pillow page images, one PDF with `save_all` (comic.md's choice) | FrameFlow's hand-written PDF writer (base-14 fonts, so it folded em dashes and curly quotes: not verbatim); reportlab: a second PDF library. **Cost:** the PDF's text isn't selectable |
| What prints under a frame | the shot's verbatim `source`, never truncated, plus its span | FrameFlow's frame description cut at four lines: a storyboard block must show exactly the lines it cites |
| One PDF per | screenplay, scenes starting new pages | FrameFlow's one PDF per scene: a crew hands around one document |
| Signing many links (T122; measured 2026-10-19) | one batch request (`signed_urls`): rooftop-tomatoes' 21 frames in 0.22 s, median of 5, from Tumo's machine | one request per link, one after another (before T122): 4.9 s for the same 21, longer than the storyboard page's 2 s poll, which re-signs every accepted frame on each tick; the same requests at once (`asyncio.gather`): 21 requests still, and a burst on every poll of every open tab; caching links: an expiry to track per link, for what one request already fixes |
| A transient Storage error (T070) | `SupabaseStore` retries it: 3 attempts, 1 s then 2 s, on 429, 5xx (520–524 included) or a dropped connection, the LLM client's policy | no retry: one Cloudflare 520 on a `put` lost a frame already drawn and paid for (live run, 2026-10-10); a retry in each caller (the upload, the frames, the comic, T027's PDF): one policy written four times; retrying a 4xx: it answers the same way every time |
| Local development Storage (deploy.md §10) | a dev bucket in the same Supabase project, through the same `SupabaseStore`; tests use an in-memory fake `AssetStore` | a local filesystem adapter: a second code path to keep honest, plus an API route to serve its files to the browser |
| Signed URLs | the bucket is private; the API hands out signed URLs | a public bucket: frames of unreleased scripts readable by anyone with the path (RLS: deploy.md §6, T009) |
| Renderer failure | that frame fails, with its card and "Try another render"; the job fails only when the renderer looks down (§4, T066) | a placeholder frame: AGENTS.md §2a, and a board that looks complete but isn't; stopping the whole job on one passing error (the first live runs) |

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none.

## 9. How this is verified

- **The prompt invariant** (property test over the self-written sample's plan and extraction, every
  shot × every public style): every part with a `span` satisfies §3.1's invariant (its span is this
  heading, the `time_source` heading for `TIME`, or a covered element, and its text is in that
  redacted span); every part without one is from `FRAMING_WORDS`, the count phrases,
  `PLACEMENT_PHRASES` or the style; `text()` contains no name token of any character; no
  `Dialogue.text` appears; `rationale` never appears (a shot built with a sentinel rationale); no
  prompt exceeds `max_words`. The sample includes a `CONTINUOUS` scene after a night scene.
- **T074:** `introduced_age`: `LERATO (10), braids…` → "a 10-year-old", `MOKGOSI (70s)` → "a person in
  their 70s", `NANDI (60s, oilskin coat)` → "a person in their 60s", a character never introduced
  with a number → `None`, `(5 months)` and `(30s-40s)` → `None`, a name inside another word never
  matches, the span is the introducing
  element's; `build_frame_prompt` puts one `AGE` part per visible character with an age right after
  `COUNT`, none for an animal or an off-screen speaker, and counts them in the fixed words;
  `cites_this_shot` accepts two characters introduced in one line (each age with that one span). Live, with
  Tumo's go-ahead (about $0.06): one upload of the-red-kite at `RENDER_MAX_ATTEMPTS=1`, against
  2026-10-10's 3 of 22 accepted on the same seeds.
- **T082:** `title_sex`: `MAMA THEMBI` → female, `MR. DUBE` → male, `OFFICER MOLOI` → None,
  `SIPHO` → None. `character_sex`: one source → its sex; two agreeing → that sex; two disagreeing →
  None; none → None; SIPHOKAZI with the grounded `sex_word` "She" → female with "Siphokazi nods. She
  cannot stop the smile." as evidence; a woman whose introduction says "her" and whose grounded word is
  "fisherman" → None. `AGE` reads "a 17-year-old girl" for Siphokazi, "a woman in her 60s" for Mama
  Thembi; a sexed character with no age gets `SEX` "a female person" / "a male person" (never "a woman": `BABY (5 months)` introduced with "she" is no woman), cited with `sex_quote`'s span or, for a title, the first located quote's; never both `AGE` and `SEX`; every `SEX` part has a span; the invariant
  test (§9) accepts a sex word keyed by `sex_quote` from another element, or by the name, and fails one
  keyed by nothing. Live, Token Factory only (ask
  first): the extraction on all three samples, the sex of every person character against a
  labelled table (eval/), **lost-property held out** (T082 was found on sipho-and-siphokazi and
  designed on its three introductions); never a wrong sex, the misses counted.
- **T079:** `introduced_sex`: `LERATO (10), braids tied back, grips … as tall as she is` → female;
  `MOKGOSI (70s), reading glasses pushed up on his forehead` → male; `MAMA THEMBI (60s), the shop's
  owner, watches her …` → None; `KOOS (70s), the night cleaner, pushes a broom. She waves.` → None. `introduced_look`: "braids tied back",
  "reading glasses pushed up on his forehead", `(60s, oilskin coat)` → "oilskin coat", `AMAHLE (8),
  who is wearing pyjamas … crying.` → None, a 9-word phrase → None. `introduced_age`: "a 10-year-old
  girl", "a man in his 70s", "a person in their 60s" when no sex. `build_frame_prompt`: each visible
  character's `AGE` then `LOOK`; no `LOOK` when the shot covers the introduction; looks dropped from
  the last character back to keep 12 action words, never a `PromptError`; a shot of only an `O.S.` line gets the
  planner's other characters as listeners, and `COUNT` counts them; a shot with an on-screen
  character gets no listener. `cites_this_shot` accepts `LOOK` with exactly `introduced_look`'s text
  and refuses any other text on that span. Live, with Tumo's go-ahead: one upload of the-red-kite.
- **`build_frame_prompt`** cases: the fixed part order, `ACTION` parts in element order;
  `INT`/`EXT`/`INT_EXT` prepositions; a `None` time omitted; a borrowed time citing the earlier
  heading; counts 0 to 5 from `visible_characters` (a planner character not in the covered text, a
  `V.O.` speaker and an `O.S.` speaker not counted; an on-screen speaker and a named actor counted); a
  dialogue-only shot (no `ACTION` part; its parentheticals and speech absent); a
  character introduced in an earlier shot contributing nothing; a placement outside
  `PLACEMENT_PHRASES` raising `ValueError`; the budget dropping `ACTION` parts from the tail, keeping the first,
  then cutting it at a sentence end or word boundary, with `trimmed` counting them; fixed parts over
  budget raising `PromptError`;
  "NANDI'S KITCHEN" in the raw heading → "inside a person's kitchen".
- **Redaction, adversarial**: a two-word name as one "a person"; possessives; `THE STRANGER` and
  `OLD MAN` cues leaving "The" and "Old" alone; a title before a name taken with it ("MR. DUBE",
  "Dr Khumalo", "OFFICER VAN WYK'S") but a title alone, a title at a sentence end ("the OFFICER.
  Moloi turns") and the "MR." of "MR. AND MRS. DUBE" left alone (T050); a lower-case common word equal to a name untouched; a
  named non-speaking person whom the fixture's extraction omits **is** left in the prompt (the
  residual risk, pinned so any change to it is deliberate).
- **`redact_names` / `redact_all`**: characters.md §9's redaction cases, plus `redact_all`, runs and stop words.
- **Labels (T052)**: on `lost-property`'s own lines with a hand-built extraction (MARMALADE with
  species `cat`, a CUE-style second entry `MARMALADE` with none, GIRAFFE with other name `Gerald`):
  "Even Marmalade comes back" → "Even the cat comes back"; "Amahle dances with Gerald" → "a person
  dances with the giraffe"; "Marmalade's tail" → "the cat's tail"; "VIOLIN" untouched; an
  unpaired other name (no shared scene) → `it`, and its possessive → `its`, and "Gerald" paired through scene 11 on the real
  sample's lines; a prop named "NANDI'S UMBRELLA" labelled `it`; a token shared by a
  person and an animal → `a person`; two animals sharing a token → the earlier entity's label;
  `COUNT` ignores the cat and `PLACEMENT` needs two *people*; the §9 invariant and `names_in` hold
  with labels and other names (no prompt contains "Gerald" or "Marmalade").
- **`load_styles`**: the repo's `styles/` loads with exactly one public default; each §3.2 failure
  raises `StyleError` naming the file (a private key shadowing a public one, a private default, a
  subject word in `medium`, weight syntax, a missing field, an unknown field).
- **`render_key` and `fit`** (T026): the key changes with the model, the request, the requested size and
  the post-process, and is stable across dict ordering; `fit` returns exactly the requested size.
  (ComfyUI's workflow tests, T003: cut 2026-10-19; never built.)
- **`FalRenderer`** (T026) with `httpx2.MockTransport` and an in-memory `AssetStore`: the request body
  is §3.5's exactly (no negative, no weights, no escapes; `Authorization: Key …`); `fal_draw_size`
  keeps every size ≤ 1,000,000 px in multiples of 16 (1280 × 720 as is, 1748 × 986 → 1328 × 736) and
  the frame is fitted to exactly the requested size; a store hit makes no fal call; the record is
  written before `render` returns; a 429 then a 200 succeeds after one sleep, three 5xx and a 401
  are `RendererError` naming status and model and never the key or prompt; a returned size other
  than the drawn one is `RendererError`; a flagged image is redrawn with the derived seeds, the
  frame and key carry the seed drawn, and three flags are `RendererError`; the factory exists only
  with `FAL_KEY`. `run_job` with a factory advances RENDERING at 60, writes every frame through
  T021's writer and ends DONE at 100; without one it ends DONE at 60 as before.
- **`ComfyRenderer`** (T003): cut 2026-10-19; never built.
- **`SupabaseStore`** with `MockTransport`: the Storage REST paths, the secret key header, a 409 on `put`
  treated as success, errors raised as `StorageError`, no key in any error message.
  T070, with a recording `sleep`: a 520 then a 200 on `put` succeeds on the second attempt after
  sleeping 1 s; a 520 then a 409 is success; three 503s raise `StorageError` naming 503 and 3
  attempts, having slept 1 s and 2 s; a `ConnectError` then a 200 on `get` returns the bytes; three
  `ConnectError`s raise `StorageError` ("unreachable"), never the httpx2 error; a 400 or a 403 is
  tried once; `exists` and `signed_url` retry the same way; no warning names the key or the path.
- **T122** (`tests/storage/test_t122.py` and `tests/api/test_t122.py`, tests first), with `MockTransport`:
  `signed_urls` sends one `POST /storage/v1/object/sign/{bucket}` with `expiresIn` and the paths,
  and returns the links in the order given, prefixed as `signed_url`'s are; 150 paths make two
  requests (100, then 50), the links still in order; `[]` makes no request; an item with
  `"signedURL": null` raises `StorageError` naming the count, not the path; a 503 then a 200 is
  retried as T070's. `read_frames` with three accepted frames and one withheld makes one batch
  request and gives the withheld frame no link; `read_comic` signs the pages and the PDF in one;
  a `StorageError` from either is 503 `storage_unavailable`. The fake `MemoryStore`
  (`tests/fakes.py`) gains `signed_urls` as a loop over its own `signed_url`, so a subclass that
  overrides `signed_url` (`BrokenStore` in `tests/api/test_read.py`, the `CountingStore`s) keeps
  failing or counting through the batch call too. **Measured first** (2026-10-19, free: signing
  writes nothing; `eval/measurements/t122/`): 21 frames one at a time 4.9 s against one batch
  0.22 s (median of 5 rounds); the batch answer keeps the order and echoes each path, a path asked
  twice is signed twice, a batch link has the single call's form up to `?token=` and opens the
  image (200), a missing object is an item with `"signedURL": null` and an `error`, and an empty
  `paths` is refused with 400 (hence no request for `[]`).
- **`build_storyboard`** with a fake renderer and a mocked audit: one frame per shot in plan order;
  every attempt logged with its asset; `PASSED`, `WARNED` (soft checks noted) and `WITHHELD` (hard
  checks noted, `asset` `None`) frames; a `FAILED` frame among drawn ones leaving the storyboard
  going (every other shot drawn, the job `DONE`); `min(3, shots)` failures before any drawing
  raising `StoryboardError` after the in-flight shots finish, with no new shot started; a plan of
  one or two shots that all fail raising it too; the log adapter passing each attempt's asset; `on_frame` fired for
  every transition with an asset only on PASSED/WARNED; `progress(settled, total)` after each
  terminal frame.
- **Document**: `layout_document` is deterministic; scenes start pages; blocks never overlap the
  header or footer; a long source continues onto the next page with every line present (the joined
  lines equal the `source` modulo wrapping); `render_pdf` makes one PDF page per `StoryboardPage` at
  1240 × 1754; a withheld block draws the card with the checks in enum order and `audit error` for
  an `ERROR`; a failed block draws the failed card for `render` and `restart`; no withheld or failed
  frame's pixels are ever read (its bytes are not passed in). `frames_from_rows` takes each frame's
  audit at its own attempt (not a later or earlier one) and gives `ERROR` with no audit;
  `document_key` changes with any frame field, the style and the version, not with row order;
  `export_pdf` builds and stores once, then answers the stored path without reading a frame.
- **Speakers (T103)**, `tests/storyboard/test_t103.py`: a shot covering an action and a speech
  gives the action's lines, then a speaker line (`speaker=True`) with the cue, then the speech's lines
  (`of` the label); a cue with an extension prints `CUE (V.O.)`; a parenthetical is not printed; two
  speeches of one cue in a row print the cue once, and with an action between them twice (the web's
  `sourceBlocks` rule); a speech whose text holds a `\n` keeps it as a line break; a cue too wide for
  the line wraps to a speaker run in the Bold font; the non-speaker lines joined (modulo wrapping)
  equal the shot's `source`; a heading-only shot (no elements) and a shot whose `source` differs from
  its elements print `source`'s lines with no speaker; a block that continues where the fitting lines
  end on a speaker run moves the run to the next page, keeps a run that is all that fits, and repeats
  the speaker above a speech cut across pages; `render_pdf` draws a speaker line Bold (a spy on
  the font counts one Bold 22 px per speaker line and page header); `DOCUMENT_VERSION` is 3 and `document_key` differs between 2
  and 3. The two tests that set a long `source` on the sample's shot (a continuation with every line;
  element breaks kept, never cut or folded) give that shot no elements, so they test the fallback
  as before, comparing the lines' `text`. The PDF of a stored run, exported locally and looked at.
- **Live** (T026/T027; needs `FAL_KEY`, T021): an upload of the self-written sample on the local stack, in the default
  public style: every shot ends `PASSED`, `WARNED` or `WITHHELD`; the PDF and frames are in Storage;
  seconds per frame, renders per frame and fal's cost are recorded in deploy.md §9 and verify.md (the hosted run of 2026-10-16: 339,000 tokens, 44
  drawings); the pages were not committed as a visual reference (§2).
- **T092** (`tests/characters/test_t092.py`, tests first): particles: "Mr. Van der Merwe climbs
  down" → "a person climbs down", "MR. VAN DER MERWE (50s)" → "a person (50s)", "Jan van der Merwe"
  (two particles) → "a person"; with `LE ROUX`, "the house of le Roux" → "the house of le a person";
  a particle after a `.` or `,` ("Thabo. de Wet"), at the end of the text, or that is no token of
  the call's names stays; `redact_names` labels a run with a particle as the character's own.
  `named_as_figure`: Title case ("Lindi", "Officer Van Wyk", "McDONALD") true; an introduction
  ("AYANDA (17)", "AYANDA(17)") true, but not with a newline before the `(`; "Mr. DUBE winds his
  watch" false and "Mr. Dube winds his watch" true (a title is not the run); possessives false
  ("Jabu's paper", "NANDI'S", "Jabu’s" with a curly apostrophe, the plural "The Lionesses'
  goalkeeper"), `O'BRIEN` not possessive; "LIONESSES 1 - EAGLES 1" false; "Jabu's paper. Jabu
  covers it" true. `_name_runs` gives the runs `_redact` replaces on every existing redaction
  fixture. Every existing redaction test unchanged.
- **T093** (`tests/storyboard/test_t093.py`, tests first): `pronoun_sentences` splits at `. ! ?`
  but not after `Mr.` ("Mr. Dube nods. She waves." is two pieces), joined by one space gives the
  text back, and marks only an exact opening `He`/`She` ("Hesitant, she…", "Then he…", "They…",
  `"He…` give None; `"Go." He nods.` is one piece); it reads the redacted text (a name redacted at a
  sentence's start leaves no He). Rule 1: a shot covering only "He looks at the ball. He puts it in
  his pocket." with cast `[MR. VAN DER MERWE]` (male by title) draws him: COUNT "one figure", his
  AGE and LOOK, which pass `cites_this_shot`; a second male cast person, one of unknown sex, mixed
  He and She pieces, an animal as the only cast, or the only male being the shot's off-screen
  speaker: no one drawn; a Listeners shot (T079) that returns people is unchanged, and rule 2 then
  reads those listeners. Rule 2: a She piece with only a male figure drawn is left out and the
  element's other pieces stay as separate ACTION parts in element and sentence order, each passing
  `cites_this_shot`; with He and She pieces and a man drawn, only the She piece goes; a She piece
  with a figure of unknown sex stays; an element whose every piece is left out gives no ACTION
  part and `trimmed` is unchanged, and so does a shot where every element goes; on a split element
  over budget, a tail run is dropped and the first run cut at a sentence end, `trimmed` counting
  each. The audit's `on_screen` and `report.py`'s rebuilt prompt agree with `build_frame_prompt`
  (the pronoun figure included). Every existing prompt test and the invariant test unchanged. Free:
  the §3.1 numbers re-measured by the real code on the stored plans with T092 built.

- **T100** (`tests/storyboard/test_t100.py`): "NALEDI (12), dungarees, scraped knees, stares at
  it. Her little brother TSHEPO (8) …" → NALEDI female; "SAM (40) sits down. His hands shake." →
  male, and the same with `!` or `?` ending the first sentence, or `…` between them; "SAM (40) sits
  down. Her hands shake." → female; "A girl, SAM (12), sits down. His hands shake." → None (one-sex
  rule: the appositive's girl and His); "SAM (40) waits as he sits down. Her hands shake." → male
  (the he is a possible owner, so the next sentence isn't read); None for each of: "MAMA (60s) hugs SIPHO. His …" (another name), "NANDI (60s)
  waves to THABO (9). His …" (a next introduction), "SAM (40) kisses the woman. Her eyes close."
  (a sex noun), "NALEDI (12) hands the man a coin. His hand shakes." (a sex noun), "SAM (40) holds
  the baby. His …" (a person noun), "SAM (40) greets Dr. Dube. His …" (another name after "Dr.",
  which doesn't end the sentence), "SAM (40) sits. Rain falls. His …" (not the next sentence),
  "SAM (40) sits. Her to …", "SAM (40) sits. Her." and "SAM (40) sits. Her, then silence." (not a
  possessive), "SAM (40) greets Émilie. His …" (an accented name), "NALEDI (12) hands the clerk a coin.
  His …" and "SAM (40) pats a dog. Her …" (an article), "SAM (40) sits. HER …"
  and "… sits. his …" (not capitalised as a sentence opens), "SAM (40) sits." as the element's last
  sentence (no next sentence, no error), and "SAM (40) sits." then a line of dialogue, then an Action
  "His …" (another element). TSHEPO, introduced in the `Her` sentence, is male from his own look
  ("shorts down past his knees") and the `Her` before his name is not read for him. NALEDI's prompt
  reads "a 12-year-old girl" and passes `cites_this_shot`; the invariant test is unchanged and
  passes. `NOT_POSSESSED` is importable from `app.grounding` and `_owned` behaves as before. Free:
  the labelled read scripts give §3.1's 1 candidate, 1 right, 0 wrong.

- **T096** (`tests/storyboard/test_t096.py`): "A boy in a too-big school blazer, THABO (9),
  stands." → male; "A small boy, KAMO (7)" → male; "A small girl, AMA (7)" → female; "An old woman,
  NANDI (60s)" → female; after another sentence ("Six learners wait. A tall girl, ZOLA (17)") →
  female; "The boy, THABO (9)", four words before the noun, more than six after it, a second sex noun
  ("A woman hands the boy a letter, THABO (9)", "A man helps a girl, AMA (7)"), a phrase about
  someone else ("A woman and her child, ZANELE (6)", "A man holding a baby, NOMSA (1)", "A man
  hands the driver a note, SIPHO (30s)", "A woman with a baby, LUMKA (1)", "A boy's teacher,
  SAM (40)" with either apostrophe), two appositives in
  one sentence, a noun after the name, and a noun and a pronoun that disagree give None ("A man
  wearing a cap, SIPHO (30s)" → male, "A girl with braids, AMA (7)" → female); THABO's
  prompt reads "a 9-year-old boy" and passes `cites_this_shot`; the invariant test's `keyed` takes the
  appositive noun.

## 10. Open questions

- [x] **Which styles stay private?** (STATUS.md § Open decisions, SPEC.md open question 3.) **Decided
  2026-09-30 by the user:** all three of FrameFlow's drawn styles (`clean`, `ink`, `pencil`) are
  public in `styles/`, `clean` is the default, `classic` is dropped (§8), and the private pack is
  empty. Built by T008.
- [ ] **A longer word budget for FLUX** (§3.5): FLUX's text encoder reads far more than CLIP's 77
  tokens, so `COMFYUI_MAX_WORDS` (55) could rise and fewer script words would be cut. Decide with
  real fal renders in hand; it changes T008's budget and its tests.
- [x] **The ComfyUI model and graph, GPU cost, how ComfyUI is exposed** (T003): moot. T003 was cut
  2026-10-19 (no money for a GPU VM); fal.ai is the only renderer, and T030 set
  `IMAGE_MONTHLY_GENERATION_CAP` to 800.
- [x] **Unaudited frames at the US1 checkpoint** (SPEC.md open question 1): resolved; T026 renders
  through T021's loop, so no frame is shown without `PASS` or `WARN`.
- [x] **Dialogue-only shots before T025**: moot; T025 was cut 2026-10-19 (and T049 closed 2026-10-12).
  Such a shot is drawn from its setting, time, figure count and its speakers' `AGE`/`SEX`/`LOOK` (T074,
  T079).
- [ ] **Off-screen speakers and `MISSING_CHARACTER`** (§8): every shot with a `V.O.`/`O.S.` speaker
  will end `WARNED`. Accepted here; if the notes are noise, verify.md could skip characters whose
  only covered speech is off-screen (a verify.md change, its own PR).
- [ ] **Scripts outside Latin-1-plus**: Courier Prime covers Latin scripts; a script in another writing
  system would print missing-glyph boxes. Out of scope until a sample needs it.
