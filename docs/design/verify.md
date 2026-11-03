# Design — `verify` (the frame audit and re-render loop)

**Status:** agreed · **Owner:** Katlego (Claude) · **Tasks:** T020 (audit), T021 (re-render loop, audit
log: the API), T061 (the log and the retry in the web app), T062 (the architecture check), T077 (a signature warns), T078 (a prop's parts; no drawing marks), T080 (sex and look; no one in frame), T082 (the judge is told each person's sex), T083 (things the scene names; background objects warn; `recheck`), T084 (a person's support is an action line), T086 (a matched person's age; a vehicle's parts inside it; unheld food warns), T089 (objects, but animals and weapons, and lettering warn), T094 (the rule ladder), T095 (the sex agent), T097 (the head agent: where each person's head is, for the comic's bubbles), T099 (the presence agent), T106 (a rooftop is exterior), T107 (a signature's letters aren't text), T102 (a found person's sex), T104 (the layout agent), T109 (the describer's answer capped), T124 (described alike) · **Spec:** [SPEC.md](../../SPEC.md) US2 (frame audit)

---

## 1. What this covers

Checking every rendered frame against its shot before anyone sees it, re-rendering it when it
fails, and logging every verdict. This is where Non-negotiable I is enforced **on pixels**: a frame
that shows a person, prop or event the script doesn't put in that shot is never shown. Up to T026,
grounding is enforced on text; this is the first check on images.

**Not covered:** rendering (T026 provides the renderer this calls: storyboard.md), comic layout (comic.md reads
the audit's speaker positions), portraits (characters.md; T025 cut 2026-10-19).

## 2. Reference material

| Kind | Where |
| --- | --- |
| The vision decision | docs/nebius-findings.md § The vision decision: **option A**: no Nemotron model on Token Factory accepts images (U7), so a vision model (`NEBIUS_MODEL_VISION`) *describes* the frame and Nemotron *judges* it. **Since 2026-10-17 that model is NVIDIA's: Nemotron 3.5 Super VL, thinking off** (T105, [vision-model.md](vision-model.md), findings § U8); DeepSeek-V4.1-Flash from 2026-09-30, GLM-5.3-Flash before (findings § U7 re-check). Option B's self-hosted GPU is no longer needed |
| Prior art in FrameFlow | **none**: FrameFlow had no image audit, no verdicts and no automatic re-render; "regenerate" was a user button with a random seed |
| Inputs | `Shot` (shots.md §6: framing, characters, props, time_of_day, source, span); `Entity` quotes (grounding.md §6); `Scene.int_ext`, `location` (script.md §6); the rendered frame (T026) |
| LLM seam | `structured_chat`, `Tier.VISION` and `Tier.REASONING` (llm.md §6). Image content parts are OpenAI-style (`image_url` data URLs), as probed in U7 |
| Expected renders | `E[N] = (1 − (1−p)^(k+1)) / p` for pass rate `p` and `k` re-renders (docs/submission/about.md) |

## 3. Domain model

```mermaid
classDiagram
    class FrameDescription {
        +list~SeenPerson~ people
        +Setting setting
        +Light light
        +ShotSize shot_size
        +list~SeenObject~ objects
        +bool has_text
        +list~str~ text
        +bool signature
    }
    class SeenObject {
        +str name
        +ObjectCategory category
        +bool held
    }
    class SeenPerson {
        +Position position
        +str appearance
    }
    class Judgement {
        +list~PersonCall~ people
        +list~ObjectCall~ objects
    }
    class PersonCall {
        +int person
        +str|None character
        +str|None support
    }
    class ObjectCall {
        +int object
        +ObjectKind kind
        +str|None support
    }
    class CheckResult {
        +Check check
        +Severity severity
        +bool ok
        +str detail
    }
    class Audit {
        +tuple~int,int~ shot
        +int attempt
        +int seed
        +FrameDescription description
        +Judgement judgement
        +tuple~CheckResult~ checks
        +Verdict verdict
        +dict~str,Position~ positions
        +tuple~str~ models
        +Usage usage
    }
    class FrameOutcome {
        +tuple~int,int~ shot
        +FrameState state
        +RenderedFrame|None frame
        +tuple~Audit~ audits
    }
    FrameDescription --> SeenPerson
    FrameDescription --> SeenObject
    Judgement --> PersonCall
    Judgement --> ObjectCall
    Audit --> FrameDescription
    Audit --> Judgement
    Audit --> CheckResult
    FrameOutcome --> Audit
```

- **The describer is blind to the shot.** It gets the image and a neutral instruction: count the
  people, where each one stands, what they look like in a short phrase, interior or exterior, the
  light, the shot size, the notable objects (each with a category from a fixed list and whether
  someone holds it), and whether any text or letters appear. It is never told
  what it *should* see, so it can't simply agree.
- **What the describer leaves out and writes down (T071).** It doesn't list what a person wears
  (that goes in the person's `appearance`) or the place's own structure (walls, floor, ceiling,
  sky, windows, doors, roofs, chimneys, stairs) as objects, nor (T078) marks of the drawing
  itself: shading, hatching, outlines, sketch lines, shadows, the frame's border (it listed
  "pencil shading" as an object, which failed a good frame). Under `text` it writes, word for
  word, each piece of writing it can actually **read**; a scribble, an unreadable signature or a
  mark that isn't letters is left out of `text` (it may still set `has_text`). **T107:** the
  artist's signature or initials are left out of `text` **even when it can read them**: they go
  only under `signature`. `text` is the scene's lettering (signs, labels, screens, paper,
  clothing, a drawn sound effect), the writing a script could have asked for. Super VL reads the
  scrawled corner signatures that DeepSeek left out ("J. Eubred", "Muller", "M. P. P. 2020"), so
  on the-red-kite's 44 stored attempts its `text` entries rose 9 → 25 and the soft `TEXT_IN_FRAME`
  6 → 22 (findings § U8), each one a signature reported as unscripted lettering. **The wording
  alone didn't move it** (measured on #210, 2026-10-18: 24 entries, 21 frames), so **the
  signature gets its own slot:** `FrameDescription` gains `signature_text` (the letters of the
  artist's signature or initials, when readable), and `signature` and `signature_text` come
  **before** `has_text` and `text`. The schema's field order is the order the model writes in,
  and it wrote `text` first, which put a legible signature there before it had thought of it as a
  signature. `text`'s own field description becomes "the scene's lettering, word for word: signs,
  labels, screens, paper, clothing, sound effects; never the artist's signature or initials".
  `TEXT_IN_FRAME` reads `text` only, as before, so a signature's letters are no lettering.
  `signature_text` is required in the schema the model is given and defaults to `[]` when a
  stored description (before T107) is read back. T109's limits cap it at **5 entries of 60
  characters** (Katlego, 2026-10-19, #212): a signature is a name or initials, never a paragraph, and
  the smaller cap keeps more of the 4,096 tokens for the rest of the answer.
- **Interior or exterior (T106).** `exterior` when the place is open to the sky (a rooftop, a
  balcony, a yard, a street), even when the sky is left as blank paper; `interior` only when walls
  and a ceiling close it in; `unclear` when the drawing doesn't show which. Super VL called
  the-red-kite's flat roof `interior` on both of its attempts (comic and storyboard 0.4): a
  parapet, a white sky, and in one some beams. That's a hard `SETTING` fail on a right frame.
  DeepSeek said `unclear` there, which passes.
- **The instruction's wording for both (T106, T107), verbatim in `DESCRIBE_PROMPT`:**
  - the setting: "Say whether the scene is interior or exterior: exterior when the place is
    open to the sky (a rooftop, a balcony, a yard, a street), even if the sky is left blank;
    interior only when walls and a ceiling close it in; unclear when you can't tell." It replaces
    "Say whether the scene is interior or exterior, and", and the light follows as its own
    sentence ("Give its light: …").
  - the text: "Under text, write out word for word each piece of writing you can read in the
    scene, as it is written: signs, labels, screens, paper, clothing, sound effects. Leave out
    scribbles, marks that aren't letters, and the artist's signature or initials even when you
    can read them: those go under signature, not text." It replaces the two sentences from "Under
    text" to "letters.".
- **Ages and signatures (T072).** Each person's `appearance` starts with how old they look
  (`a child`, `a teenager`, `an adult`, `an old man`, `an old woman`). `signature` is true when
  the image carries a signature, initials or an artist's mark, readable or not: the live run's
  frames had one in a corner again and again (eval.md §6a.2: 15 of 27), and it is writing
  no script asked for. **T077:** it is the soft `SIGNATURE` check, not a hard fail: an
  artist's mark is no character, prop, line or event, so it can't break the non-negotiable,
  and failing on it withheld frames that were otherwise right (below, §8).
- **What the judge is told (T072).** A described person whose apparent age plainly contradicts
  a character's quoted age (an adult for `LERATO (10)`, a young man for `MOKGOSI (70s)`) is not
  that character: `character` null, so with no support they are `UNSCRIPTED_PERSON`. **T080:** the
  same for a plainly contradicted sex or look: a boy for a character the quotes call "she", short
  hair for one they give braids (on 2026-10-11 klein drew Lerato, `LERATO (10), braids tied back …
  as tall as she is`, as a short-haired boy, and the judge matched him to her 9 times). Only what
  the quotes say counts; a look they don't mention is no contradiction. And **code**
  refuses as support for such a person any quote that names a shot character (`LERATO (10),
  braids…` is about Lerato, so it can't put a stranger there). An ordinary
  thing the heading's place would hold (a workshop's clock, boxes and tools; a roof's bucket,
  pipes and vents; the sky, clouds and puddles outdoors) is `set_dressing`, its support the
  heading's words for the place, which code still checks. Weather that happens (lightning, rain,
  snow, a storm) is an event: `scripted_prop` only with a verbatim quote, else `unscripted`.
  **Code** refuses `set_dressing` for an object whose name is, or is a word of, a prop the
  extraction names anywhere in the script (a `kite` against `RED KITE`): a thing the script
  names is a story choice, so it needs a `scripted_prop` quote, and a second kite stays
  unscripted.
- **A part of a prop (T078).** The judge calls a `kite string` unscripted when the shot has the
  `RED KITE` (3 of eval.md §6a's 7 good frames failed so). **Code** (`part_of_prop`) treats an
  object as a part of a prop of **this shot** that the extraction quotes when its name, in lower
  case, has that prop's head noun (the last word of the prop's name) as its **second-to-last
  word**, has no copy word (`second`, `another`, `other`, `extra`, `spare`, `two`, `three`,
  `more`, `duplicate`), and its category is not one that is never set dressing (`animal`,
  `vehicle`, `weapon`, `food`): `kite string` and `kite tail` are parts of `RED KITE`; `kite`,
  `blue kite` and `second kite` end in the head noun, so they are the prop or a copy of it and
  are judged as before; `map of the town`, `box of matches` and `kite tail string` don't have
  the head noun next to last, so they are judged as before; `spool of wire` holds no `string`.
  A part passes whatever the judge called it, held or not: its support is the prop's own
  quote, already in the shot's supports. **Accepted residue:** a compound where the prop's noun
  only modifies (`coat hanger` with the `oilskin coat` in the shot, `kite shop`) reads as a part;
  no rule on words tells them apart, and it needs that very prop in the shot.
- **Each person's sex in the spec (T082).** `render_spec(shot, scene, screenplay, extraction,
  description)` (it gains `screenplay`; `audit_frame` passes it) gives, under each person character
  `character_sex` sexes, the line `sex (from the script): <female|male>, "<evidence>"` (storyboard.md
  §6: the evidence is the quote, the introduction or the name, 160 characters at most). It imports
  `app.storyboard.prompt` inside the function, as `audit_frame` does (the import cycle). The judge
  prompt gains: "A character's 'sex (from the script)' line, when there is one, is the script's own
  word for their sex: a person drawn as the other sex is not that character." Before T082 the judge
  saw only the extracted quotes, so it matched a boy to Siphokazi (L002, L009).
- **Things the scene names (T083).** An animal, vehicle, weapon or food is never set dressing: the
  script must put it there. On 2026-10-11 the judge called the boats of sipho-and-siphokazi's
  harbour (shot 1.1: "a single row of forty-year-old wooden fishing-boats") set dressing, and
  `vehicle · never set dressing` failed 31 times. **Code** (`named_in_scene`) now asks the
  script directly. Only for those four categories, an object is scripted when one of its
  candidate words is a word of **this scene's action text**:
  - **The scene's action text:** the text of every `Action` element of the scene, lower case,
    split on anything but letters ("fishing-boats" gives "fishing" and "boats"). Not the
    heading, not dialogue: a boat that is only talked about is not on screen.
  - **The candidates:** the object's name in lower case, split on spaces only (so `off-road`
    stays one word, and doesn't match "road"), each word stripped of `.,;:!?'"()`. The
    candidate is the **last word**, the thing's own noun; but when the name has two words or more
    and its last word is a part word, the candidate is **only the second-to-last word**, the thing
    the part belongs to (a `car door` is named by a car, never by the scene's doors). Part words (`mast`, `sail`, `hull`, `deck`, `cabin`, `bow`,
    `stern`, `oar`, `wheel`, `door`, `window`, `windscreen`, `bonnet`, `boot`, `bumper`, `tyre`,
    `tire`, `engine`, `roof`, `seat`, `mirror`, `light`, `tail`, `wing`, `fin`, `head`, `leg`,
    `paw`, `hoof`, `horn`, `mane`, `ear`, `collar`, `lead`, `handle`, `blade`, `barrel`,
    `trigger`, `hilt`, `sheath`, `crust`, `rind`, `peel`, `skin`, `bone`, `slice`, in singular
    or plural): `boat masts` is a part of a boat; `police car` is not a police officer; a
    single `wheel` is its own noun. A
    candidate has at least 3 letters and is no function word (`of`, `the`, `and`, `with`, `in`,
    `on`, `a`, `an`, `for`, `from`, `to`, `at`, `by`, `into`, `onto`, `over`, `under`, `its`,
    `his`, `her`, `their`). A copy word in the **name** (T078's list) means no match.
  - **Singular and plural:** a candidate matches when the scene has any of its forms: the word;
    it plus `s`; it plus `es` only after `s`, `x`, `z`, `ch` or `sh` (`boxes`, `buses`); a `-y`
    word with `-ies`; and, for a plural, its singular: `-ies` → `-y`; `-es` dropped only when what
    is left ends in `s`, `x`, `z`, `ch` or `sh`; any other `-s` dropped, but not from `-ss`. So
    `horse` meets "horses", `boats` meets "boat", `pony` meets "ponies", `box` meets "boxes", and
    no form is a stray word: `bees` never meets "be", `car` never meets "cares" (the code review:
    both would have excused an unscripted thing). Irregular plurals (`wolves`, `geese`) don't
    match: accepted residue, they stay judged.
  - **Accepted residue:** a food named after an animal (`hot dog` in a scene with a dog) reads as
    the dog, as `coat hanger` does for T078, and a verb spelled like the noun ("Gulls wheel"
    names a `wheel`); no rule on words tells them apart, and both need the word in the scene.
  - Measured on every stored audit: the same idea over **all** categories excused "small pills"
    (on "small"), "power lines" (the script's *washing* lines) and "tripod stand" (a verb), each
    an unscripted thing; the four categories (with the last and the second-to-last word, before the part-word
    limit) excused 11 of the 2026-10-11 sipho-and-siphokazi objects shot by shot, and 32 scene by
    scene, all of them the script's
    boats, fish, the bakkie's wheel and its truck.
- **Background objects warn (T083; Tumo, 2026-10-11).** An everyday thing the script never
  mentions and nobody holds (a pen on a counter, grass, the moon) withheld a frame as an invented
  person does. Now it is the soft `BACKGROUND_OBJECT` check: logged, named on the card (web.md
  §4.3 shows a warned frame's soft checks with their details), the frame `WARN`, and shown, on
  the storyboard and in the comic alike (the same audit). Exactly: an object of category `other`,
  `nature`, `furniture` or `screen_or_sign`, **not held**, whose name is **not** a word of a prop
  the extraction names (`_named_prop`), called `unscripted`, or called `set_dressing` with a
  `support` not found in the heading. Its detail is `object N (name, category): not in the
  script`. **Everything else stays hard:** any person; a held object; an animal, vehicle, weapon
  or (until T086, which makes unheld food warn) food the scene doesn't name; a `scripted_prop` without a verified support, whatever its
  category (the judge claimed a quote it can't show); a named prop called `unscripted` or
  dressing (T072); and legible text (`TEXT_IN_FRAME` still reads a sign's words). **Since T089**
  all of these but an animal or a weapon (and any person) warn too: §3, Objects and lettering
  warn. Measured free
  on the 2026-10-11 storyboards' stored audits (`recheck`, with the scene-named rule too):
  sipho-and-siphokazi 7 → 12 of 30 shots with an accepted attempt, the-red-kite 16 → 19 of 21.
  **Looked at:** 2 of the 9 attempts it newly accepts draw Siphokazi with the wrong sex (L009):
  the object checks were catching them by accident, so T083 goes live after T082.
- **The order in `run_checks` (T083)**, for each judged object: costume and structure that nobody
  holds pass (T071, `_NEVER_UNSCRIPTED`); then a part of a shot prop passes (T078,
  `part_of_prop`); then a thing the scene names passes (T083, `named_in_scene`), held or not and
  whatever the judge called it (a held sword the scene names is the script's sword); then the
  judge's call: `unscripted` → `BACKGROUND_OBJECT` when the rule above holds, else
  `UNSCRIPTED_OBJECT` "unscripted"; `scripted_prop` without support → `UNSCRIPTED_OBJECT`;
  `set_dressing` held → hard; named prop → hard; one of the four categories → hard "never set
  dressing"; support not in the heading → `BACKGROUND_OBJECT` when the rule holds, else hard
  "not in the heading". **T086:** right after `named_in_scene`, a part of the vehicle the scene is
  inside passes (`part_of_vehicle`); and before the judge's call, unheld food that no rule above
  passed and that is no named prop is `background`, so `set_dressing` → `BACKGROUND_OBJECT` (even
  with the heading as support) and `unscripted` → `BACKGROUND_OBJECT`; a `scripted_prop` food with a
  verified support still passes, without one it stays hard; held food stays hard. For each judged
  **person**, the age test (T086) comes first: a contradicted match is refused as that character
  and is never then tried as a stranger (no support can excuse it); then T072/T084 as before.
  **T089:** the cases and their order, and the `background` and `food` variables, are unchanged;
  every place above that files `UNSCRIPTED_OBJECT` ("hard") files `_filed(obj.category)`
  instead: `UNSCRIPTED_OBJECT` for an animal or a weapon, else `BACKGROUND_OBJECT`, the detail
  the same (§6).
- **A person's support is an action line (T084).** A described person the judge matches to no
  character is scripted only by a verbatim `support`. On 2026-10-12 lost-property (L011) showed
  three accepted frames whose strangers were excused by what someone **says** ("Somebody might
  have.", "Sorry, my friend. He's already got a home.") or by a sentence whose only person is a
  pronoun for a character ("A pigeon glares at him.", "him" is Koos). A line of dialogue puts no
  one on screen, as `named_in_scene` already holds for things. **Code** now asks two more things
  of a person's support, after T072's (it names no shot character):
  - **It is found in the shot's action text** (`shot_action_text`: the text of the shot's covered
    `Action` elements, in order, joined by a space and normalised as `_found` does), not in its
    dialogue or parentheticals, and no longer in an entity quote from elsewhere in the script.
    Detail: `person N (position, appearance): its support is not an action line`. **Only this
    shot's action, on purpose** (unlike T083's scene-wide words for things): a stranger the
    script introduced in an earlier shot and still on screen in a shot of dialogue alone now
    fails. Accepted: the stored runs have no such case, and a person who stays is usually a
    character the judge can match.
  - **It has no `he`, `him` or `she`**: the words of the support, lower case, split on anything
    but letters (`re.findall(r"[a-z]+", support.lower())`, so "he's" gives "he"), against
    `_PERSON_PRONOUNS`. Such a word points back at someone the script has already introduced, a
    character, so it can't introduce a stranger. Possessives and reflexives (`his`, `her`,
    `hers`, `himself`, `herself`) are **not** in the set: they usually belong to the sentence's
    own subject ("A WOMAN, 40s, folds her umbrella" introduces her); with them or without, the
    stored runs give the same result. Plural `they`/`them` stay allowed: a crowd is introduced
    as "Passengers hurry" and then "they". Detail: `person N (position, appearance): its support
    points at someone else`. **Accepted residue:** a stranger introduced in a sentence that also
    points at a character ("A WOMAN hands him a cup"), quoted whole, fails; the judge isn't told to
    quote only the stranger's part (§10).
  - **The order, for a person matched to no character**, first failure wins: support not found
    in the shot's text or its in-shot entities' quotes → "no shot character, no support" (as
    before); names a shot character → "its support is about a character" (T072); not in the
    shot's action text → "its support is not an action line"; has `he`, `him` or `she` → "its
    support points at someone else".
  - Measured free (`recheck` with a prototype, every stored audit): lost-property 12 → 9 shots
    with an accepted attempt (7.4, 10.2, 10.3, the three of L011). **Not designed on:** the
    2026-10-11 sipho-and-siphokazi 12 → 11 (6.1, a man excused by Sipho's introduction from
    another shot; 9.3, an old woman excused by "He takes the tide book from her", where "her" is
    Siphokazi, 17), the-red-kite runs 35 → 33, 16 → 15 and 10 → 9 (a "teenager" excused by "my
    girl", a child by "Is that my good shirt you are flying?", "an adult man" by "He switches off
    the soldering iron." for Mokgosi, 70s), every other stored project unchanged. Each newly
    failed attempt was read: every one excuses a person with a spoken line, someone else's pronoun
    or a quote from another shot.
- **A matched person's age (T086).** The judge is told (T072) that a person whose age plainly
  contradicts a character's is not that character, but nothing checked it. On 2026-10-12 the-bread-van
  (L012) matched THEO (9) to an adult in 17 of 24 matches, and DANIEL (40s) to "an old man". **Code**
  now compares: `described_age` reads the describer's own words (the earliest of child, teenager, old,
  adult: "an old man looking toward the girl" is old; parents and grandparents are adult and old, so "a
  mother holding a child" is adult; "older" is no age word, DANIEL (40s) drawn as "an older man" is
  not refused), and `age_contradicts(years, described)` with the
  introduction's age in years (`introduced_years`, storyboard.md §6): under 13 not an adult or old; 13 to
  19 not old; 20 to 49 not a child or old; 50 and over not a child or a teenager. No described age, or
  no introduced age, is no check. A contradicted match is `UNSCRIPTED_PERSON` `person N (position,
  appearance): described as <age>, but <NAME> is introduced at <years>`, and the character is not
  placed (so `NO_CHARACTER` and `MISSING_CHARACTER` see them absent). `run_checks` gains `ages`, each
  shot character's introduced years (`shot_ages`), passed by `audit_frame` and `recheck`. It only
  tightens: it can't make the judge match the right person, only refuse a wrong match.
- **Inside a vehicle, its parts are the place (T086).** On 2026-10-12 the-bread-van's INT. VAN - MOVING
  failed a rearview mirror, a dashboard, headrests and car seats as vehicles never set dressing, and a
  driver's held steering wheel as held (L013). **Code**: when the scene is not `EXT` and its location's
  head noun (the last word of the location's first part, before any " - ") is a vehicle, so INT. VAN -
  MOVING and SIPHO'S BAKKIE are inside one and BUS STATION, CAR PARK and TAXI RANK are not
  (`_VEHICLE_PLACES`: van, car, bus, minibus, kombi, taxi, cab, truck, lorry,
  bakkie, jeep, ambulance, train, carriage, tram, coach, boat, ship, ferry, plane, aeroplane, airplane,
  helicopter), an object, not an animal, weapon or food, whose last word is a vehicle part word
  (`_VEHICLE_PART_WORDS`: wheel, door, window, windscreen, bonnet, boot, bumper, tyre, tire, engine,
  roof, seat, mirror, light; T083's list less its animal, weapon and food parts, so a held "pistol
  barrel" or a "dog collar" in a van is judged as before) or an interior word
  (`_INTERIOR_WORDS`: dashboard, steering, headrest, seatbelt, gearstick, gear, speedometer, windshield,
  visor, glovebox, upholstery), or that has an interior word, is the place's own structure
  (`part_of_vehicle`), held or not, whatever the judge called it; never with a copy word. A bare vehicle
  (a sailboat through the window, a second van) is judged as before: the prototype that let any
  `vehicle` object pass accepted a sailboat in a boat's cabin. In `run_checks`, right after
  `named_in_scene`.
- **Unheld food warns (T086; Tumo, 2026-10-12).** Bread in the bakery failed 26 times on the-bread-van
  (`food · never set dressing`). Food nobody holds that the scene doesn't name and that is no named
  prop is now `BACKGROUND_OBJECT` (soft, `WARN`), whatever the judge called it, `unscripted` or
  `set_dressing`, even with the heading as support: food is never quietly the place's, it is shown with
  a warning. Held food (someone eating what the script never gave them) and a `scripted_prop` without
  support stay hard. Animals, vehicles and weapons stay never set dressing. (Since T089 held food,
  an unsupported prop and a vehicle warn too; only an animal or a weapon stays hard.)
- **Measured free** (every stored audit, main's `run_checks` against T086's): the-bread-van 1 → 2 shots
  with an accepted attempt, sipho-and-siphokazi (2026-10-11) 11 → 14 and its older run 10 → 11, the-red-
  kite `fbe668c8` 9 → 7 (two adults matched to LERATO, 10, now refused), every other project unchanged.
  **Looked at, every newly accepted drawing (9):** 5 right (the-bread-van 5.1 twice, Nomsa and Theo;
  the-red-kite 5.1 three times, Mokgosi and Lerato in braids); **4 wrong**: sipho-and-siphokazi 2.3, 3.2
  and 3.3 draw Siphokazi (17) as a boy, the older run's 3.3 draws Sipho (50s) young. The object
  checks were catching them by accident (L009 again): those audits are from before T082, and Siphokazi
  has no sex the judge could check (L010). **So T086 goes live after T088** (TASKS: the extraction model
  resolves a "his"/"her" to its character, code checks the quote; L010), as T083 went after T082.
- **Objects and lettering warn (T089; Tumo, 2026-10-12).** Measured free on five runs' stored audits
  with today's code (L014): the shots with an accepted attempt go the-bread-van 3 → 9 of 20 (and its
  first run 2 → 5 of 19), lost-property 9 → 33 of 49, sipho-and-siphokazi 14 → 26 of 30, the-red-kite
  19 → 20 of 21 when an object or a painted word the script didn't put there warns instead of
  failing. klein can't spell (LOST PROPERTY is painted LOST POVERTY, LOST PORRY) and fills a place with
  bags, pens, plates and cars; each one withheld the frame. Now:
  - **An object** that would fail `UNSCRIPTED_OBJECT` (any reason: `unscripted`, `prop without
    support`, `held, so not set dressing`, `the script names it`, `never set dressing`, `not in the
    heading`) fails the soft `BACKGROUND_OBJECT` instead, with the same detail, **unless its category
    is `animal` or `weapon`** (`_STORY_OBJECTS`): a dog or a knife the script never gave the scene is
    a story choice, and stays hard. Keeping those two hard costs nothing measured (the same shots on
    all five runs: a baton, a knife and a bird).
  - **`TEXT_IN_FRAME` is soft.** A painted word the script didn't write is named on the card and the
    frame shown with a warning. It is lettering, never a line someone says: speech bubbles come only
    from the script's dialogue (comic.md).
  - **Everything else stays hard:** every person (`UNSCRIPTED_PERSON`, the age check, `NO_CHARACTER`),
    `SETTING`, and an animal or weapon. In `run_checks` the object cases are unchanged; only where a
    failure is filed changes: `UNSCRIPTED_OBJECT` when `obj.category in _STORY_OBJECTS`, else
    `BACKGROUND_OBJECT`, the detail the same.
  - **Rule I, as the audit reads it now (PLAN.md Non-negotiable I; Tumo's call, 2026-10-12, "go a bit
    easy on the refusals"):** a person, an animal or a weapon the script didn't write never reaches
    the board; an everyday object, a misspelt sign, and **weather drawn as an object** (lightning in
    a storm the script gives only thunder: the-red-kite 3.2, `nature`, newly accepted) do, **named on
    the storyboard frame's card as a warning** (web.md §4.3). **The comic shows such a panel with no
    note:** comic.md draws a `WARNED` panel as it draws a `PASSED` one (the same `run_checks`), so a
    misspelt sign or an unscripted pen reaches a comic page unannotated; the storyboard card is
    where it is named. This loosens the rule for props and painted words, so the team confirms it
    on the design PR. Strict again is one revert of `_SEVERITY` and `_filed`.
  - **No re-render for them:** a `WARN` is accepted at once, so a frame whose only faults are
    objects or lettering is shown at that attempt instead of drawn again (up to 3 attempts). That
    is the point: the retries went to frames klein can't draw without a bag or a misspelt sign.
  - **What else reads these checks** (checked, none changes): `report.py` parses object and text
    details whatever their severity, and its `ShotLine.failed` lists hard checks only, so it lists
    fewer; a report over a project with audits from before and after T089 shows the first row's
    severity for a check (old runs' reports stay as written). `recheck` reuses `run_checks`. The
    web's and the comic's `withheld_check` take the first failed hard check, so a withheld frame
    no longer names `text_in_frame`, or `unscripted_object` for anything but an animal or weapon.
  - **Evidence:** L014 (the five runs, the 46 drawings) and L015 (split panels) in
    docs/learning-log.md, landing with the-bread-van's second run report (#152), which merges first.
  - **Looked at, every newly accepted drawing (46):** 34 right, **12 wrong, every one in its people**:
    7 girls drawn as boys (sipho-and-siphokazi 2.2, 2.4, 4B.1, 4B.3, 6.1; lost-property 11.1, 3.2), two
    split panels (L015), Mr. Dube drawn young (lost-property 12.2), Theo at a steering wheel (the-bread-van
    3.1), a rowboat for a fishing boat (sipho 5.2). The audits of the girls predate T088 (no sex for
    Siphokazi or Amahle then; T088 finds both now, not Priya): the object checks were catching them by
    accident (L009). So T089 is live only with T088's sex, which is merged.
- **The judge is Nemotron** (`Tier.REASONING`, Nemotron 3 Super, thinking on). It gets the shot's
  grounded spec (characters with their quotes, props, location, time of day, the verbatim `source`)
  and the description. It decides only what needs judgement: which described person is which
  character (or nobody), and whether each object is a scripted prop, set dressing, or unscripted.
- **`PersonCall.person` and `ObjectCall.object`** are 0-based indexes into the description's `people`
  and `objects`. The judgement must call **every** person and **every** object **exactly once**; a
  judgement that skips one, repeats one, or indexes out of range is invalid, and the audit is
  `ERROR` (the frame is withheld).
- **`support` must be verbatim.** When the judge says an unnamed person or an object is supported
  by the script ("a crowd gathers"), `support` must quote the shot's `source` or a quote of one of
  the shot's entities. Code checks the quote with `normalize_for_grounding` substring matching,
  exactly as the grounding filter does. **A support that isn't found counts as unscripted.** For
  `set_dressing`, `support` must instead quote the scene heading (the location words that make a
  stove plausible in a kitchen).
- **`positions`**: character → `left | centre | right`, from the judge's person calls (each character
  matches at most one person, so the position is unambiguous). Stored with the audit; the comic
  reads the accepted audit's positions (comic.md §4, `PanelFrame.positions`).

### The checks

| Check | Decided by | Severity | Fails when |
|---|---|---|---|
| `UNSCRIPTED_PERSON` | judge + code | **hard** | a described person is called with no character (or a name not in `shot.characters`) and has no verified `support`; **or** a character is called for more than one person (every person after the first called for it counts as unscripted); or (T072) the `support` of a person called with no character names a shot character; or (T084) that support isn't found in the shot's action text (`shot_action_text`), or has `he`, `him` or `she`; or (T086) a matched person's described age contradicts the character's introduced age |
| `UNSCRIPTED_OBJECT` | judge + code | **hard** | an object called `unscripted`; `scripted_prop` without a verified `support`; or `set_dressing` when the object is `held`, or its category is `animal`, `vehicle`, `weapon` or `food`, or its `support` isn't found in the heading. **Never** for an object of category `clothing` or `architecture` that isn't held (T071): costume and the place's own structure are not story choices the script makes, whatever the judge called them. A `screen_or_sign` may be set dressing (T071): what makes a sign a risk is its words, which `TEXT_IN_FRAME` checks. **T072:** `set_dressing` also fails for an object whose name is, or is a word of, a prop the extraction names (§3). **T083:** never for an animal, vehicle, weapon or food the scene's action text names (`named_in_scene`); and an everyday unheld object called `unscripted`, or dressing not in the heading, is the soft `BACKGROUND_OBJECT` instead (§3, the order in `run_checks`). **T089:** hard only for an object whose category is `animal` or `weapon` (`_STORY_OBJECTS`); for every other object the same failure, with the same detail, is the soft `BACKGROUND_OBJECT` (§3, Objects and lettering warn) |
| `TEXT_IN_FRAME` | code | soft (T089; hard before) | a piece of the description's `text` isn't found (`normalize_for_grounding`, as whole words) in the shot's `source` or the scene's `location` (T071): legible words the script never wrote. The heading's time of day is not a haystack (a painted "NIGHT" is not the script's; since T089 it warns). An empty `text` passes, whatever `has_text` says; `has_text` is logged and shown but decides nothing. T089: soft, named on the card |
| `SETTING` | code | **hard** | `interior`/`exterior` contradicts `Scene.int_ext` (`INT_EXT` accepts either; `unclear` passes) |
| `NO_CHARACTER` (T080; T099) | code; T099: + presence agent (VISION) | **hard** | the prompt put at least one of the shot's people on screen (`on_screen`, from storyboard.md §3.1's `visible_characters`) and no described person is matched to any of them: a frame of the setting alone, or of strangers, for a shot about its characters (on 2026-10-11 shot 1.3 was an empty roof, shown with a warning). A shot whose people are only heard off screen, or that names no one, has an empty `on_screen` and never fails it. **T099:** a character the presence agent finds (a person who exists, not accepted as another character, of no contradicted age) counts as in the frame; the detail is unchanged |
| `MISSING_CHARACTER` | code | soft | a shot character **who is a person** matched to no described person (an animal character, `species` set, is described as an object: T052) |
| `LIGHT` | code | soft | `light` is `day` and the shot's time is night-family (`NIGHT`, `MIDNIGHT`, `EVENING`), or `light` is `night` and the time is day-family (`DAY`, `MORNING`, `AFTERNOON`). Transitional times (`DAWN`, `DUSK`, `SUNRISE`, `SUNSET`, `MAGIC HOUR`), a `None` time, `dawn_or_dusk` and `unclear` always pass |
| `FRAMING` | code | soft | `shot_size` is two or more steps from the shot's framing on wide → medium → close → extreme_close (`over_shoulder`, `pov` count as medium; `insert` as close); `unclear` passes |
| `BACKGROUND_OBJECT` (T083; T086: and unheld food) | judge + code | soft | an object of category `other`, `nature`, `furniture` or `screen_or_sign`, not `held`, not a named prop, called `unscripted`, or `set_dressing` whose `support` isn't in the heading (§3, Background objects warn): the place's everyday things the script didn't mention. Its detail is `object N (name, category): not in the script`. **T089:** also every object failure that isn't an animal's or a weapon's, with that failure's own detail (`held, so not set dressing`, `prop without support`, `unscripted`, `the script names it`, `never set dressing`, `not in the heading`) |
| `DRAWN_SEX` (T095) | sex agent (VISION) + code | **hard** | a person the judge matched to a character whose sex the script gives (`character_sex`) is drawn as the other sex: the sex agent, asked about that one person on the image, answers `male` or `female` and it isn't the script's. `unclear` passes, and so does a person matched to no character or to one with no sex from the script. Detail: `person N (position, appearance): drawn male, but REFILWE is female`. **T102:** also a person the presence agent finds for a character the script sexes (`found_people`), asked the same question |
| `SPLIT_PANELS` (T104) | layout agent (VISION) + code | **hard** | the layout agent, asked on a frame with two or more described people, answers `panels` > 1: the frame is a strip or grid of pictures, not one (L015). No answer (not asked, or a failed question) passes. Detail: `drawn as 2 panels` |
| `DRAWN_TWICE` (T104, T124) | layout agent (VISION) + code | **hard** | (T124: also a pair `described_alike`, with or without a layout answer, below) on a frame of one picture (`panels` 1), a `copies` pair of two described people in range who are not both known as characters (accepted by `matched_people`, or found by the presence agent: `found_people`), and so not two different characters: one person drawn twice. In a split frame the copies are the split's own (`SPLIT_PANELS` names it). Detail: `person 0 (left, …) and person 1 (right, …): the same person drawn twice` |
| `SIGNATURE` (T077) | code | soft | `signature` is true: a signature, initials or an artist's mark, readable or not. Since T107 the describer keeps a signature's letters out of `text`, readable or not, so a legible signature that isn't the script's (`@hutley`) still fails `TEXT_IN_FRAME` (soft since T089) |

**Verdict:** `FAIL` if any hard check fails; `WARN` if only soft checks fail; `PASS` otherwise. Hard
checks are the ones that would put something unscripted on screen; soft checks are quality
(an omission, a wrong light), logged and shown but not blocking.

**The rule ladder (T094; Tumo, 2026-10-13).** Which failed hard checks withhold a frame is a
setting, `AUDIT_WITHHOLD_CHECKS`: `all` (the default, every hard check, as above), empty (none), or a
comma list of hard check names (`drawn_sex,no_character`); a name that is no **hard** check (a typo,
or a soft check that could switch nothing on) is refused at start-up. `apply_ladder(audit,
withholding)` turns every hard check **not** on the ladder into a soft one in the audit itself, before
it is logged: an attempt whose remaining failed hard checks are none is `WARN` and accepted on that
attempt, and a withheld frame's audit holds only failed hard checks that are on the ladder, so every
reader that names the reason (`writer.withheld_check`, the comic's `withheld_checks`, the card's
`_noted`) names a check that withheld it. A warned card lists every failed check ("Audit: warn
(unscripted person, …)"). An audit that can't run (`ERROR`) still withholds, whatever the ladder:
nothing shows the frame was looked at. `recheck`, `reaudit` and the run report run today's checks at
full strictness (`all`) on the stored descriptions, so they show what each rule *would* withhold:
that is how a rule is measured before it goes back on the ladder; their "before" is the logged
verdict, the ladder's. **Why:** on 2026-10-13, market-day (held out) had 0 of 15 shots accepted,
though about 12 of the 15 final drawings were right: klein fills a market with shoppers and every
one failed `UNSCRIPTED_PERSON`. With an empty ladder the same script showed 16 of 17, 9 right, 5
weak, 2 split panels (L015), none of the wrong sex or age, in 17 drawings instead of 44.
**Non-negotiable I (PLAN.md):** an empty or partial ladder shows frames that fail a hard check, so §1's
"never shown" holds only for the checks on the ladder. This is Tumo's call (2026-10-13), labelled:
such a frame is always WARNED and its card names the failed check, never presented as passing. The
code default stays `all`; the hosted demo's value is set at deploy (render.yaml, deploy.md §6):
`drawn_sex,no_character,split_panels` since 2026-10-17 (Katlego, #190; T104 below).

**The sex agent (T095).** After the judge, for each described person accepted as a character whose
sex the script gives, one more vision call asks about that person alone. **Who:** `matched_people`,
pure, the rule `run_checks` itself uses: the judge's name resolved by `match_speaker` among the shot's
people, not refused for their age (T086), the first person called for that name; an animal never.
**Which sex:** `shot_sexes` (`character_sex` per shot person, passed in like `shot_ages`, since
`run_checks` has no screenplay). **The question:** the image, the person's `position` and
`appearance` as the describer wrote them, every other described person's position and appearance
("not these others: …") so two people in one position can't be confused, and the fixed
`SEX_AGENT_PROMPT`: male, female or unclear, as a `PersonCheck`. The questions of one attempt run at
once (`asyncio.gather`), the PNG encoded once. **Kept:** `Audit.seen` (`PersonSeen`: person, the
resolved character, sex), written by `FrameWriter.log` to the `frame_audits.seen` column (migration
0007), so `recheck` runs `DRAWN_SEX` again for free; its tokens count in the audit's usage and
models. **Fails:** `run_checks(..., seen=, sexes=)` fails `DRAWN_SEX` when an answer about a person
accepted as that character is the other sex; `unclear` passes. **Never an ERROR:** the agent runs
only after the judge succeeds (a judge failure is `ERROR` as before, with no question asked), in its
own handling: a failed question (an `LLMError` or `ValidationError`) checks nothing for that person
and is logged. **Measured** (2026-10-13, Token Factory, DeepSeek-V4.1-Flash, stored drawings of
stormwater, load-shedding, the-night-taxi, market-day's second run and the-red-kite; the labels' sex
standing in for the script's, and the prototype asking about every judge match): **175** matched
people asked; 154 agree, 9 `unclear`, **12 the other sex, every one looked at and every one a real
error** (Fatima drawn as a boy twice, Pieter as a girl twice, a girl matched to Jabu, a young man to
Fatima, Refilwe as a boy three times, Sibusiso as a young woman three times); **0 false alarms**.
Three known wrong frames pass as `unclear` (Refilwe as a short-haired child in 1.2 and 6.2,
load-shedding 1.2). About 1,000 tokens a question, so roughly 45,000 a script of 20 shots.
**No age:** the prototype asked age too, and called men in their 50s `old` 15 times (BONGANI,
MR. VAN DER MERWE) and a 60s woman `adult`; nothing would read it, so the question is sex only and
T086's code age check stays the one age rule. **Only where the script gives a sex:** in the live
runs above, REFILWE, SIBUSISO and FATIMA had none in the extraction, so the agent would have asked
about none of them; T096 and the L018 work widen that. A row's `seen` holds only the characters
sexed when it was audited: `recheck` can't measure a sex found later (that needs `reaudit`, tokens).

**The head agent (T097; Katlego, 2026-10-14).** Where each described person's head is in a comic
panel's accepted frame, so the comic can point a bubble's tail at the speaker's head and keep
bubbles off faces (comic.md §4 steps 7 and 8, T098). **It is no check:** it never fails, warns,
withholds or changes a verdict; it only measures. **When:** in `render_until_accepted`, only with
`heads=True` (the comic job; the storyboard has no bubbles), and only on the attempt that is
accepted, after the ladder: one question per panel, never one on a frame that is thrown away.
**The question:** the image, every described person numbered with their `position` and
`appearance` as the describer wrote them (`0: left third, an old man …`), and the fixed
`HEAD_AGENT_PROMPT`, on `Tier.VISION`, `max_tokens=4096`; the answer is a `HeadCheck`: per person,
`visible` and a box `x0, y0, x1, y1` as fractions of the frame's width and height from its
top-left. **Kept:** `heads_seen` (pure) keeps an answer only when its person is a described one,
the first answer for that person, `visible`, and `0 ≤ x0 < x1 ≤ 1`, `0 ≤ y0 < y1 ≤ 1`; anything
else is dropped (counted in one log line). Each kept box becomes a `HeadSeen` carrying the
character that person was accepted as (`Audit.matched`, the same `matched_people` the sex agent
uses; `None` for a person matched to no one), written by `FrameWriter.log` to
`frame_audits.heads` (migration 0010; 0008 is T099's `audit_found`, 0009 T104's `audit_layout`); its tokens count in the audit's usage and models. **Never
an ERROR:** a failed question (`LLMError` or `ValidationError`) leaves `heads` empty and is
logged; the frame is accepted exactly as it was, and the comic falls back to the third. A frame
with no described person asks nothing. **Measured** (2026-10-14, Token Factory,
DeepSeek-V4.1-Flash, a prototype asking head boxes and anatomy in one call, on 15 distinct
drawings of the 2026-10-10 the-red-kite runs, Workers AI's FLUX.2 [klein] 4B, 21 people): every
box of the 8 drawings looked at lies on the head, the small far ones and profiles too, sometimes
generous, never off; the same drawing asked twice gave boxes within 0.02; about 1,900 prompt and
500 completion tokens a frame; 0 of 30 questions failed (one of a later 15, with a longer prompt,
spent its budget thinking at `max_tokens=2048`, hence 4096). The prompt here is the head half of
the prototype's, and the vision model is now Nemotron 3.5 Super VL (T105, 2026-10-17), so T097's
Verify measures it again, on Super VL. **Measured on Super VL** (2026-10-17, T097's code, thinking
off, `find_heads` itself): the 18 distinct drawings of that probe, 24 described people, 24 boxes,
every one on its head (the small far ones, profiles and a back of a head too), 0 failed
questions, about 1,340 prompt and 100 completion tokens a frame. **No anatomy:** the same prototype was asked
for each person's heads, arms, legs and hands, and called a man drawn with three arms (0.3 a1)
`normal` twice, even when told to count each limb back to its shoulder; it counted 0 legs on
standing people and 1 arm on a person with two, and called one drawing's ordinary hands deformed.
A rule built on it would withhold right frames and pass wrong ones, so there is none (§8).

**The presence agent (T099).** When the judge has matched none of the people the prompt drew, so
`NO_CHARACTER` would fail, one more vision call per drawn character asks which described person, if
any, is that character. **Why:** on nine stored runs (2026-10-14) `NO_CHARACTER` would have withheld
30 frames that `drawn_sex` alone shows, and 23 of them had the character plainly drawn (22 at first
look; final-whistle 3.3's referee does wear the script's striped shirt): the describer
saw the person, and the judge called them no one, often citing the character's own line as the
stranger's support (the-night-taxi 2.4, "a child … laughing … leaning out of the car's rear window",
support "Thabo laughs."). **When:** only after the judge succeeds with a judgement that calls every described person and
object once (`_calls_each_once`, the test `run_checks` makes before anything else: a malformed
one is `ERROR` and asks nothing), and only when `on_screen` (the people of `visible_characters`,
no animal) is not empty and `matched_people` accepts none of them. **Order:** after the sex agent's
questions (T095), one `gather` after the other; the two are independent (a heard-only character can
be matched while no drawn one is), so both can run on one attempt.
**Who:** each such character, one question each, all at once (`asyncio.gather`), the PNG encoded
once per attempt by `audit_frame` as a data URL and passed to both agents (`_ask_sexes` takes it
instead of the PNG bytes). **The question:** the fixed `PRESENCE_AGENT_PROMPT` (§6,
verbatim); the user text is the character's line exactly as the judge gets it (`_quoted`, then
`_sexed`'s sex line when the script gives one), the shot's `source`, and every described person as
`[i] position: appearance` (or `none`), then the image; the answer is a `Presence` (`person`, an
index or null, and a short `reason`), at `max_tokens=4096` (at 1,024 the vision model ran out and
returned nothing on 9 of about 40 questions; at 4,096, 6 of about 80). **Kept:** every answer, as
`Audit.found` (`PersonFound`: character, person, reason), written by `FrameWriter.log` to the
`frame_audits.found` column (migration 0008), so `recheck` decides `NO_CHARACTER` again for free; its
tokens count in the audit's usage and models. **Passes:** `run_checks(..., found=)` counts a
character as in the frame for `NO_CHARACTER` when an answer names a person who exists, whom
`matched_people` doesn't already accept as another character, and whose described age doesn't
contradict the character's introduced years (`age_contradicts`, T086). That is all it changes: the
person stays unmatched for every other check (`UNSCRIPTED_PERSON`, `MISSING_CHARACTER`; and
`DRAWN_SEX` until T102, which asks a found person's sex: below), so a found person is no excuse for
anything else, and `positions` is unchanged (a
speaker shown only through `found` gets the comic bubble's fallback placement). **What the viewer
sees (Non-negotiable I):** a person the agent finds is still unmatched, so the judge's call stands
for `UNSCRIPTED_PERSON`: the person passes it only when the judge's support holds for a stranger
(T084: an action line of the shot, naming no character, with no he or she), and otherwise fails it,
a warning the card names on a ladder without it (`person N: no shot character, no support`). So a
frame shown only through `found` carries no note of it when the judge's stranger support holds; the
agent's own pick is not on the card, it is in the audit log (`found`). The cost is the measured one:
about a third of the real misses found wrongly are shown, warned. **Never an ERROR:** a failed
question (an `LLMError` or `ValidationError`) finds no one, is logged, and leaves `NO_CHARACTER` as
the judge's matches decide it, so the verdict is the judge-alone verdict; the safe side, a redraw. **Measured** (2026-10-14, Token Factory,
DeepSeek-V4.1-Flash, the 30 stored frames above, every one looked at; prototype
`proto_presence.py`, two runs): **18 and 16 of the 23 false alarms found**, and **2 and 3 of the 7
real misses wrongly found**: load-shedding 2.1 (an adult seen from behind in an empty classroom
taken for LUCKY), lost-property 9.4 (MR. DUBE in a split panel, L015, a fault of its own) and the
bread-van 4.1 (once; a woman at the shop window for AUNTIE BETTY, arguably right). The frames still
withheld include real faults of other kinds: the-night-taxi 5.4 (BONGANI, 50s, drawn a teenager
and UNCLE SIZWE, 30s, old: the age refusal), stormwater 6.4 (Mr. Van der Merwe drawn young),
lost-property 3.2 (Priya drawn as a man). About 2,000 tokens a frame it runs on; it would have run on 30 of
the 218 shots' shown frames above (and on more of the attempts before them).

**A found person is asked the sex question too (T102).** Found on 2026-10-14 (L022): the-lighthouse-
inspector 7.5 drew Mr. Fortuin as an old woman; the judge matched no one, the presence agent found her
as him, and a found person was asked nothing, so the frame was shown. T099 left `DRAWN_SEX` out of a
found person on purpose ("measured only for presence"); this is that measurement. **Who:** after the
presence agent, each person `found_people` gives (the rule `present_characters` already applies: an
answer naming a person in range, not accepted by `matched_people` as another character, of no
contradicted age), for a character the script sexes (`sexes`, as T095). **One question per
person:** the question names no character, so a person found for two characters (load-shedding
5.2: JABU and PIETER both person 0) is asked once, and the answer is kept once per character
(`PersonSeen(person, character, sex)` for each, characters in name order). When those characters'
script sexes differ, the answer fails `DRAWN_SEX` for the one it contradicts: a decision, because
one person can't be both, and at most one of them is drawn. **The question:** T095's
(`check_person`: the image, the person's position and appearance, the others, `SEX_AGENT_PROMPT`),
all at once, after the presence agent's `gather`. **Its token budget** rises from 1,024 to 4,096 for
T095's questions too (`check_person` serves both): at 1,024, 6 of the 36 questions below came back
empty (the vision model spent the budget thinking), as T099's presence questions did at 1,024 (9 of
about 40; 6 of about 80 at 4,096); the budget is a ceiling, so an answer that ends early costs what
it did. **Kept:** in
`Audit.seen` with T095's answers (`PersonSeen`: person, character, sex), so `recheck` reads them from
`frame_audits.seen` with no migration; a row from before T102 has none for found people and decides
as before. **Fails:** `run_checks` fails `DRAWN_SEX` for an answer about a person found as that
character (`found_people(...)[character] == person`) that is the other sex, with T095's detail;
`unclear` passes. A found person still counts for `NO_CHARACTER` (T099 is unchanged), but the
frame fails `DRAWN_SEX`: withheld and redrawn when `drawn_sex` is on the ladder
(`AUDIT_WITHHOLD_CHECKS`, T094; render.yaml sets `drawn_sex,no_character,split_panels`, §3 T104 and
§6 T124; `drawn_sex,no_character` until 2026-10-17), else
`WARN`, the card naming the check.
Nothing else changes: the found person stays unmatched for `UNSCRIPTED_PERSON` and
`MISSING_CHARACTER`. **Never an ERROR:** as T095, a failed question checks nothing for that person
and is logged. **Measured** (2026-10-16, Token Factory, DeepSeek-V4.1-Flash, `proto_found_sex.py`;
no fal): every stored storyboard attempt of the newest run of 11 scripts (511 audits) where
`audit_frame` would run the presence agent: **77 frames**; the presence agent (today's code, run
afresh) found **36** people for characters the script sexes; asked, **2 the other sex, both looked
at and both real errors** (sipho-and-siphokazi 2.1's second attempt, MAMA THEMBI drawn as an old
man; the-borrowed-bicycle 4.1, NALEDI drawn as a boy, L023), 2 `unclear` (LUCKY seen from behind,
KAMO), 26 agreeing, 6 failed questions (the vision model spent its 1,024 tokens thinking: logged,
checking nothing); **0 false alarms**: 2 of 36, a small sample, the rule generic. the-lighthouse-
inspector 7.5 isn't among them: its stored extraction gives the bare `FORTUIN` no sex; since T101
the character is `MR. FORTUIN`, whose title gives the prompt and `character_sex` male, so 7.5 would
be asked. **The real code** (2026-10-16, `real_t102.py`, the branch's `app/` on the same 77 frames, the
lighthouse re-grounded with T101 and its shots' names folded, so 7.5's MR. FORTUIN pair joins the
prototype's 36): 37 pairs asked, 36 answered (**1 failed**
at 4,096 tokens, against 6 at 1,024), `DRAWN_SEX` fails on **4 frames**, every one looked at: lighthouse
7.5 (an old woman for MR. FORTUIN: the L022 case, now caught), sipho-and-siphokazi 2.1 and the
borrowed-bicycle 4.1 (as above), and the-night-taxi 2.3's second attempt (THABO, the child leaning
out of the window, bobbed hair and a sleeveless top: arguable, and the frame is wrong anyway, a
child at the taxi's wheel); 0 plainly false. About 1,000 tokens a question, on
the frames the presence agent runs on (36 questions on 33 of the 77 frames here).

**The layout agent: several panels, or one person drawn twice (T104).** klein, on a storyboard
prompt, sometimes draws a strip or grid of panels (L015), and sometimes one character twice in one
picture (the-night-taxi 1.4, THABO three times; the-red-kite 4.1, LERATO twice in the alley; L022,
lighthouse 4.2). The describer lists every figure as a person of one frame, so nothing checked
either: a split frame was shown (market-day 4.2 and 5.2 warned, the-red-kite 5.2 passed), and the
copy was a stranger at most (`UNSCRIPTED_PERSON`, off the ladder since T094). **When:** after the
judge succeeds with a well-formed judgement (`_calls_each_once`), on a frame with **two or more**
described people (a split or a copy needs two figures), after the T095, T099 and T102 questions.
**The question:** one vision call, the fixed `LAYOUT_AGENT_PROMPT` (§6, verbatim), the user text
`People in the drawing:` then `[i] position: appearance` per person, then the image (the data URL
`audit_frame` already encoded), at `max_tokens=4096`; the answer is a `Layout` (`panels`, `copies`
as `[a, b]` pairs, `reason`). **Kept:** `Audit.layout` (`FrameLayout`: panels, copies as sorted
pairs, reason), written by `FrameWriter.log` to the `frame_audits.layout` column (migration 0009: see
**Migration** below), so `recheck` decides both checks again
for free; its tokens count in the audit's usage and models. **The answer, cleaned** (`frame_layout`,
pure): `panels` below 1 is 1 (a model's 0 or -1 is no split); `copies` keeps each pair of exactly two
indexes `a != b` with `0 <= a, b < len(description.people)` once, as the sorted `(a, b)`, the pairs in
sorted order; anything else is dropped. **Fails:** `run_checks(..., layout=)`: `SPLIT_PANELS` when
`panels > 1`; `DRAWN_TWICE` when `panels == 1`, for each kept pair on its own (a frame may have
several: the same boy three times is `(0, 1)`, `(0, 2)`, `(1, 2)`; the details are joined by `; ` as
every check's are), unless **both** people are known as characters: in `accepted` (`matched_people`)
or found by the presence agent (`found_people`, T099/T102), as person → character. Both known means
two different characters, since neither map gives one character two people (`matched_people` keeps
the first person per name; `found_people` one person per character, and a person it finds is never
in `accepted`). One known and one not is still a copy (fails); neither known fails. That veto is the
measured fix for the one kind of false alarm: two cast characters who look alike (final-whistle 6.1,
PALESA and LINDI, matched to each); with `found_people` in it, the same two found by the presence
agent pass too. It uses the accepted matches, not the judge's raw ones: on lost-property 7.3 the
judge called a young man KOOS (the 70s night cleaner), refused for his age, so the copy of TEBOGO
still fails. **Known risk, generic:** look-alike extras the script doesn't cast (pupils in uniform,
guards) are never vetoed (they are no character); only the prompt's "people who merely look alike
… are not copies" guards them, one more reason the ladder entry is Tumo's call. **Every target:**
`audit_frame` audits storyboard frames and comic panels alike (`loop.py`, and `reaudit.py` and
`run.py` for measuring), so comic panels get the question and both checks too. Both are **hard**, so they withhold only when on the ladder
(`AUDIT_WITHHOLD_CHECKS`, T094). **The hosted ladder** (Katlego, 2026-10-17, #190):
`drawn_sex,no_character,split_panels`: a split withholds (23 of 23 flags real), a copy warns (5
real and 1 wrong anyway after the veto, recall unmeasured); `render.yaml` takes it with T104's code,
since `withholding` refuses a check name the running code doesn't know. A withheld frame is
redrawn: a new seed, a new layout; on the hosted ladder about 5.7% of attempts are split, some
shots on every attempt (lost-property 11.5 split on all three), so they end withheld. **Never an ERROR:** a failed question (an `LLMError` or `ValidationError`) leaves `layout`
None, is logged, and both checks pass. **Cost:** about 1,400 tokens a question, asked on about
two thirds of attempts (332 of 511 had two or more people): about 15,000–24,000 tokens a storyboard
of 17–26 attempts (limits.md §3: its audit is 130,000–175,000, so about +12–14%), the same again
for its comic: about 30,000–48,000 a storyboard and comic, +9–14% on the 339,000 deploy.md §6
sizes `LLM_MONTHLY_TOKEN_CAP` by (about 370,000–387,000 each, about 7 a month instead of 8); and, when on the ladder, each withheld frame is one
more attempt, a drawing (the image budget, T030) and its audit. **Old rows:** a row from before T104
has no `layout`, so `recheck` can't measure `SPLIT_PANELS` or the layout's copies on it (they pass),
as for a sex found later; T124's described-alike pairs need only the description, so they are checked. **Migration:** `0009_audit_layout` (T097's heads are `0010_audit_heads`, down_revision 0009).
**Described alike (T124; 2026-10-19, `eval/measurements/t124/`).** The layout agent argues copies apart:
on gogos-recipe 2.1 the describer gave both children the same words ("a child in a short-sleeved shirt
and shorts") and the agent answered "different faces, hair, and clothing details"; 1.4's second
attempt, "loose hair against a ponytail". And a caught copy only warned. So **a pair the describer
itself described alike is a copy too**, in code: `described_alike` (pure, §6) gives each pair of
described people, not both characters and not both scripted extras, whose
`appearance` words overlap by **at least 0.5** (Jaccard on the lowercase words, a short stop-word
list out). Characters are T104's `known` (accepted ∪ found); a **scripted extra** is a
person the judge called no character with a support that passes every `UNSCRIPTED_PERSON` test (found,
naming no character, an action line, pointing at no one else). A scripted crowd ("PUPILS fill the
corridor", "two GUARDS") is drawn alike on every attempt, so without it such a shot would be withheld
three times over (review of #222). A character and an alike stranger, or a character and an alike
extra, is still a copy. Layout pairs keep T104's veto (characters only). Each such pair not already a
layout pair fails `DRAWN_TWICE` with its own detail. It needs
no layout answer (a frame of one person has no pairs; a failed layout question still lets it run),
but a split frame (`panels > 1`) is `SPLIT_PANELS`'s alone. **Measured** on stored Super VL audits,
67 labelled attempts with 10 copies and 34 right frames (the 17 Oct runs, lighthouse, red-kite):
alone it catches 7 of 10 copies, with the layout agent 8 of 10, and flags **no right frame** (4 weak
ones, one of them a real extra person). **Known risk:** on the 109 labelled frames' stored DeepSeek
descriptions it flags 6 of 40 right frames, each a cast the judge didn't match whose two people
DeepSeek described in generic words ("a man in a shirt"). Super VL describes every hosted frame and
writes longer appearances; the-choir and the judge sample measure it again. **Off the hosted
ladder** (2026-10-20, after one night on it): T124 put `drawn_twice` on the ladder, and the T109
re-score of the 109 labelled frames the next day (Super VL, today's code;
`eval/measurements/t124/rescore-2026-10-20/`) withheld 6 of the 40 right frames for it, against 1
without it. Re-asked with details, the flags came from both sources: the word rule where the judge
matched neither of two look-alike cast members (final-whistle 2.1), one of a pair (the-night-taxi
1.1), or one of a 24-person crowd (market-day 3.2); and the layout agent itself (the-night-taxi 2.1,
two men with buckets called one man). The answers also vary run to run (final-whistle 6.1 and 6.2
passed on the re-ask). So a copy now **warns**, named on its card by both detectors, and the hosted
ladder is back to `drawn_sex,no_character,split_panels`. Withholding it again waits on a judge that
matches the drawn cast, measured on the-choir and the judge sample.

**Measured** (2026-10-16, Token Factory, DeepSeek-V4.1-Flash,
`proto_twice.py`, the prompt verbatim; no fal): every stored storyboard attempt of the newest run of
11 scripts with two or more described people, **332** of 511; 330 answered. **Splits: 23 flagged,
every one looked at, all 23 real** (lost-property 11.5's three attempts, a 2×2 grid among them;
the-night-taxi 6.3's two; the-bread-van 1.3's two; …). **Copies on one picture: 8 flagged, every
one looked at with its cast:** 6 real (the-night-taxi 1.4, the-red-kite 4.1, lost-property 7.3
and 9.1, the-bread-van 4.4, the-borrowed-bicycle 5.2), 2 not: final-whistle 6.1 (PALESA and LINDI,
removed by the veto) and stormwater 3.1's second attempt (two boys for SIBUSISO and REFILWE,
matched to no one: a wrong frame anyway, Refilwe drawn as a boy). The veto, computed on the stored
judgements, removes final-whistle 6.1 and one real copy, lost-property 9.1's third attempt, where
the judge accepted the two look-alike girls as TEBOGO and PRIYA (a girl for Tebogo, a young man:
`DRAWN_SEX`'s to catch). So, with the veto, **29 flags: 28 real, the 29th a wrong frame**. These are in-sample (the
prompt's look-alike sentence was written on these frames) and precision only: recall isn't
measured beyond the misses below, and the 179 attempts with fewer than two people were never asked
(a split among them is unmeasured). The held-out runs are the real check. **Missed:** lighthouse
4.2 and 7.3 (two women in suits on the stairs for MS. NAIDOO alone: the agent saw short against
shoulder-length hair and called them two people). About 1,400 tokens a question (456,411 for 332).

## 4. Flow

```mermaid
sequenceDiagram
    participant J as Frame job
    participant R as Renderer (T026)
    participant D as Describer (VISION)
    participant N as Judge (Nemotron, REASONING)
    participant L as Audit log (Postgres)
    loop attempt 1 .. max_renders
        J->>R: render(shot, attempt)  (seed from shot + attempt)
        R-->>J: RenderedFrame
        J->>D: image + neutral instruction → FrameDescription
        J->>N: shot spec + description → Judgement
        J->>D: T095: each matched person with a script sex → PersonCheck
        J->>D: T099: none of on_screen matched → each on_screen character → Presence
        J->>D: T102: each found person with a script sex → PersonCheck
        J->>D: T104: two or more described people → Layout (panels, copies)
        J->>J: verify supports; run the checks; verdict; T094: a hard failure off the ladder warns
        opt T097: heads=True (a comic panel) and the attempt is accepted
            J->>D: every described person → HeadCheck (head boxes; never a verdict)
        end
        J->>L: Audit (every attempt, pass or fail)
        alt PASS or WARN
            J-->>J: state PASSED / WARNED; stop
        else FAIL and attempts left
            J-->>J: next attempt
        end
    end
    J-->>J: out of attempts: WITHHELD
```

- **Seeds** are deterministic: `seed(shot, attempt)`, so an attempt can be reproduced.
- **`max_renders` = 3** (the first render plus two re-renders, `k = 2`). With a pass rate `p = 0.6`
  that's `E[N] ≈ 1.56` renders per frame; the real `p` is in the run reports (`eval/runs/`).
  **T071:** it is the setting `RENDER_MAX_ATTEMPTS` (`Settings.render_max_attempts`, 1 to 3,
  default 3). Every full loop passes it: the storyboard's rendering stage (T026's
  `build_storyboard`) and the comic job (T064); "Try another render" still passes 1. The
  live run of 2026-10-10 is why: 257 drawings, 3 accepted, 2 of them on a second attempt, because
  the failures were systematic (the same sign, the same jacket), so a re-render bought another
  FAIL. A dev run sets 1 until the pass rate is known; the frame sheet's "attempt n of N" reads
  the same setting.
- **A withheld frame is never shown.** The storyboard shows its shot as a text card:
  the verbatim `source`, the span, and "Frame withheld: failed audit (unscripted person)". The user
  can ask for more attempts later; each is audited the same way. The comic has its own withheld
  card, without the source (its bubbles letter the dialogue): comic.md §4 step 6.

**Failure paths:** the describer or judge call fails (an `LLMError`, or `ValidationError` after the
repair retry) → that attempt's audit is `ERROR`, logged, and the frame is **withheld**, never passed
unaudited. The renderer fails → the frame job fails (a `Job` `FAILED`). A frame is never shown
without a `PASS` or `WARN` audit.

**Animal characters (T052).** An animal character (`animals(extraction)`, storyboard.md §3.1:
its own `species`, or bound to an animal by `match_speaker`) is drawn as an animal, and the describer files an animal under objects (`ObjectCategory.ANIMAL`). So the judge's
spec lists it under **"Animals in this shot"** (name, species, its quotes), not under "Characters
in this shot"; the judge prompt says an animal listed there is called `scripted_prop` with a
verbatim support quote that names it; people are matched only against the shot's person
characters (`match_speaker` over those); and `MISSING_CHARACTER` checks person characters only.
An unscripted animal is still `UNSCRIPTED_OBJECT` (hard), as before.

## 5. State

```mermaid
stateDiagram-v2
    [*] --> RENDERING
    RENDERING --> AUDITING
    AUDITING --> PASSED: PASS
    AUDITING --> WARNED: WARN
    AUDITING --> RENDERING: FAIL, attempts left
    AUDITING --> WITHHELD: FAIL, no attempts left
    AUDITING --> WITHHELD: audit ERROR
    RENDERING --> FAILED: renderer error
    RENDERING --> FAILED: interrupted by an API restart (startup sweep)
    AUDITING --> FAILED: interrupted by an API restart (startup sweep)
    WITHHELD --> RENDERING: user asks for another attempt
    FAILED --> RENDERING: user asks for another attempt
    PASSED --> [*]
    WARNED --> [*]
    FAILED --> [*]
```

`PASSED` and `WARNED` are the only states whose frame may be displayed. No transition skips
`AUDITING`. The two sweep edges (added with docs/design/web.md, 2026-09-30) are taken only by the
startup sweep, for frames whose job died with the process; T021 implements them. `FAILED →
RENDERING` (T066, 2026-10-10) is "Try another render" on a frame whose renderer failed or whose
render a restart cut off, as on a withheld one: a failed frame is no longer the end of the line,
since one passing renderer error no longer stops the storyboard (storyboard.md §4).

## 6. Contracts

```python
# app/verify/model.py
class Position(StrEnum): LEFT = "left"; CENTRE = "centre"; RIGHT = "right"
class Setting(StrEnum): INTERIOR = "interior"; EXTERIOR = "exterior"; UNCLEAR = "unclear"
class Light(StrEnum): DAY = "day"; NIGHT = "night"; DAWN_OR_DUSK = "dawn_or_dusk"; UNCLEAR = "unclear"
class ShotSize(StrEnum): WIDE = "wide"; MEDIUM = "medium"; CLOSE = "close"; EXTREME_CLOSE = "extreme_close"; UNCLEAR = "unclear"
class ObjectKind(StrEnum): SCRIPTED_PROP = "scripted_prop"; SET_DRESSING = "set_dressing"; UNSCRIPTED = "unscripted"
class ObjectCategory(StrEnum): FURNITURE = "furniture"; ARCHITECTURE = "architecture"; NATURE = "nature"; CLOTHING = "clothing"; ANIMAL = "animal"; VEHICLE = "vehicle"; WEAPON = "weapon"; SCREEN_OR_SIGN = "screen_or_sign"; FOOD = "food"; OTHER = "other"
class Check(StrEnum): UNSCRIPTED_PERSON; UNSCRIPTED_OBJECT; TEXT_IN_FRAME; SETTING; MISSING_CHARACTER; LIGHT; FRAMING; SIGNATURE; NO_CHARACTER; BACKGROUND_OBJECT   # BACKGROUND_OBJECT: T083, soft; value = the name in lower case; SIGNATURE: T077, soft; NO_CHARACTER: T080, hard;
#   T089: TEXT_IN_FRAME soft, UNSCRIPTED_OBJECT only for an animal or a weapon
class Severity(StrEnum): HARD = "hard"; SOFT = "soft"
class Verdict(StrEnum): PASS = "pass"; WARN = "warn"; FAIL = "fail"; ERROR = "error"
class FrameState(StrEnum): RENDERING; AUDITING; PASSED; WARNED; WITHHELD; FAILED   # value = the name in lower case
@dataclass(frozen=True) class CheckResult: check: Check; severity: Severity; ok: bool; detail: str
@dataclass(frozen=True) class Audit: shot: tuple[int, int]; attempt: int; seed: int; description: FrameDescription | None; judgement: Judgement | None; checks: tuple[CheckResult, ...]; verdict: Verdict; positions: dict[str, Position]; models: tuple[str, ...]; usage: Usage
@dataclass(frozen=True) class FrameOutcome: shot: tuple[int, int]; state: FrameState; frame: RenderedFrame | None; audits: tuple[Audit, ...]

# app/verify/schema.py — the two model calls (strict json_schema)
class SeenPerson(BaseModel): position: Position; appearance: str
class SeenObject(BaseModel): name: str; category: ObjectCategory; held: bool
class FrameDescription(BaseModel): people: list[SeenPerson]; setting: Setting; light: Light; shot_size: ShotSize; objects: list[SeenObject]; signature: bool; signature_text: list[str] = []; has_text: bool; text: list[str]   # T107: the signature first, its letters in their own slot; signature_text required in the model's schema, [] for a stored row before T107
#   text (T071): each piece of writing the describer can read, verbatim, in reading order; [] for none.
#   The describer must always return it (strict schema). A row written before T071 has no `text`:
#   AuditView's description reads it as [] (its old has_text verdict stands in the log)
#   signature (T072): a signature, initials or an artist's mark anywhere, readable or not; required
#   from the describer; a row written before T072 reads as false in AuditView
class PersonCall(BaseModel): person: int; character: str | None; support: str | None   # person: 0-based index into description.people
class ObjectCall(BaseModel): object: int; kind: ObjectKind; support: str | None        # object: 0-based index into description.objects
class Judgement(BaseModel): people: list[PersonCall]; objects: list[ObjectCall]

# The renderer T026 must provide (verify depends on this shape, nothing more)
@dataclass(frozen=True) class RenderedFrame: shot: tuple[int, int]; attempt: int; seed: int; png: bytes; width: int; height: int; prompt: str
class Renderer(Protocol):
    async def render(self, shot: Shot, attempt: int, seed: int, width: int, height: int) -> RenderedFrame: ...
    # width × height: the storyboard's 16:9 size, or a comic panel's rect (comic.md §4 step 6)

# app/verify/audit.py (T020)
async def describe_frame(model: NebiusChatModel, png: bytes) -> tuple[FrameDescription, ChatResult]: ...
#   the blind describer on its own (Tier.VISION, no shot details); audit_frame is its only caller
#   (portraits, characters.md, were to call it too: T025, cut 2026-10-19)
def seed_for(shot: Shot, attempt: int) -> int: ...          # int.from_bytes(sha256(f"{scene_index}:{number}:{attempt}").digest()[:4], "big")  (unsigned)
def part_of_prop(name: str, category: ObjectCategory, shot: Shot, extraction: Extraction) -> str | None: ...   # T078, pure:
#   the shot prop whose part `name` is (§3, A part of a prop), or None; the first such prop in
#   `shot.props` order that the extraction quotes
def named_in_scene(name: str, category: ObjectCategory, scene: Scene) -> str | None: ...   # T083, pure:
#   the scene word that names the object (§3, Things the scene names), or None; only for animal, vehicle,
#   weapon and food. run_checks skips an object it names, as it does a part_of_prop
def shot_action_text(shot: Shot, scene: Scene) -> str: ...   # T084, pure:
#   normalize_for_grounding of the text of `scene.elements[i]` for each `i` in `shot.elements` that is an
#   `Action`, joined by " " in order; "" when the shot covers no action. A person's support must be found
#   in it (§3, A person's support is an action line)
# _PERSON_PRONOUNS = frozenset({"he", "him", "she"})  # T084: against re.findall(r"[a-z]+", support.lower())
def described_age(appearance: str) -> str | None: ...   # T086, pure: "child", "teenager", "old" or "adult",
#   the earliest match in the lower-cased appearance of: child \b(child|children|kids?|boys?|girls?|toddlers?|baby|
#   babies|infant)\b; teenager \b(teenagers?|teens?|teenage|adolescents?)\b; old \bold (man|woman|person|adult)\b|
#   \belderly\b|\b(grandmother|grandfather|granny|grandma|grandpa)\b; adult \b(adults?|man|men|woman|women|mother|
#   father|mum|mom|dad|lady|gentleman|guy)\b; None when none matches
def age_contradicts(years: int, described: str | None) -> bool: ...   # T086, pure: §3, A matched person's age
def inside_vehicle(scene: Scene) -> frozenset[str]: ...   # T086, pure: the location's head noun (the last of
#   re.findall(r"[a-z]+", location.split(" - ")[0].lower())) when it is in _VEHICLE_PLACES and the scene isn't
#   EXT; empty otherwise
def part_of_vehicle(name: str, category: ObjectCategory, scene: Scene) -> bool: ...   # T086, pure: §3, Inside a
#   vehicle; the name split as named_in_scene splits it, its last word's _forms against _VEHICLE_PART_WORDS |
#   _INTERIOR_WORDS, or any word in _INTERIOR_WORDS; False outside a vehicle, with a copy word, or for an animal,
#   weapon or food
def shot_ages(shot: Shot, screenplay: Screenplay, years: Callable[[str, Screenplay], int | None]) -> dict[str, int]: ...
#   T086: {character: years} for each shot character years() gives; years is storyboard's introduced_years,
#   passed in (app.storyboard imports app.verify)
# run_checks(..., *, on_screen=(), ages: Mapping[str, int] | None = None)  # T086: ages from shot_ages
_STORY_OBJECTS: frozenset[ObjectCategory] = frozenset({ObjectCategory.ANIMAL, ObjectCategory.WEAPON})  # T089
def _filed(category: ObjectCategory) -> Check: ...   # T089, pure: UNSCRIPTED_OBJECT if category in
#   _STORY_OBJECTS else BACKGROUND_OBJECT; used at every UNSCRIPTED_OBJECT append in run_checks
# _SEVERITY[Check.TEXT_IN_FRAME] = Severity.SOFT  (T089; UNSCRIPTED_OBJECT stays HARD, for animals and weapons)
# services/api/app/verify/recheck.py (T083): measures a code-only audit change for free
async def recheck(sessions: async_sessionmaker[AsyncSession], project_id: UUID, *,
                  target: AuditTarget | None = None) -> tuple[list[Reaudit], int]: ...
#   every stored audit of the project (one target, or both), in reaudit's order, re-checked: today's
#   run_checks on its stored description and judgement, on_screen = visible_characters(shot, screenplay,
#   extraction) for every row of either target, exactly as audit_frame builds it (imported inside the
#   function, as audit_frame does: the storyboard import cycle). `before` is the stored verdict, `after`
#   today's. Skipped, and counted in the returned int: a row whose description or judgement is NULL (an
#   ERROR) or doesn't validate as FrameDescription / Judgement (stored before today's schema). A row whose
#   lists make run_checks return ERROR is not skipped: its `after` is `error`. Reads the project and its
#   frame_audits only: no model, no Storage, no write. Raises ValueError for no project or no plan,
#   as reaudit does. T094: `withholding=` (keyword, default None), the rule ladder, applied to each
#   row's checks as the loop applies it before it logs (`apply_ladder`), so a stored WARN isn't a
#   change; the CLI passes `withholding(Settings())`, so AUDIT_WITHHOLD_CHECKS names a rule to
#   measure on its way back (code review of #168)
def accepted_shots(rows: Sequence[Reaudit]) -> tuple[int, int]: ...   # pure: shots with any attempt
#   `pass` or `warn`, before and after
# python -m app.verify.recheck <project-id> [--target storyboard|comic]   (default: both, as reaudit)
#   prints reaudit.line per row, then reaudit.summary, then "shots with an accepted attempt: <b> → <a>"
#   and "skipped: <n>". Exit 0; 2 with "no such project" / "no shot plan yet" (the ValueError); 1 on a
#   database error (SQLAlchemyError or OSError), as report.py
def run_checks(shot: Shot, scene: Scene, description: FrameDescription, judgement: Judgement,
               extraction: Extraction, *, on_screen: tuple[str, ...] = ()
               ) -> tuple[tuple[CheckResult, ...], Verdict, dict[str, Position]]: ...   # pure
#   T080: `on_screen`, the people the prompt drew; audit_frame passes `visible_characters(shot, screenplay,
#   extraction)` (storyboard.md §3.1), imported where it is called: T026's renderer modules in app.storyboard
#   import app.verify, so a module-level import would be a cycle once they land
async def audit_frame(model: NebiusChatModel, frame: RenderedFrame, shot: Shot, screenplay: Screenplay,
                      extraction: Extraction) -> Audit: ...

# app/verify/loop.py (T021)
async def render_until_accepted(model: NebiusChatModel, renderer: Renderer, shot: Shot, screenplay: Screenplay,
                                extraction: Extraction, *, width: int, height: int, max_renders: int = MAX_RENDERS,
                                first_attempt: int = 1,
                                log: Callable[[Audit], Awaitable[None]],
                                on_state: Callable[[FrameState, int], Awaitable[None]] | None = None) -> FrameOutcome: ...
#   on_state(state, attempt) is awaited on every §5 transition, before the work of the new state:
#   RENDERING and AUDITING for each attempt, then the terminal state. It is how web.md's `frames` rows
#   show a frame in progress (added with docs/design/web.md, 2026-09-30).
#   first_attempt (T021): attempts run first_attempt .. first_attempt + max_renders − 1, each seeded
#   seed_for(shot, attempt). The storyboard passes 1 and 3; "Try another render" on a frame withheld at
#   attempt n passes n + 1 and 1: one more audited attempt, reproducible like the rest.
#   Order, a contract: each attempt's `log(audit)` is awaited before the next on_state, so the terminal
#   state's writer can read the audit that decided it. An audit ERROR withholds at once (no retry).
#   A renderer exception is re-raised after on_state(FAILED, attempt): the caller fails its job.
MAX_RENDERS = 3   # the default; callers pass Settings().render_max_attempts (T071)

# app/core/config.py (T071)
render_max_attempts: int = Field(default=3, ge=1, le=3)   # RENDER_MAX_ATTEMPTS: a full loop's attempts per frame
#   app/comic/job.py drops its own MAX_RENDERS for it; app/frames/views.frame_view takes it as
#   `max_renders: int` (the projects router passes the setting) and shows max(max_renders, attempt)

# The renderer the frame writers need: a Renderer that remembers where it stored each attempt (T021).
class SupportsAsset(Protocol):
    @property
    def asset(self) -> str: ...                   # the attempt's Storage path, frames/<…>.png (read-only: a frozen dataclass fits)
class RecordingRenderer(Renderer, Protocol):
    def record(self, shot: tuple[int, int], attempt: int) -> SupportsAsset: ...
    # recorded before render() returns, so a lookup after it never misses; FalRenderer
    # (app/storyboard/fal.py, its RenderRecord has .asset) and T062's SketchRenderer are both one
```

**Audit log table** (`frame_audits`, T021, migration `0004`, `lock_down` like every table, deploy.md
§6; one row per audited attempt, passed or not):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, primary key | |
| `project_id` | uuid, FK `projects` on delete cascade | so a frame's attempts across its jobs (the upload's, each retry's) are one indexed read |
| `job_id` | uuid, FK `jobs` on delete cascade | the job that ran the attempt |
| `target` | text, CHECK `storyboard`/`comic`, default `storyboard` | which frame was audited: the storyboard's 1280 × 720 frame or a comic panel at its rect (T064, migration `0005`, comic.md §4a). Rows written before 0005 are `storyboard` |
| `scene_index`, `shot_number`, `attempt` | int, `attempt ≥ 1` | **unique** `(project_id, target, scene_index, shot_number, attempt)` (`(project_id, scene_index, shot_number, attempt)` until 0005), which is also the read's index |
| `seed` | **bigint** | `seed_for` is an unsigned 32-bit value: it overflows `integer` |
| `frame_asset` | text | the attempt's Storage path; never sent to the web (only a `frames` row's accepted asset is, as a signed URL) |
| `description`, `judgement` | jsonb, null | null on an ERROR audit that didn't get that far |
| `checks` | jsonb list of `{check, severity, ok, detail}` | `[]` on an ERROR audit |
| `positions` | jsonb `{character: position}` | `{}` on an ERROR audit |
| `verdict` | text, CHECK `pass`/`warn`/`fail`/`error` | |
| `models` | jsonb list of model ids | |
| `prompt_tokens`, `completion_tokens` | int | `Audit.usage`'s two counts (reasoning tokens are inside completion's) |
| `created_at` | timestamptz, `clock_timestamp()` | |

Nothing in it quotes more of the script than the shot's own `source`. A frame's **last audit** is its
row with the greatest `attempt`. Every read for the storyboard (`audits_of`, `withheld_check`,
`FrameView.audits`) filters `target = 'storyboard'`; the comic job's rows are read by nothing in the
web app yet (comic.md §4a).

**T021's writers** (`app/frames/writer.py`). Each write is its own short transaction (a frame's state
must be visible while its job still runs). The `frames` row is written by exactly these hooks and the
restart sweep.

```python
class FrameWriter:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], project_id: uuid.UUID, job_id: uuid.UUID,
                 *, target: AuditTarget = AuditTarget.STORYBOARD): ...   # AuditTarget(StrEnum): STORYBOARD, COMIC (T064)
    async def log(self, audit: Audit, frame_asset: str) -> None: ...      # one frame_audits row, with the writer's target
    #   on_frame below raises ValueError on a COMIC writer: a comic panel has no frames row
    async def on_frame(self, shot: tuple[int, int], state: FrameState, attempt: int, asset: str | None) -> None: ...
    #   upserts the frames row and sets every column on every write: state, attempt, job_id; asset only
    #   for PASSED/WARNED, else null; withheld_check only for WITHHELD (from the frame's last audit: its
    #   first failed hard check in Check order, lower case, or "audit_error" when its verdict is ERROR),
    #   else null; failure "render" only for FAILED, else null. No column outlives its state.

def frame_hooks(writer: FrameWriter, renderer: RecordingRenderer, shot: tuple[int, int]
                ) -> tuple[Callable[[Audit], Awaitable[None]], Callable[[FrameState, int], Awaitable[None]]]: ...
#   (log, on_state) for render_until_accepted: log(audit) → writer.log(audit, renderer.record(shot, audit.attempt).asset);
#   on_state(state, attempt) → writer.on_frame(shot, state, attempt, renderer.record(shot, attempt).asset
#   if state is PASSED or WARNED else None). The one adapter: the retry uses it, and so does T026's
#   build_storyboard for its log and on_frame (storyboard.md §4), so the asset rule is stated once.
```

**The architecture check** (T062, `app/frames/check.py`): the loop end to end with no image model.

```python
class SketchRenderer:   # a RecordingRenderer
    def __init__(self, store: AssetStore): ...
    async def render(self, shot, attempt, seed, width, height) -> RenderedFrame: ...
    #   draws with Pillow at exactly width × height from random.Random(seed): a horizon, one to three
    #   figures, a box, pencil grey on paper; PNG with no metadata, so the same seed is the same bytes;
    #   stores it at frames/<sha256 of the PNG>.png (content address, put is idempotent) and records it
async def run_check(sessions, store: AssetStore, model: NebiusChatModel, project_id: uuid.UUID,
                    *, bucket: str, shots: int = 3) -> uuid.UUID: ...   # → the throwaway project's id
```

- **It never touches the project it is given.** It copies that project's screenplay, extraction and
  plan, and its `owner` and `pdf_path` (the same Storage object: nothing is re-uploaded), into a **new
  project** titled "{title} (architecture check)", with one
  `storyboard` job `DONE` (so the list shows it planned), and works only there. Its frames, a sketch
  that passes included, belong to that copy; delete the copy to discard them. A sketch the audit
  passes is a test artefact, not evidence of grounding: it shows the path an accepted frame takes.
- **It refuses** (`CheckRefused`, before writing anything) unless `bucket`, the store's bucket, which
  the command passes from `SUPABASE_STORAGE_BUCKET`, is `panelwise-dev` (the dev bucket, never the
  hosted demo's), and unless the source project exists and has a plan.
- For the copy's first `shots` shots **in plan order**, one `frame_attempt` job (`RUNNING` at stage
  `rendering`, `DONE` after the last shot, `FAILED` if a render raises) runs `render_until_accepted`
  with the **real** audit (`Tier.VISION` describer, `Tier.REASONING` judge: the only spend, two calls
  per attempt) through `frame_hooks`. `python -m app.frames.check <project-id> [--shots N]` builds
  the store and model from settings, calls `run_check`, and prints each shot's states and verdicts
  and the copy's id. Most sketches end `withheld` after three attempts: the path a wrong frame takes.

**The re-audit** (T071, `app/verify/reaudit.py`): today's audit run again on drawings already made,
so a change to the audit is measured without drawing anything.

```python
@dataclass(frozen=True) class Reaudit: shot: tuple[int, int]; attempt: int; target: str; before: Verdict; after: Verdict; failed: tuple[Check, ...]
async def reaudit(sessions, store: AssetStore, model: NebiusChatModel, project_id: uuid.UUID,
                  *, target: AuditTarget | None = None, limit: int | None = None) -> list[Reaudit]: ...
def summary(rows: Sequence[Reaudit]) -> str: ...   # pure: before → after counts of pass/warn/fail/error, and each hard check's count after
```

- **It writes nothing**: no row, no Storage object. It reads the project's plan and its
  `frame_audits` rows (one `target`, or both; in `(target, scene_index, shot_number, attempt)` order;
  the first `limit`), reads each row's `frame_asset` from Storage, and calls `audit_frame` with that
  PNG (its width and height from the image, the row's seed) against the row's shot.
- **The only spend** is the audit's Token Factory calls per row (the describer and the judge, and
  since T095–T104 the agents' vision questions); nothing is drawn.
  `python -m app.verify.reaudit <project-id> [--target storyboard|comic] [--limit N]` prints one
  line per row (`6.4 a1 comic: fail → pass`) and `summary`. A row whose asset is gone is reported
  and skipped, never a crash.

### T094, T095 contracts

```python
# app/core/config.py
class Settings: audit_withhold_checks: str = "all"     # T094: "all", "" or a comma list of Check values
def withholding(settings: Settings) -> frozenset[Check] | None: ...   # None for "all"; ValueError for a name that is no hard check

# app/verify/loop.py
async def render_until_accepted(..., withholding: frozenset[Check] | None = None) -> FrameOutcome: ...
#   T094: apply_ladder before log: a FAIL whose failed hard checks are all off `withholding` is logged and accepted as WARN;
#   None keeps today's rule (every hard check withholds). build_storyboard, run_job, run_comic_job and
#   run_attempt pass it through; the API passes withholding(settings).

# app/verify/model.py
class Check(StrEnum): ... DRAWN_SEX = "drawn_sex"         # T095, hard; appended last (enum order is report order)
_SEVERITY[Check.DRAWN_SEX] = Severity.HARD
@dataclass(frozen=True) class PersonSeen: person: int; character: str; sex: str   # T095: male, female or unclear
@dataclass(frozen=True) class Audit: ...; seen: tuple[PersonSeen, ...] = ()               # T095

# app/verify/schema.py
class PersonCheck(BaseModel): sex: Literal["male", "female", "unclear"]

# app/verify/audit.py
SEX_AGENT_PROMPT: str      # the fixed question above, verbatim in the code
async def check_person(model: NebiusChatModel, image: str, description: FrameDescription, index: int) -> tuple[PersonCheck, ChatResult]: ...  # Tier.VISION; image a data URL, encoded once
def matched_people(shot, description, judgement, extraction, ages=None) -> dict[int, str]: ...   # pure: who run_checks accepts as which character
def shot_sexes(shot, screenplay, extraction, sex_of) -> dict[str, str]: ...   # character_sex per shot person, passed in
def apply_ladder(audit: Audit, withholding: frozenset[Check] | None) -> Audit: ...   # T094: off-ladder hard checks become soft; FAIL -> WARN when none is left
def run_checks(..., seen: Sequence[PersonSeen] = (), sexes: Mapping[str, str] | None = None) -> ...   # T095: DRAWN_SEX

# app/frames/model.py, migration 0007
FrameAuditRow.seen: Mapped[list[dict] | None]   # JSONB, nullable: older rows have none (recheck: no DRAWN_SEX)
```

The card names `drawn sex` like any check (`document.py`'s check names). `report.py` counts it with
the others; `recheck` reads `seen` from the row.

### T097 contracts

```python
# app/verify/model.py
type HeadBox = tuple[float, float, float, float]   # x0, y0, x1, y1: fractions of the frame's width and height, from its top-left
@dataclass(frozen=True) class HeadSeen: person: int; character: str | None; box: HeadBox   # T097: character None for a person matched to no one
@dataclass(frozen=True) class Audit: ...; matched: Mapping[int, str] = field(default_factory=dict)   # T097: matched_people's answer, kept (not stored)
                                       heads: tuple[HeadSeen, ...] = ()                              # T097: the head agent's kept answers

# app/verify/schema.py
class HeadAnswer(BaseModel): person: int; visible: bool; x0: float; y0: float; x1: float; y1: float
class HeadCheck(BaseModel): heads: list[HeadAnswer]

# app/verify/audit.py
HEAD_AGENT_PROMPT = (
    "You look at the people in a storyboard drawing and say where each listed person's head is: "
    "the box around the head, from the top of the hair to the chin, as fractions of the image's "
    "width and height from its top-left corner (0 to 1). Set visible to false when the head is out "
    "of frame or hidden. Answer for every person listed, by their number, and only for them."
)
def heads_seen(answer: HeadCheck, people: int, matched: Mapping[int, str]) -> tuple[HeadSeen, ...]: ...   # pure: the keep rule above, in person order
async def find_heads(model: NebiusChatModel, frame: RenderedFrame, audit: Audit) -> Audit: ...
#   one Tier.VISION question (max_tokens=4096) on audit.description's people; returns the audit with heads, usage and models
#   added, verdict and checks untouched; no description or no people: the audit unchanged, no call; LLMError or
#   ValidationError: logged ("head agent on shot %s attempt %d failed: %s"), the audit unchanged; anything else raises

# app/verify/loop.py
async def render_until_accepted(..., heads: bool = False) -> FrameOutcome: ...
#   T097: after apply_ladder, an accepted audit (PASS or WARN) gets find_heads before log; never on a FAIL or ERROR.
#   run_comic_job passes heads=True; build_storyboard, run_job and run_attempt keep the default.

# app/frames/model.py, migration 0010_audit_heads (down_revision 0009, T104's audit_layout)
FrameAuditRow.heads: Mapped[list[dict] | None]   # JSONB, nullable: [{"person": 0, "character": "NANDI" | null, "box": [x0, y0, x1, y1]}]; older rows and storyboard rows have none
```

### T099 contracts

```python
# app/verify/model.py
@dataclass(frozen=True) class PersonFound: character: str; person: int | None; reason: str   # T099: one answer
@dataclass(frozen=True) class Audit: ...; found: tuple[PersonFound, ...] = ()                # T099

# app/verify/schema.py
class Presence(BaseModel): person: int | None; reason: str

# app/verify/audit.py
PRESENCE_AGENT_PROMPT = (
    "You check whether a storyboard drawing shows one character from a screenplay. You get what the script says about the character, the shot's text, and a numbered list of the people a describer saw in the drawing. Look at the drawing and answer which numbered person is that character, or null when none of them can be. Pick a person when the drawing fits what the script says: their age group, their sex if the script gives it, and what the shot has them doing. A detail the drawing leaves out (a hat, a colour) doesn't rule anyone out. A person who is plainly someone else in the shot text (a bystander, a vendor, another character) is not this character. Give a short reason."
)   # verbatim; written as one string here, split across lines in the code
async def find_character(model: NebiusChatModel, image: str, character: str, shot: Shot,
                         screenplay: Screenplay, extraction: Extraction,
                         description: FrameDescription) -> tuple[Presence, ChatResult]: ...
#   Tier.VISION, max_tokens=4096; the user text is "The character:", then the lines of
#   _sexed(_quoted(extraction, EntityKind.CHARACTER, (character,)), (character,), screenplay, extraction)
#   (the judge's own helpers, imported from app.verify.prompts on purpose), "", "Shot text:",
#   shot.source, "", "People in the drawing:", "[i] position: appearance" per person or "none";
#   then the image (a data URL, encoded once per attempt)
async def _ask_sexes(model, image: str, description, matched, sexes, chats) -> ...   # T099: takes the
#   data URL audit_frame encoded, not the PNG bytes
#   (T102 replaces this signature and the order below: see T102 contracts)
def present_characters(on_screen: Sequence[str], found: Sequence[PersonFound], accepted: Mapping[int, str],
                       description: FrameDescription, ages: Mapping[str, int] | None) -> frozenset[str]: ...
#   pure: the on_screen characters an answer finds: 0 <= person < len(description.people), not a key of `accepted`
#   (matched_people), and no age_contradicts(years, described_age(appearance))
def run_checks(..., found: Sequence[PersonFound] = ()) -> ...   # T099: NO_CHARACTER passes when
#   any on_screen character is matched (as before) or in present_characters(...)
#   audit_frame: encodes the PNG once; after the judge succeeds with _calls_each_once true, the sex
#   agent first, then, when on_screen is not empty and matched_people accepts none of it,
#   find_character for each on_screen character at once; a failed one (LLMError or
#   ValidationError) is logged and left out; the answers are Audit.found; tokens and model count

# app/frames/model.py; migrations/versions/0008_audit_found.py: revision "0008", down_revision "0007",
#   op.add_column("frame_audits", sa.Column("found", JSONB(), nullable=True)); downgrade drops it
FrameAuditRow.found: Mapped[list[dict] | None]   # JSONB, nullable: older rows have none (recheck: the judge alone)
```

`recheck` reads `found` from the row (`[{"character", "person", "reason"}]`) and passes it on.
`render_spec` and `_quoted`/`_sexed` are unchanged; `find_character` imports them from
`app.verify.prompts`. `app/verify/__init__.py` is unchanged: the new names are imported from
`app.verify.model`, `app.verify.schema` and `app.verify.audit`, as T095's tests import theirs.

### T102 contracts

```python
# app/verify/audit.py
def found_people(on_screen: Sequence[str], found: Sequence[PersonFound], accepted: Mapping[int, str],
                 description: FrameDescription, ages: Mapping[str, int] | None) -> dict[str, int]: ...
#   pure: character -> person for each answer that passes the three tests, the first answer that
#   passes per character (an earlier null or out-of-range one is skipped); present_characters(...)
#   returns frozenset(found_people(...)), its signature unchanged
async def _ask_sexes(model, image: str, description, pairs: Sequence[tuple[int, str]], sexes, chats) -> ...
#   T102: takes (person, character) pairs instead of `matched`; keeps the pairs whose character is in
#   `sexes`, asks check_person once per distinct person (in person order), and returns one PersonSeen per
#   kept pair in the given order, each with its person's answer; a failed question drops that person's
#   pairs. audit_frame passes sorted(matched.items()) first (T095, as before), then, after the presence
#   agent, the found_people pairs sorted by person then character
# check_person: max_tokens 1024 -> 4096 (T095 and T102)
def run_checks(...) -> ...   # unchanged signature; DRAWN_SEX reads an answer when accepted.get(person)
#   == character (T095) or found_people(on_screen, found, accepted, description, ages).get(character)
#   == person (T102); the detail is T095's
#   audit_frame: Audit.seen = the T095 answers then the T102 answers; tokens and models count
```

No migration: the answers go in `frame_audits.seen` with T095's. `recheck` already passes the row's
`seen` and `found` to `run_checks`, so it decides T102 for free on rows written after it.

### T104 contracts

```python
# app/verify/model.py
class Check(StrEnum): ...; SPLIT_PANELS = auto(); DRAWN_TWICE = auto()   # T104, hard; appended last
@dataclass(frozen=True) class FrameLayout: panels: int; copies: tuple[tuple[int, int], ...]; reason: str   # T104
@dataclass(frozen=True) class Audit: ...; layout: FrameLayout | None = None                           # T104

# app/verify/schema.py
class Layout(BaseModel): panels: int; copies: list[list[int]]; reason: str

# app/verify/audit.py
LAYOUT_AGENT_PROMPT = (
    "You look at one storyboard drawing and a numbered list of the people a describer saw in it. Answer two things from the drawing alone. First, panels: 1 when it is one single picture, or the number of separate panels when it is laid out as a strip or grid of pictures side by side. Second, copies: the pairs of numbered people who are plainly the same person drawn more than once (the same face, hair, build and clothes, for example one person shown at two moments, or twice in one room), as [a, b] pairs; an empty list when everyone is a different person. People who merely look alike in a sketchy style (two men in suits, two children) are not copies unless their face, hair and clothes match. Give a short reason."
)   # verbatim; split across lines in the code
async def check_layout(model: NebiusChatModel, image: str,
                       description: FrameDescription) -> tuple[Layout, ChatResult]: ...
#   Tier.VISION, max_tokens=4096; user text "People in the drawing:" then "[i] position: appearance" per person
def frame_layout(layout: Layout, people: int) -> FrameLayout: ...
#   pure (§3, the answer cleaned): panels max(1, panels); copies: each pair of exactly two ints, a != b,
#   both 0 <= i < people, as sorted (a, b), once, in sorted order; [i, i], out-of-range, short or long
#   pairs dropped
_SEVERITY[Check.SPLIT_PANELS] = Severity.HARD; _SEVERITY[Check.DRAWN_TWICE] = Severity.HARD   # T104
def run_checks(..., layout: FrameLayout | None = None) -> ...   # T104: SPLIT_PANELS when panels > 1;
#   DRAWN_TWICE when panels == 1, per pair, unless both people are in accepted ∪ invert(found_people(...))
#   (person -> character); details joined by "; "; both pass with layout None
#   audit_frame: after the T102 questions, when the judgement is well formed and
#   len(description.people) >= 2, check_layout once; a failed one (LLMError or ValidationError) is
#   logged and leaves layout None; Audit.layout; tokens and model count

# app/frames/model.py; migrations/versions/0009_audit_layout.py: revision "0009", down_revision "0008",
#   op.add_column("frame_audits", sa.Column("layout", JSONB(), nullable=True)); downgrade drops it
FrameAuditRow.layout: Mapped[dict | None]   # {"panels", "copies", "reason"}; NULL: not asked or older
```

`recheck` reads `layout` from the row and passes it on (NULL: `SPLIT_PANELS` and the layout's copies pass, as before T104; T124's described-alike pairs are still checked).

### T124 contracts

```python
# app/verify/audit.py
ALIKE_OVERLAP = 0.5   # T124: measured, eval/measurements/t124/
_ALIKE_STOP_WORDS = frozenset("a an the with and of in on at wearing holding her his their to is".split())
def described_alike(description: FrameDescription, known: Collection[int], extras: Collection[int] = (),
                    overlap: float = ALIKE_OVERLAP) -> tuple[tuple[int, int], ...]: ...
#   pure: every pair (a, b), a < b, of description.people, not both in `known` and not both in
#   `extras` (a character and an extra still pair), whose appearance
#   words overlap >= overlap; words: re.findall(r"[a-z]+", appearance.lower()) minus the stop words;
#   overlap |A & B| / |A | B| (0.0 when both are empty); pairs in sorted order
def run_checks(...) -> ...   # T124: unless layout.panels > 1 (SPLIT_PANELS), DRAWN_TWICE also for each
#   pair of described_alike(description, known, extras) not in layout.copies (layout None: none),
#   detail f"person {a} ({position}, {appearance}) and person {b} ({position}, {appearance}):
#   described alike, one of them no character"; known = T104's accepted ∪ found people; extras = the
#   scripted extras (a no-character call whose support passes every UNSCRIPTED_PERSON test);
#   layout pairs keep T104's veto (known only)
```

`recheck` decides it again for free on every stored row with a description (the layout column isn't
needed). The hosted ladder (`render.yaml`, deploy.md §6) stays
`drawn_sex,no_character,split_panels`: `drawn_twice` warns (§3, 2026-10-20).
`FrameWriter.log` writes it. The web shows a check's name as it shows every check's (no new copy).

### T109 contracts: the describer's answer capped in its grammar

**Why** (measured 2026-10-17, §9 T109): on Super VL the describer sometimes repeats itself at
temperature 0 until it hits `max_tokens=4096`: the same object again and again ("picture frame",
"ceiling light", "streetlight": up to 40 times with 3 names), or one string that never ends
("B. B. B. …" for a boat's lettering, "1000…" on a bicycle). The answer is cut off mid-JSON, the
repair turn resends it and loops the same way, and the attempt is an `ERROR`: withheld, and on the
hosted demo a redraw. Seen on 7 of the 109 labelled frames (findings § U8) and on rooftop-tomatoes'
comic 6.1; 6 of those 7 and comic 6.1 loop again when asked (§9 T109). The seventh,
sipho-and-siphokazi 2.1, answered in 422 tokens on all three asks: its stored `ERROR` was not
reproduced, its cause is unknown, and T109 is not claimed to remove it.

**The change:** the describer's call sends its schema with length limits in `response_format` only.
Token Factory's strict decoding obeys `maxItems` and `maxLength`, so a looping list or string stops
at its limit and the JSON closes. The prompt keeps the schema text it has today, so an answer that
stays inside the limits is the same answer as before (10 of 10 control frames byte for byte). The
limits sit above every honest answer stored (§9 T109) and keep the whole answer under 4,096 tokens:

```python
# app/verify/schema.py
@dataclass(frozen=True) class DescriptionLimits: people: int; objects: int; text: int; text_chars: int;
                                                 appearance_chars: int; object_name_chars: int;
                                                 signature: int; signature_chars: int
DESCRIPTION_LIMITS = DescriptionLimits(people=24, objects=40, text=40, text_chars=100,
                                       appearance_chars=200, object_name_chars=60,
                                       signature=5, signature_chars=60)
def description_grammar(limits: DescriptionLimits = DESCRIPTION_LIMITS) -> dict[str, Any]: ...
#   pure: a deep copy of FrameDescription.model_json_schema() with
#   properties.people.maxItems, properties.objects.maxItems, properties.text.maxItems,
#   properties.text.items.maxLength, properties.signature_text.maxItems (`signature`),
#   properties.signature_text.items.maxLength (`signature_chars`),
#   $defs.SeenPerson.properties.appearance.maxLength,
#   $defs.SeenObject.properties.name.maxLength set from `limits`; nothing else changes
#   (FrameDescription itself is unchanged: validation and the prompt's schema text stay as they are)

# app/verify/audit.py
async def describe_frame(model, png) -> tuple[FrameDescription, ChatResult]: ...
#   T109: structured_chat(..., FrameDescription, Tier.VISION, max_tokens=4096,
#   grammar=description_grammar()); everything else as before
def run_checks(...) -> ...   # T109: a list that reaches its limit may have been cut, so what lay past
#   it was never checked. len(description.people) >= DESCRIPTION_LIMITS.people adds the
#   UNSCRIPTED_PERSON detail f"{n} people described, the limit: any more were not checked";
#   len(description.objects) >= DESCRIPTION_LIMITS.objects adds the BACKGROUND_OBJECT detail
#   f"{n} objects described, the limit: any more were not checked". Each joins that check's other
#   details as today; the text list's limit adds nothing (TEXT_IN_FRAME is soft, and what was read stays)
```

**A list at its limit is never passed silently** (Non-negotiable I): the describer can't say whether
it stopped at 24 people because there were 24 or because the grammar cut it, and a 25th person the
judge never sees could be unscripted. So a frame described at the limit fails `UNSCRIPTED_PERSON`
(hard; on the hosted ladder it warns, and the card names it), whatever the judge called the 24.
No stored answer reaches either limit (DeepSeek: at most 21 people and 32 objects in 1,352), so the
rule only meets a loop or a real crowd of 24 or more, which the audit can't check person by person
anyway. Objects at 40 fail `BACKGROUND_OBJECT` (soft) the same way.

The judge and the agents are unchanged: none of them was seen to loop (their answers are short,
and a failed agent question is logged, never an `ERROR`). A looping list now arrives cut to its
limit (40 "ceiling light" objects): the judge calls each, as it would any description, and the
limit rule above names it. A looping string arrives cut to 100 characters, which is lettering
(`TEXT_IN_FRAME`, soft).

## 7. Structure

| Path | New? | Responsibility | Task |
| --- | --- | --- | --- |
| `services/api/app/verify/{__init__,model,schema,prompts,audit}.py` | new | `describe_frame`, judge, checks, verdict | T020 |
| `services/api/app/verify/run.py` | new | live check: audit one PNG against one planned shot on the real account | T020 |
| `services/api/app/verify/loop.py` | new | render → audit → retry → state | T021 |
| `services/api/app/frames/{model,writer}.py` + migrations `0003` (`frames.failure`), `0004` (`frame_audits`) | new | `FrameAuditRow`, `FrameWriter`, `frame_hooks` | T021 |
| `services/api/app/frames/check.py` | new | `SketchRenderer`, `run_check`, `python -m app.frames.check` | T062 |
| `services/api/app/verify/{prompts,schema,audit,loop}.py`, `app/core/config.py`, `app/comic/job.py`, `app/frames/views.py`, `app/api/v1/{schemas,projects}.py` | changed | T071: `text` and the new `TEXT_IN_FRAME`, costume and structure exempt, signs may be dressing, `RENDER_MAX_ATTEMPTS` | T071 |
| `services/api/app/verify/reaudit.py` | new | `reaudit`, `summary`, `python -m app.verify.reaudit` | T071 |
| `services/api/app/verify/{model,audit}.py` | changed | `Check.BACKGROUND_OBJECT`, `named_in_scene`, the order in `run_checks` | T083 |
| `services/api/app/verify/recheck.py` | new | `recheck`, `accepted_shots`, `python -m app.verify.recheck` | T083 |
| `services/api/app/verify/audit.py` | changed | `shot_action_text`, `_PERSON_PRONOUNS`, two person-support rules in `run_checks` | T084 |
| `services/api/app/verify/{audit,recheck}.py`, `app/storyboard/prompt.py` | changed | `described_age`, `age_contradicts`, `inside_vehicle`, `part_of_vehicle`, `shot_ages`, `run_checks(ages=)`, unheld food as `BACKGROUND_OBJECT`; `introduced_years` | T086 |
| `services/api/app/verify/audit.py` | changed | `_STORY_OBJECTS`, `_SEVERITY[TEXT_IN_FRAME]` soft, object failures routed to `BACKGROUND_OBJECT` | T089 |
| `services/api/app/verify/{model,schema,audit,loop}.py`, `app/frames/{model,writer}.py`, migration `0010_audit_heads`, `app/comic/job.py` | changed / new | `HeadSeen`, `Audit.matched`, `Audit.heads`, `HeadCheck`, `HEAD_AGENT_PROMPT`, `heads_seen`, `find_heads`, `render_until_accepted(heads=)`, `FrameAuditRow.heads`; the comic job asks for heads | T097 |
| web: the audit log view (per shot: attempts, verdicts, checks) | new | built to web.md §4.4 step 5 | T061 |
| `services/api/app/verify/{model,schema,audit,recheck}.py`, `app/frames/{model,writer}.py`, migration `0008_audit_found` | changed | `PersonFound`, `Presence`, `PRESENCE_AGENT_PROMPT`, `find_character`, `present_characters`, `run_checks(found=)`, `frame_audits.found` | T099 |
| `services/api/app/verify/audit.py` | changed | `found_people`, `_ask_sexes(pairs)` one question per person, `check_person` at 4,096 tokens, `run_checks`' `DRAWN_SEX` for a found person, `audit_frame` asks after the presence agent | T102 |
| `services/api/app/verify/{model,schema,audit,recheck}.py`, `app/frames/{model,writer}.py`, migration `0009_audit_layout` | changed | `Check.SPLIT_PANELS`, `Check.DRAWN_TWICE`, `FrameLayout`, `Layout`, `LAYOUT_AGENT_PROMPT`, `check_layout`, `frame_layout`, `run_checks(layout=)`, `frame_audits.layout` | T104 |
| `services/api/app/verify/audit.py` | changed | `ALIKE_OVERLAP`, `described_alike`, `run_checks`' second `DRAWN_TWICE` source | T124 |
| `services/api/app/verify/{schema,audit}.py`, `app/llm/structured.py` | changed | `DescriptionLimits`, `DESCRIPTION_LIMITS`, `description_grammar`, `describe_frame` sends it; `structured_chat(grammar=)` (llm.md §6) | T109 |
| `services/api/tests/{verify,frames}/` | new | §9 | T020, T021, T062 |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Which failures withhold (T094; Tumo, 2026-10-13) | a ladder setting, measured back in rule by rule (empty on the hosted demo at first); the hosted demo withholds `drawn_sex,no_character,split_panels` (render.yaml), every other hard check warns; `all` stays the code default | every hard check (before): market-day 0 of 15 with most drawings right; dropping the audit: the card's notes and `recheck` are how the rules come back |
| A drawn character's sex (T095) | a vision question about the one matched person, only when the script gives a sex, `unclear` passing | the judge alone (T082 tells it the sex; it still matched the girls drawn as boys); asking the describer for every person's sex (more tokens on people nobody checks, and a describer told to look for sex starts guessing it); age bands from the same answer (15 of 175 called men in their 50s old) |
| Where a head is (T097) | one vision question per comic panel, on the accepted attempt only, boxes as fractions, never a verdict | face detection (another model and dependency for a box the vision model already gives, measured on the drawings); the describer giving boxes (it is blind and general; a longer schema on every attempt, storyboard frames too); asking on every attempt (tokens on frames thrown away); an anatomy rule from the same question (it missed a three-armed man twice and miscounted limbs: §3) |
| A character the judge didn't match (T099) | a vision question per drawn character, only when the judge matched none of them; it counts for `NO_CHARACTER` alone | a judge sentence (the judge already gets the same lines and cites them while calling the person no one; and it can't be measured free); code taking a stranger's support that names a drawn character as a match (free, but by the stored supports it finds about 8 of the 23, and none where the judge cited nothing); making the found person a full match (it would excuse `UNSCRIPTED_PERSON` and start `DRAWN_SEX` questions on a second opinion's say-so; measured only for presence). **T102** adds only the `DRAWN_SEX` question, measured: 36 found people asked, 2 flagged, both real, 0 false alarms |
| A frame in panels, or one person drawn twice (T104; L015, L022, 2026-10-16) | one vision question on a frame with two or more people; `SPLIT_PANELS` on panels > 1; `DRAWN_TWICE` on a copy pair in one picture unless the two are accepted as two different characters | rewording every style's positive words (fal's klein takes no negative prompt; L015 parked it: it changes every drawing); a code test on the describer's text (it describes the copies differently: "short dark hair" against "shoulder-length wavy hair" for lighthouse 4.2's two women); asking the describer (a describer told to look for copies starts finding them, as T095 found for sex); copies in a split frame (the split's own figures; `SPLIT_PANELS` already names it) |
| A copy the layout agent argues apart (T124; 2026-10-19) | the describer's own words: a pair described alike (word overlap ≥ 0.5), not both known, fails `DRAWN_TWICE`; it warns (on the hosted ladder for one night, off again 2026-10-20: it withheld right frames) | withholding on `UNSCRIPTED_PERSON` (it catches 9 of 10 copies, but flags 11 of 40 right frames on the 109 labelled: a judge that misses a drawn cast); a stricter layout prompt (another paid question, and it already sees the matching words); a threshold of 0.8 (no false flag anywhere, but 3 of 10 copies) |
| A found person's sex (T102; L022, 2026-10-16) | T095's question on each person `found_people` gives for a character the script sexes; `DRAWN_SEX` fails on the other sex | the presence agent's own answer refusing a person of the other sex (its prompt already says "their sex if the script gives it", and it still found an old woman for Mr. Fortuin); a full match (excuses `UNSCRIPTED_PERSON`, T099's reason) |
| Who sees the image | a vision model, blind to the shot | the judge looking at the image itself: no Token Factory Nemotron accepted images until Super VL (U7, U8), and since T105 the split stays because a describer blind to the shot can't simply agree; telling the describer what to expect: it would agree |
| Who judges | Nemotron (reasoning tier) + code | the vision model judging itself: it already saw the image without the spec, which is the point (it was also not NVIDIA's until T105) |
| Countable checks | code | the judge counting: code is exact and free |
| Where a comic panel's attempts are logged (T064) | `frame_audits` with a `target` column | a second `comic_audits` table: the same columns twice, and two writers to keep in step; logging nothing: every attempt is kept (§4), a comic panel's too |
| "Supported by the script" | only with a verbatim quote, verified in code | trusting the judge's say-so: the same failure the grounding filter exists to stop |
| After the last failed attempt | withhold the frame | show the "best" failed frame: that shows something unscripted |
| Audit error | withhold | pass unaudited: the one outcome this module exists to prevent |
| Re-render feedback | a new seed | feeding the failed checks into the prompt: SDXL-Turbo at cfg 1 ignored negative prompts (FrameFlow's own config note), and fal's FLUX.2 [klein] takes no negative prompt (L015) |
| Hard vs soft | hard = would show something unscripted; soft = quality | failing on every soft miss: burns renders on lighting a storyboard can live with |
| Text in the frame (T071; Tumo, 2026-10-10) | fail only legible words that aren't the script's own (the shot's `source` or the scene's location) | any writing-like mark fails (before T071): 237 of 249 failed audits on 2026-10-10 had text, a sign naming the very office the scene is in among them, so almost nothing could pass; ignoring only unreadable marks: the office's own sign would still fail; counting the time of day as script words: a painted "NIGHT" would pass |
| Costume and the place's structure (T071) | never an unscripted object when not held, and the describer stops listing them | trusting the judge on each jacket and chimney: on 2026-10-10 it called a chest pocket, a hat and jackets unscripted; a held one is still checked (a held object is a story choice) |
| Attempts per frame (T071) | the setting `RENDER_MAX_ATTEMPTS`, 1 to 3, default 3 | a constant 3: when failures are systematic, two of every three drawings buy another FAIL; more than 3: the same spend, faster |
| A wrong sex or look (T080) | the judge refuses the match, as for a wrong age | a code check on the describer's words ("a boy"): the describer's phrases vary, and matching them to "she" or "braids" is guessing |
| No one in frame (T080) | the hard `NO_CHARACTER`, against the people the prompt drew | `MISSING_CHARACTER` made hard: a shot of two where one is drawn would be withheld for a framing choice; against `shot.characters`: a planner character no covered line puts on screen was never drawn, so every attempt would fail |
| A child drawn as an adult (T072) | the judge refuses the match when the apparent age plainly contradicts the character's quoted age, so the person is unscripted | a new `AGE` check in code: the describer's age is a phrase, and matching it to `(10)`, `(70s)` or "old" in code is guessing; leaving it to portraits (T025): T025 waited on the renderer (and was cut 2026-10-19), and 14 of 27 labelled frames (eval.md §6a.2) drew the wrong age |
| A rooftop (T106) | the describer's rule: open to the sky is `exterior`, even with the sky left blank; `interior` only when walls and a ceiling close it in; else `unclear` | a code exception for `ROOF` in the heading (it would pass a roof drawn indoors); dropping `SETTING` to soft (it catches real INT/EXT swaps: verify.md §8, T071) |
| A signature (T072, T077, T107; Tumo, 2026-10-11) | the soft `SIGNATURE` check (T077): logged and shown, the frame `WARN`; since T107 its letters are never `text`, readable or not (both checks are soft, so a frame's verdict is the same either way; what changes is that a scrawl isn't reported as unscripted lettering). On eval.md §6a's 27 labelled frames this passes 2 that Katlego labelled bad for their signature (one also had a second kite the describer missed): by this decision a signature is no grounding failure, so those labels count the signature as a note | a hard fail (T072): on 2026-10-11, re-judging the same stored drawings, it withheld 4 more of the-red-kite's 22 klein frames (6 accepted with T077, 2 without) and 1 of its 21 schnell frames, each otherwise right, and a mark in a corner is no character, prop, line or event; T071's rule alone (no flag): the flag stays, so a reviewer sees the mark; cropping the border to remove it: halved signatures in a 2026-10-10 experiment, and is renderer post-processing, after the renderer decision |
| A part of a prop (T078) | code: the prop's head noun right before the part's own word, a prop of this shot, no copy word, never an animal, vehicle, weapon or food; the judge's call doesn't matter | the judge alone (it called a kite string unscripted 3 times in 27 labelled frames); a shared word (my first draft matched `coil of wire` to `SPOOL OF BLUE STRING` through `of`, and `second kite` to `RED KITE`); a judge prompt saying everyday things are set dressing (2026-10-11: no labelled good frame gained, and a grown man for Lerato passed). Measured on the saved judgements of three runs over the 27 labelled frames: 0, 1 and 2 good frames gained, no labelled-bad frame passing |
| Drawing marks (T078) | the describer leaves them out | a code list of mark words: the describer's names vary; the judge: it called "pencil shading" unscripted |
| Ordinary things in the place (T072) | the judge is told what set dressing covers; code still needs the heading's words as support | exempting more categories in code (as T071 did for costume and structure): weather is `nature` too, and a lightning bolt is an event the script must have |
| Things the scene names (T083) | code: the object's noun or its whole's noun in the scene's action text, for the never-set-dressing categories only | the judge's label alone (it called the harbour's boats dressing 31 times); every category (it excused "small pills", "power lines", "tripod stand"); the shot's own text only: the boats a scene's first shot names belong to every shot of that harbour, and a later shot's own text often doesn't name them (11 objects excused against the scene's 32) |
| Background objects (T083; Tumo, 2026-10-11) | the soft `BACKGROUND_OBJECT`: shown, named, the frame `WARN` | hard as before: on 2026-10-11 it withheld 5 of sipho-and-siphokazi's 30 shots and 3 of the-red-kite's 21 for a pen, grass or a moon alone; painted text warning too (Tumo kept it hard: legible invented words on an accepted frame; reversed by T089, below) |
| A matched person's age (T086) | code compares the describer's age word with the introduction's years | the judge alone (T072's sentence): on the-bread-van it matched THEO (9) to adults 17 times; a finer scale (teen for 11 or 12, adult for 50s): the describer's words are coarse, so only plain contradictions count |
| A vehicle's parts inside it (T086) | code: part and interior words, inside a scene whose location is a vehicle | any `vehicle` object there (it passed a sailboat seen from a boat's cabin); the judge's call (it called the van's dashboard never-set-dressing) |
| Unheld food (T086; Tumo, 2026-10-12) | soft `BACKGROUND_OBJECT` whatever the judge called it | food as plain set dressing with the heading as support (it would pass silently: a cake at a birthday the script never had); hard as before (bread in a bakery failed 26 times) |
| Objects and lettering warn (T089; Tumo, 2026-10-12) | every object failure but an animal's or a weapon's, and `TEXT_IN_FRAME`, are soft and named on the card | strict as before (9 of 49 on lost-property, most for a misspelt LOST PROPERTY sign); all objects soft (the same counts, but a knife or a dog the script never gave would pass); asking klein for no lettering (a prompt change, fal money, and the script's own signs would go too); a setting for strict mode (one revert does it, no caller needs both) |
| A person's support (T084) | code: found in the shot's action text, with no `he`, `him` or `she` | any verbatim quote of the shot or of an in-shot entity, as before (2026-10-12: three strangers accepted on lost-property, excused by dialogue or a pronoun, and an old woman for Siphokazi on sipho-and-siphokazi); a person-noun list the support must contain (a vocabulary that never ends: "commuter", "busker", "courier"); telling the judge only (it can't be measured free, and code would still trust what it cites; a judge sentence is §10's open question) |
| A describer answer that loops (T109; measured 2026-10-17) | length limits in the decoding grammar only (`response_format`), the prompt's schema unchanged: 7 of 7 looping frames valid, 10 of 10 controls the same answer | the same limits in the schema the prompt shows too (7 of 7 valid, but 7 of 10 controls answered differently with no limit reached: a different prompt); `frequency_penalty` 0.5 (6 of 7, and fewer objects on every control: 15 → 8, 10 → 5, which changes what the judge checks); a prompt sentence asking for each object once (2 of 7); asking again at temperature 0.3 (2 of 7); a larger `max_tokens` (a loop fills any budget, and is billed for it); salvaging the cut-off JSON (it drops the rest of the answer silently: validation fixes shape, never content, llm.md) |
| Measuring a code-only audit change (T083) | `recheck`: today's checks on stored descriptions and judgements | `reaudit`: two Token Factory calls a drawing for a change that calls no model |
| Measuring an audit change (T071) | re-audit the drawings already in Storage (`reaudit`) | a new live run per change: the image spend again, and different drawings each time, so before and after aren't comparable |

**Accepted residual risk:** the audit can only judge what the describer reports. A person or object
the describer misses passes unseen. And since T072 the judge, not code, decides what a place
would hold: an object the script never names, called `set_dressing` with the heading's words,
passes (weather called dressing included). Code only stops a named prop and an unsupported one. T049
was to measure exactly this (recall on frames with a deliberately injected extra person or object);
it was deferred 2026-10-12, and the 109 hand-labelled frames measure it instead
(`eval/tools/score_labels.py`; the 2026-10-20 rescore, read on today's hosted ladder: 38 of 57 wrong frames
withheld, 1 of 40 right).

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none. Wording for the
pitch and README (SPEC.md): *"Nemotron 3.5 Super VL describes each frame; Nemotron Super judges it
against the script."*

## 9. How this is verified

- `run_checks` (pure) on hand-built descriptions and judgements: every check's pass and fail —
  including **two people called as one character** (the second is unscripted), a name not in the
  shot, a skipped or repeated index (`ERROR`), a held object or an animal called `set_dressing`,
  every `LIGHT` family and exemption, `unclear` framing — each
  severity's effect on the verdict, `support` quotes verified (and a fake support counted as
  unscripted), `INT_EXT` and `unclear` passing, positions derived.
- `audit_frame` with `httpx2.MockTransport`: the describer call carries the image and **no** shot
  details; the judge call carries the spec and the description; `VISION` then `REASONING` tiers.
- `render_until_accepted` with a fake renderer: pass first time; fail then pass; three fails →
  `WITHHELD`; an audit error → `WITHHELD`; every attempt logged; deterministic seeds.
- **T071:** `run_checks`: a `text` of the scene's location ("LOST PROPERTY" in `INT. LOST PROPERTY OFFICE - NIGHT`)
  or a phrase of the shot's `source` passes; a garbled sign ("PARK LEAZING STATION"), a readable
  signature and the heading's time ("NIGHT") fail, each named in the detail; `has_text` true with
  an empty `text` passes; a `clothing` or `architecture` object called `unscripted` or set dressing
  without support passes when not held and fails when held; a `screen_or_sign` called set dressing
  with the heading's words passes. The describer prompt names worn clothes, the place's structure
  and `text`; the describer's schema requires `text`; a stored description without it (a row from
  before T071) validates as `[]` in `AuditView`. `RENDER_MAX_ATTEMPTS` 0 and 4 are refused; the comic job runs
  the setting's attempts (`run_comic_job(max_renders=...)`, comic.md §6); `frame_view` shows `max(max_renders, attempt)`. `reaudit` on a real
  Postgres with an in-memory store and a scripted model: every row of one target in order, none
  written, a missing asset reported and skipped, `limit` honoured; `summary` counts before and after.
  Live, with Tumo's go-ahead (Token Factory only): `python -m app.verify.reaudit` on the
  2026-10-10 lost-property project, then one live upload of the-red-kite at `RENDER_MAX_ATTEMPTS=1`.
- **T072:** `run_checks`: `signature` true fails `TEXT_IN_FRAME` with `text` empty, and the detail
  says "a signature"; `signature` false and `text` empty passes. The describer prompt asks for each
  person's apparent age first and for `signature`; its schema requires `signature`; a stored
  description without it validates as `false` in `AuditView`. The judge prompt names the age rule,
  set dressing's ordinary things and weather as an event. `run_checks`: a no-character person
  supported by a quote naming a shot character (`LERATO (10), braids…`) is `UNSCRIPTED_PERSON`,
  one supported by `a crowd gathers` still passes; a `kite` called `set_dressing` with the
  heading's words fails against the prop `RED KITE`, a `bucket` doesn't. Live, with Tumo's go-ahead (Token
  Factory only): T071's and T072's audits on eval.md §6a's 27 labelled frames (Katlego's, in the
  dev bucket), scored against his labels, the numbers in the PR; then one upload of the-red-kite.
- **T106:** `DESCRIBE_PROMPT` carries the setting sentence verbatim (§3), and the schema is
  unchanged. Live, with `reaudit` on Super VL (announced on the PR): the-red-kite's 44 stored
  attempts are described again; both rooftop attempts (0.4) read `exterior` or `unclear`, and no
  other attempt's setting changes.
- **T107:** `DESCRIBE_PROMPT` carries the text sentences verbatim (§3); `FrameDescription`'s
  fields run `…, signature, signature_text, has_text, text`, `signature_text` is in the model's
  schema's `required`, a stored description without it validates with `[]`, and `run_checks`
  never reads `signature_text`. The same run: the stored attempts' `text` entries are classified by hand first
  (signature or scene lettering), then `text_in_frame` falls back near DeepSeek's 6, with every
  piece of scene lettering ("SNAP.", "SLAP & NOPE.") still in `text`.
- **T077:** `run_checks`: `signature` true with `text` empty fails `SIGNATURE` (soft) and no hard
  check, so the verdict is `WARN`; with an unread word in `text` it also fails `TEXT_IN_FRAME`
  (`FAIL`); `signature` false fails neither. The web names `signature` "artist's signature".
  Free (Token Factory only): T072's and T077's audits on eval.md §6a's 27 labelled frames; the
  only labelled-bad frames newly passing are ones labelled for a signature, the numbers in the PR.
- **T078:** `part_of_prop`: `kite string` and `kite tail` → `RED KITE` when the shot has it; `kite`,
  `blue kite`, `second kite`, `another kite string`, `map of the town`, `kite tail string` → None;
  `kite string` → None when the shot hasn't the prop or the extraction has no quote of it;
  `spool of wire` → None against `SPOOL OF BLUE STRING`; a `weapon`, `animal`, `vehicle` or
  `food` → None. `run_checks`: a held `kite string` passes with the prop in the shot whether
  called `unscripted`, `set_dressing` or `scripted_prop` with no support, and fails without the
  prop; a held `map knife` of category `weapon` still fails. The describer prompt names shading, hatching, outlines and the border. Free, with
  Tumo's go-ahead (Token Factory only): the 27 labelled frames scored with and without T078,
  with no labelled-bad frame newly passing, the numbers in the PR.
- **T080:** `run_checks`: with `on_screen=("NANDI",)` and the one person called no character,
  `NO_CHARACTER` fails (hard, `FAIL`); called `NANDI`, it passes; only `THABO` matched, it fails; with no people described, it fails;
  with `on_screen=()` it never fails. `audit_frame` passes `visible_characters`. The judge prompt
  names sex and look beside age. The web names `no_character` "no character in frame". Free (Token
  Factory only): the 27 labelled frames and the 2026-10-11 klein run's stored drawings, the
  numbers in the PR.
- **T082:** `render_spec` shows `sex (from the script): female, "Siphokazi nods. She cannot stop the
  smile."` for a sexed character and no such line when `character_sex` is None; the judge prompt has
  the sentence.
- **T083:** `named_in_scene`: `boat masts` and `boats` (vehicle) against "a single row of
  forty-year-old wooden fishing-boats" → a match; `fish` (food) against "a fish-head in its mouth"
  → "fish"; `horse` against "horses", `pony` against "ponies", `box of fish` → a match;
  `off-road vehicle` against "the road" → None (the hyphenated word stays whole); `police car`
  against "a police officer" → None (`car` is no part word); `car door` against a scene with a
  door and no car → None (the part's whole is the candidate); `bees` against "will be" → None;
  `car` against "she cares" → None; `buses` against "a bus" → a match; `second boat` → None (copy word);
  `small boats` (other) → None (not one of the four categories); `cart of` → None; a word only in
  the heading or in dialogue → None. `run_checks`: a set-dressing `boats` of a scene
  that names them passes; one the scene doesn't name still fails `UNSCRIPTED_OBJECT` "never set
  dressing"; an unheld `pen` (other) called `unscripted` fails `BACKGROUND_OBJECT` (soft, `WARN`)
  and not `UNSCRIPTED_OBJECT`; a held `pen`, an unheld `pen` called `scripted_prop` with no
  support, and a named prop called `unscripted` still fail `UNSCRIPTED_OBJECT`; a `moon` (nature)
  called `set_dressing` with a support not in the heading fails `BACKGROUND_OBJECT`; a `dog`
  (animal) called `unscripted` still fails `UNSCRIPTED_OBJECT`. `recheck` on database rows: today's
  verdict per attempt, a row with no description and one in an old schema skipped and counted,
  `accepted_shots`, no such project and no plan raising ValueError. The web names
  `background_object` "unscripted background". Free: `recheck --target storyboard` on the 2026-10-11
  runs gives sipho-and-siphokazi at least 12 of 30 (12 measured) and the-red-kite at least 19 of 21 shots with an
  accepted attempt, and the frames newly accepted are looked at for anything a hard check should have
  caught. **Held out:** the same on every other stored project (the-red-kite's earlier runs), the
  numbers in the PR beside the two that showed the problem.
- **T084:** `shot_action_text` joins only the shot's `Action` elements, in order, and is "" for a
  shot of dialogue alone. `run_checks`: an unmatched person supported by a dialogue line of the
  shot fails `UNSCRIPTED_PERSON` "its support is not an action line"; by an entity quote not in
  the shot's action text, the same; by "A pigeon glares at him." (in the action text) fails "its
  support points at someone else", and so do `He …`, `… she …` and "he's" in any case; `his`, `her`,
  `himself` alone don't ("A WOMAN, 40s, folds her umbrella." passes); `he` inside another word ("the",
  "where") doesn't count; a support found nowhere still fails "no shot character, no support", and a
  dialogue line with "him" fails "its support is not an action line" (the order); "A SLEEPING
  COMMUTER lies across a bench under a newspaper." passes, and so does "Passengers hurry past. They
  ignore him"'s first sentence quoted alone; "they" alone passes; a matched character is unaffected;
  T072's "its support is about a character" still wins when the support names one. Free: `recheck`
  on lost-property `0c7cceb4` gives at most 9 shots with an accepted attempt and fails 7.4, 10.2 and
  10.3; **held out**, every other stored project, its before and after in the PR, each newly failed
  attempt read. Then the new held-out script (Tumo, 2026-10-12, unseen until T084 and the L010 fix
  are built) is drawn and every accepted frame looked at.
- **T086:** `described_age`: "a child, a boy with short dark hair" → child; "an old man with white hair, looking
  toward the girl" → old; "a 10-year-old girl" → child; "an older woman" → adult; "a mother holding a child"
  → adult; "a grandmother with a shawl" → old; "an elderly man" → old; "a
  teenager with dark hair" → teenager; "an adult seen from behind" → adult; "an adult woman" → adult; "a figure
  in a coat" → None. `age_contradicts`: (9, adult) and (9, old) → True, (9, teenager) and (9, child) → False;
  (17, old) → True, (17, child) → False; (40, old) and (40, child) → True, (40, teenager) → False; (70, child)
  and (70, teenager) → True, (70, adult) → False; (any, None) → False. `run_checks` with `ages={"THEO": 9}`:
  THEO matched to "an adult seen from behind" fails `UNSCRIPTED_PERSON` "described as adult, but THEO is
  introduced at 9" and THEO isn't placed; matched to "a child, a boy" passes; without `ages` nothing changes.
  `inside_vehicle`: INT. VAN - MOVING → {"van"}; SIPHO'S BAKKIE → {"bakkie"}; EXT. VAN, INT. BAKERY, INT. BUS
  STATION, INT. CAR PARK - LEVEL 2, INT. TAXI RANK → empty. `part_of_vehicle` in
  INT. VAN: "steering wheel", "rearview mirror", "dashboard", "headrests", "car seats" → True; "sailboat",
  "car", "van", "second van", "steering wheel" in INT. BAKERY, a held "pistol barrel" (weapon) and a "dog
  collar" (animal) in INT. VAN → False. A THEO refused for age with a verbatim action-line support still
  fails (no stranger excuse). `run_checks` in INT. VAN: a held
  steering wheel and an unheld dashboard called never-set-dressing both pass. Unheld "bread loaves" (food)
  called `set_dressing` with the heading as support, or `unscripted`, fails `BACKGROUND_OBJECT` (soft, `WARN`),
  not `UNSCRIPTED_OBJECT`; a held bun still fails `UNSCRIPTED_OBJECT`; food the scene names still passes (T083).
  Free: the comparison on every stored audit gives the numbers in §3, every newly accepted drawing looked at
  and listed in the PR. Live: after T088, on the held-out script.
- **T089:** `run_checks`: an unheld pen called `unscripted` with no prop of that name and a held pen called `set_dressing` each fail `BACKGROUND_OBJECT` (soft, `WARN`) with details `object N (pen, other): not in the script` and `object N (pen, other): held, so not set dressing`; a held bun (food) and a car (vehicle) called never-set-dressing warn too, with their own details; a `scripted_prop` mug without a found support warns `prop without support`; a knife (weapon) called `unscripted` and a dog (animal) called `set_dressing` still fail `UNSCRIPTED_OBJECT` (hard); painted text 'LOST POVERTY' in a shot whose source says LOST PROPERTY fails `TEXT_IN_FRAME` with severity soft and the verdict `WARN`; with an unscripted person as well, the verdict is `FAIL`; painted text alone (no other fault) gives `WARN`. Also: an animal `scripted_prop` without support still fails `UNSCRIPTED_OBJECT` "prop without support"; a held knife (weapon) called `set_dressing` still fails it "held, so not set dressing"; a held `clothing` object (a scarf in a hand) now warns. `_filed`: animal and weapon → `UNSCRIPTED_OBJECT`; other, nature, furniture, screen_or_sign, clothing, architecture, vehicle, food → `BACKGROUND_OBJECT`. **Existing tests that change** (their hard object or text failure is now a warning): `test_checks.py` (the `hard` set loses `TEXT_IN_FRAME`; the verdict asserts on held, unsupported and never-dressing objects and on text), `test_t083.py` (a vehicle expected `FAIL`; `test_the_rest_stays_hard`'s held pen, named prop and unsupported prop, its animal case stays), `test_t086.py` (held food and a food `scripted_prop` without support), `test_t078.py` (an `UNSCRIPTED_OBJECT` assert); each is changed to the new routing, not deleted. Free: `recheck` on every stored project gives the numbers in §3, every newly accepted drawing looked at and listed in the PR. Live: the next run.
- **Accuracy:** T049's injected-frame set (eval.md) was deferred 2026-10-12. The 109 hand-labelled
  frames (`eval/frame-labels.json`) scored by `eval/tools/score_labels.py` give the audit's numbers
  ([eval/audit-mistakes.md](../../eval/audit-mistakes.md); the rescore in
  `eval/measurements/t124/rescore-2026-10-20/`).

- **T094** (`tests/verify/test_loop.py`, `tests/verify/test_t095.py`): a failed check off the
  ladder is accepted as WARN on that attempt, logged as WARN with that check now soft; one on the
  ladder still withholds, and a frame failing both names only the one on the ladder; an empty ladder
  still withholds an `ERROR`; `all` returns the audit unchanged; the setting parses `all`, `ALL`,
  empty and a spaced comma list, and refuses a misspelt name and a soft check's name; a warned card
  names every failed check (`build.py`, `document.py`).
- **T095** (`tests/verify/test_t095.py`, tests first): `run_checks` fails `DRAWN_SEX` for a seen
  `male` on a female character with the detail above, and passes `unclear`, the same sex, a
  character with no sex from the script, and an answer filed against a person not accepted as that
  character; `matched_people` skips a second person called for one name, a name not in the shot and
  a person refused for their age; `audit_frame` asks the agent only about a matched person with a
  script sex (a MockTransport counts the questions), names the other described people in the
  question, stores `seen`, counts the agent's tokens, and a failing question leaves `seen` empty and
  the verdict no `ERROR`; `FrameWriter.log` writes `seen`; the severity table names `DRAWN_SEX`
  hard; migration 0007 upgrades and downgrades (the schema test). Live: one script with
  `AUDIT_WITHHOLD_CHECKS=drawn_sex`, where the real code meets `character_sex` (the prototype used
  the labels).
- **T124** (`tests/verify/test_t124.py`, tests first): `described_alike` on identical appearances
  (1.0), on 0.5 exactly (flags) and just below (doesn't), on a pair both known (never), one known
  (flags), neither (flags), with stop words only (0.0), case and punctuation ignored, three alike
  people as three sorted pairs; in `run_checks` two alike scripted extras (no character, an action
  line's support) pass, a character and an alike extra fail, two alike people whose support fails
  (`UNSCRIPTED_PERSON`) fail; `run_checks` fails `DRAWN_TWICE` for an alike pair with `layout` None
  and with a layout of no copies, with the T124 detail; a pair in both sources fails once, with the
  layout's detail; a split frame fails `SPLIT_PANELS` only; `recheck` on a stored row flags it.
  `render.yaml`'s ladder stays `drawn_sex,no_character,split_panels`; a copy warns (test_t104.py `test_the_hosted_ladder_withholds_a_split_and_warns_a_copy`). Mutation check: each rule
  removed, a test fails. Live, free: `recheck` over the 17 Oct runs' stored rows flags 2.1, 1.4 a2,
  5.3 and rooftop 3.1, 6.2, and no frame labelled right.
- **T104** (`tests/verify/test_t104.py`, tests first): `frame_layout` sorts and de-duplicates pairs,
  drops `[i, i]`, negative, out-of-range, short and long pairs, and makes `panels` 0 and -1 into 1;
  `run_checks` fails `SPLIT_PANELS` for `panels` 2 with its detail and passes 1; fails `DRAWN_TWICE`
  for a pair in one picture with its detail, three pairs (the same person three times) with three
  details joined by `; `, a pair with neither person known, and a pair with one accepted and one not;
  passes a pair accepted as two different characters, a pair found by the presence agent as two
  characters (`found=`), a pair one accepted and one found as another character, a pair in a split
  frame, and `layout` None; the severity table names both hard (`tests/verify/test_checks.py`'s hard
  set changes), the default `all` ladder withholds them and a ladder without them warns; `audit_frame` (a MockTransport counting
  questions) asks once for two or more described people, after the other agents, none for one
  person, none for a malformed judgement, sends the prompt and the numbered people with the image at
  4,096 tokens, stores `layout`, counts the tokens, and a failed question leaves `layout` None and
  the verdict no `ERROR`; a comic panel's audit asks it too (comic panels share `audit_frame` through
  `loop.py`, pinned by `audit_frame` taking no target); `FrameWriter.log` writes `layout`; `recheck` passes the row's `layout` (NULL
  as None); migration 0009 upgrades and downgrades (`test_the_models_match_the_migrations`). Token
  Factory: the real code on the 332 stored frames gives about §3's numbers. Live: the next held-out
  runs.
- **T102** (`tests/verify/test_t102.py`, tests first): `found_people` gives character → person for
  the answers `present_characters` keeps, the first that passes per character (a null first answer
  skipped), and `present_characters` equals its
  keys on every T099 case; `run_checks` fails `DRAWN_SEX` for a seen `male` on a found female
  character with T095's detail, and passes `unclear`, the same sex, a found character with no script
  sex, an answer about a found person filed under another character, and an answer about a person
  found but dropped by `found_people` (out of range, accepted as another character, age
  contradicted); `NO_CHARACTER` still passes on that frame (T099 unchanged), so the verdict is
  `FAIL` on `DRAWN_SEX` alone; `audit_frame` (a MockTransport counting questions) asks the sex
  question after the presence agent for a found person with a script sex, once per (person,
  character) pair, none for a character with no script sex, none when the presence agent didn't run,
  none for a null answer, and a failing question leaves that answer out of `seen` and the verdict no
  `ERROR`; a person found for two characters is asked once and kept twice, and with opposite script
  sexes the answer fails `DRAWN_SEX` for the one it contradicts only; a person matched to an
  off-screen character's name beside a found on-screen character (T099's shape): T095's question, the
  presence agent, T102's question, and `seen` in that order; a malformed judgement asks nothing;
  `check_person` asks with `max_tokens` 4,096; with `drawn_sex` off the ladder the frame is `WARN`
  (`apply_ladder`); `recheck` passes a row's `seen` and `found` to `run_checks` (whose failing is the `run_checks` cases
  above), and on a row with
  T095's `seen` alone and `found` decides as before. Token Factory: the real code on the 77 stored
  frames gives about §3's numbers, and lighthouse 7.5 replayed with T101's names is asked and
  flagged. Live: the next held-out runs with `AUDIT_WITHHOLD_CHECKS=drawn_sex,no_character`.
- **T099** (`tests/verify/test_t099.py`, tests first): `present_characters` finds a character
  whose answer names a person in range, and not one whose answer is null, out of range (past the end, or negative), a person
  `matched_people` accepts as another character, or a person whose described age contradicts the
  introduction (a `child` for a character of 50); `run_checks` with such an answer passes
  `NO_CHARACTER` and leaves `UNSCRIPTED_PERSON` and `MISSING_CHARACTER` as they were, and without
  `found` fails it as before; `audit_frame` asks the agent only when the judge matched none of
  `on_screen` (a MockTransport counts the questions: none when one is matched, none for an empty
  `on_screen`, none for a judgement that calls a person twice, one per drawn person character,
  never an animal), asks them after the sex agent's, puts the character's line, the
  shot text and the numbered people in the question, stores `found`, counts the tokens, and a
  failing question leaves `found` without it and the verdict no `ERROR`; `FrameWriter.log` writes
  `found`; `recheck` passes the row's `found` (a NULL row decides as the judge alone);
  `tests/db/test_schema.py::test_the_models_match_the_migrations` covers 0008 and the
  `found` column. Token Factory: the real code on the 30 stored frames gives about
  §3's numbers. Live: one held-out script with `AUDIT_WITHHOLD_CHECKS=drawn_sex,no_character`
  (fal: ask Tumo).
- **T109, measured first** (2026-10-17, Token Factory only, about $0.3; scripts and results in
  `eval/measurements/t109/`): every Super VL `ERROR` with a stored drawing, 7 of the labelled
  frames (market-day 2.1, 3.2, 5.2; sipho-and-siphokazi 2.1; the-borrowed-bicycle 5.5;
  the-lighthouse-inspector 8.1; the-night-taxi 1.1) and rooftop-tomatoes' comic 6.1, asked the
  describer's exact call three times. **Every failure was `finish_reason=length` at 4,096 tokens**,
  cut mid-JSON at the limit on every run, the text nearly the same each time (temperature 0); sipho 2.1 answered in 422 tokens
  all three times, and market-day 5.2 failed once in four runs: it loops sometimes, the other six every time. The raw answers loop: a repeated object or
  person, or a string that never ends. Then each candidate on the 7 that loop and on 10 control
  frames (today's two held-out runs, the most objects first), against the stored answer:

  | Candidate | Looping frames valid | Controls: the same answer |
  |---|---|---|
  | none (the call as it is, a 4th run) | 1 of 7 (market-day 5.2; the other 6 failed all 4 runs) | 9 of 10 |
  | limits in the schema and the prompt (first, smaller limits) | 7 of 7 | 3 of 10 |
  | **limits in the grammar only** (the final limits) | **7 of 7** (351–1,597 tokens) | **10 of 10** |
  | `frequency_penalty` 0.5 | 6 of 7 | 0 of 10 (fewer objects on every one) |
  | a prompt sentence: each object once | 2 of 7 | not run |
  | temperature 0.3 | 2 of 7 | not run |

  **The limits** sit above every stored answer: DeepSeek's 1,352 descriptions reach 21 people,
  32 objects, 15 pieces of text and 175 characters of appearance; Super VL's 79 reach 33 pieces of
  text (a calendar's 31 dates, an honest answer). **Tests** (`tests/verify/test_t109.py`, tests
  first): `description_grammar()` sets exactly the eight limits (`signature_text` at 5 entries of 60,
  2026-10-19) and leaves the rest of
  `FrameDescription.model_json_schema()` equal; `describe_frame` sends the capped schema as
  `response_format` and the uncapped one in the system message (a MockTransport reads the body);
  `structured_chat` without `grammar` sends today's body (llm.md §9); `run_checks` on a description
  of 24 people, every one judged a shot character or supported, fails `UNSCRIPTED_PERSON` with the
  limit detail, and on 23 passes it; 40 objects all scripted fail `BACKGROUND_OBJECT` (soft) with
  its detail, and 39 pass; 40 text entries add nothing. **After the code:**
  `eval/tools/score_labels.py` on the 109 labelled frames with Super VL (about $0.25, Tumo's
  go-ahead): 0 describer `ERROR`s, and every frame whose verdict moves looked at.

- **T097** (`tests/verify/test_t097.py`, tests first): `heads_seen` keeps a visible in-range box
  with its matched character, `None` for an unmatched person, in person order, and drops an
  out-of-range person, a second answer for one person, `visible` false, a box with `x0 ≥ x1` or
  `y0 ≥ y1`, and a coordinate outside 0–1; `render_until_accepted(heads=True)` asks the head agent
  once, on the accepted attempt only (a MockTransport counts the questions over a FAIL then a
  PASS), names every described person by number with position and appearance, logs the audit with
  `heads` and the agent's tokens added, and leaves verdict and checks as they were;
  `heads=False` (the default) never asks; a frame with no described person asks nothing; a failing
  question leaves `heads` empty and the frame accepted; `FrameWriter.log` writes `heads` (`None`
  when the audit has none); the comic job passes `heads=True` and the storyboard paths don't;
  migration 0010 upgrades and downgrades (the schema test). Token Factory, before the code merges:
  the real `find_heads` on Super VL (T105's default, thinking off) on the 15 drawings of §3's
  measurement, the boxes drawn on each and looked at, every one on its head.

## 10. Open questions

- **T084, the judge's side:** the judge isn't told that a person's support must be an action line
  without he/she. If later runs show a scripted stranger failing because the judge quoted a line
  of dialogue, add one judge sentence and measure it with `reaudit` (Token Factory), not `recheck`.

- [x] Does the describer honour `json_schema`? **Answered 2026-09-30 (T020):** GLM-5.3-Flash turned out
  not to receive images at all (findings § U7 re-check), so the describer became DeepSeek-V4.1-Flash
  (2026-09-30 → 10-17), which returned schema-valid descriptions on every live call, no repair needed.
  Since T105 it is Nemotron 3.5 Super VL: 44 of 44 schema-valid, 0 repairs (findings § U8).
- [ ] How reliable is the describer's `shot_size`? If noisy, `FRAMING` stays soft (it is) or is
  dropped. In T020's three live runs it matched what the frames show.
- [x] **Precision on correct frames (for T049).** Live, the describer filed plates and bowls under
  `food`, which can never be set dressing, and set `has_text` on two of three frames whose only candidates are papers and plans on a table. Both
  push a frame toward FAIL, the safe side, but a good frame could burn its renders. T049 was to measure the
  false-FAIL rate; if it's high, the category list or the describer prompt changes, not the rule.
  **Measured on the labelled set instead** (T049 deferred): 1 of 40 right frames withheld on today's
  hosted ladder (2026-10-20 rescore); food and lettering warn since T086 and T089.
- [x] Option B (a self-hosted NVIDIA VLM on the ComfyUI GPU) would let Nemotron-family models see
  the image directly. **Answered 2026-10-17 without a GPU:** Nemotron 3.5 Super VL on Token Factory
  sees the image (T105, findings § U8); T003 was cut 2026-10-19.
