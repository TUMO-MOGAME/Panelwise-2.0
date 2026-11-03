# Design — `script` (screenplay parsing; lane `script+grounding`)

**Status:** agreed · **Owner:** Katlego (Claude) · **Tasks:** T005, T039 · **Spec:** [SPEC.md](../../SPEC.md)
US1 (script → grounded storyboard)

---

## 1. What this covers

Turning a screenplay PDF into ordered, typed scenes where **every piece of text carries the page
and lines it came from**. This is the foundation of Non-negotiable I: a panel can only trace back to
a verbatim span if the parser kept one. Also here: resolving a scene's clock when the heading
borrows it (`CONTINUOUS`), and matching a dialogue cue to an extracted character name.

**Not covered:** storage (the projects lane's; everything here is a pure function over values),
entity extraction and the grounding filter (T006, `docs/design/grounding.md`), shots (T007).

## 2. Reference material

| Kind | Where |
| --- | --- |
| Code ported from | FrameFlow `services/api/app/services/screenplay_parser.py` (margin-based classification, heading regex, page-furniture filter), `scene_time.py` (absolute/relative times), `dialogue_linker.py` (`normalise`, `match_speaker`) |
| Test fixture | a self-written 3-scene screenplay, rendered to PDF in the test with fpdf2 at standard screenplay margins. No copyrighted script, ever (PLAN.md constraints) |
| External | pdfplumber `extract_text(layout=True)`; screenplay format conventions (action at the margin, cue ~3.7", dialogue ~2.5", parenthetical ~3.1") |

## 3. Domain model

```mermaid
classDiagram
    class Screenplay {
        +str text
        +int page_count
        +tuple~Scene~ scenes
    }
    class Scene {
        +int index
        +str number
        +str heading
        +IntExt int_ext
        +str location
        +str|None time_of_day
        +tuple~Element~ elements
        +Span span
    }
    class Span {
        +int page
        +int line_start
        +int line_end
    }
    class Action {
        +str text
        +Span span
    }
    class Dialogue {
        +str cue
        +str|None extension
        +str|None parenthetical
        +str text
        +Span span
    }
    class IntExt {
        <<enum>>
        INT
        EXT
        INT_EXT
    }
    Screenplay "1" --> "*" Scene
    Scene "1" --> "*" Action
    Scene "1" --> "*" Dialogue
    Scene --> Span
    Action --> Span
    Dialogue --> Span
```

- **`Screenplay.text`** is the extracted text, one line per layout row, pages joined in order. It is
  the source every `Span` indexes, and the text grounding (T006) checks quotes against.
- **`Span`**: `page` is 1-based (the page of `line_start`); `line_start`/`line_end` are 1-based,
  inclusive line numbers in `Screenplay.text`. `Screenplay.text.splitlines()[line_start-1:line_end]`
  is the exact source of the element, verbatim.
- **`Scene.elements`** keeps action and dialogue **in script order** (a comic needs the
  interleaving). Consecutive action lines form one `Action` until a blank line or a non-action
  line. Consecutive dialogue lines under one cue form one `Dialogue`; a parenthetical starts a new
  one for the same cue. Wrapped lines are joined with a single space, except across a
  **line-break hyphen** (T048): a line ending in a run of dashes (`-`, `–`, `—`, `−`) that touches
  the word before it joins the next line with no space (`sea-` / `green` → `sea-green`, `south-` /
  `westerly` → `south-westerly`, `stops--` / `then` → `stops--then`). A spaced dash at a line's
  end (`LOST PROPERTY -` / `PLATFORM 9`, `WAIT --` / `NO`) keeps its space, and so does a line
  that is only dashes. Grounding's `normalize_for_grounding` applies the same rule to the raw lines
  (grounding.md §4; it folds `–` `—` `−` to ASCII first), so an element's text and its span's
  lines normalise to the same string. The span's lines themselves are untouched: an element's text
  is its span's lines, stripped and joined by this rule.
- **`Scene.number`**: the number printed in the script ("12A") when there is one, else the 1-based
  sequence. `index` is always the 0-based position.
- **`time_of_day`** is the heading's time as written, upper-cased (`NIGHT`, `CONTINUOUS`), or
  **`None` when the heading gives none**. FrameFlow defaulted to `DAY`, which states a fact the
  script doesn't. The first separator (` - ` or `--`) splits location from time, except when
  the heading has two or more and its last segment is a known time (`ABSOLUTE_TIMES |
  RELATIVE_TIMES`): then that segment is the time and everything before it the location
  (`INT. SIPHO'S HOUSE - KITCHEN - NIGHT` → `SIPHO'S HOUSE - KITCHEN`, `NIGHT`; T039).
- **`Dialogue.cue`** is the name only ("WAYNE"); `extension` is the cue's bracket ("O.S.", "V.O.",
  "CONT'D") or `None`.

## 4. Flow

```mermaid
sequenceDiagram
    participant U as Caller (upload endpoint, T053)
    participant P as parse_pdf
    participant L as pdfplumber
    participant T as parse_text
    U->>P: PDF bytes
    P->>L: extract_text(layout=True, y_density=12) per page
    L-->>P: page texts
    P->>T: lines joined, page_breaks = first line of each page
    T->>T: action margin = most common indent
    T->>T: walk lines: heading / furniture / transition / cue / parenthetical / dialogue / action
    T-->>U: Screenplay
```

**Classification** (per non-blank line; page furniture — `(CONTINUED)`, `CONTINUED: (2)`, `(MORE)`,
bare page numbers — is dropped whole. A line is never rewritten, so an element's text is always
exactly the lines its span names):
1. Scene heading (`INT`/`EXT`/`INT/EXT`/`EXT/INT`, each dot optional, so `INT./EXT.` too;
   optional scene number on the left) → new scene. The number repeated at the right edge is dropped only when it sits after a
   layout gap of 2+ spaces, so `INT. ROOM 1` keeps its "1".
2. Before the first heading → ignored (title page).
3. Transition (`CUT TO:`, `FADE OUT.`, `DISSOLVE TO:` …) → dropped; it is editing, not content.
4. Indented past the action margin + 4:
   parenthetical `(…)` → attaches to the current cue; all-caps ≤ 5 words **at the cue column**
   (within 2 of the last cue's indent; any column for the first cue) → cue; otherwise, under a cue
   → dialogue. The cue-column rule keeps a shouted "NO!" at the dialogue column from reading as a
   new speaker. **A parenthetical that wraps** (T039): under a cue, a line that opens `(` with no
   `)` is held; following lines at the *same indent on the same page*, with no `(`, are held too,
   and the first one ending `)` closes it — the held lines, joined, become the parenthetical.
   Anything else first (a blank line, another indent, a page break, furniture) replays the held
   lines as dialogue, which is what they were read as before: the rule can only retype lines, never
   drop them.
5. Anything else → action (and it ends the current cue).
A blank line ends the current action paragraph and the current cue. A page break ends the current
element but keeps the speaker, so dialogue continuing onto the next page stays dialogue.

**Row height:** pdfplumber's layout text groups characters into rows of `y_density` points,
13 by default. Screenplay lines are 12 pt apart (6 an inch), so at 13 some one-line gaps round
away and two action paragraphs read as one (13 of 102 breaks in the T031 samples). `parse_pdf`
uses 12, which kept every break in all three samples and in the fpdf2 test PDF (T039).

**Action margin:** the column scene headings start at (they always sit at the action margin); only
without headings, the most common indent. FrameFlow used the most common indent alone, which in a
dialogue-heavy script is the dialogue column.

**Failure paths:** a PDF with no text layer (a scan) → `ScriptParseError("no text layer")`, never an
empty screenplay that looks like success. No scene heading anywhere → `ScriptParseError("no scene
headings")`. A malformed PDF → `ScriptParseError` wrapping pdfplumber's error type only.

## 5. State

None. Values in, values out.

## 6. Contracts

```python
# app/script/model.py
class IntExt(StrEnum): INT = "INT"; EXT = "EXT"; INT_EXT = "INT/EXT"
@dataclass(frozen=True) class Span: page: int; line_start: int; line_end: int
@dataclass(frozen=True) class Action: text: str; span: Span
@dataclass(frozen=True) class Dialogue: cue: str; extension: str | None; parenthetical: str | None; text: str; span: Span
type Element = Action | Dialogue
@dataclass(frozen=True) class Scene: index: int; number: str; heading: str; int_ext: IntExt; location: str; time_of_day: str | None; elements: tuple[Element, ...]; span: Span
@dataclass(frozen=True) class Screenplay: text: str; page_count: int; scenes: tuple[Scene, ...]; page_starts: tuple[int, ...]
#   page_starts: the 1-based first line of each page in `text`: page_starts[0] == 1, len == page_count,
#   (1, *page_breaks) (web.md §3; the lined script breaks pages where the PDF did)
type ParseErrorCode = Literal["not_a_pdf", "no_text_layer", "no_headings"]
class ScriptParseError(ValueError):
    def __init__(self, code: ParseErrorCode, message: str) -> None: ...
    code: ParseErrorCode   # one per raise: parse_pdf can't open it → "not_a_pdf"; no page has text → "no_text_layer";
                           # parse_text finds no heading → "no_headings". Callers branch on `code`, never on the message.

# app/script/parser.py
def parse_pdf(data: bytes) -> Screenplay: ...
def parse_text(text: str, page_breaks: Sequence[int] = ()) -> Screenplay: ...
#   page_breaks: 1-based line numbers where pages 2, 3, … begin; () means one page.

# app/script/scene_time.py
ABSOLUTE_TIMES: frozenset[str]; RELATIVE_TIMES: frozenset[str]
def absolute_time(value: str | None) -> str | None: ...
def resolve_times(scenes: Sequence[Scene]) -> list[str | None]: ...
#   one entry per scene: its own absolute time, else the nearest earlier scene's, else None.

# app/script/speakers.py
def normalise(name: str) -> str: ...
def match_speaker(cue: str, names: Sequence[str]) -> str | None: ...
#   exact normalised match wins; else the cue's words ⊆ exactly one name's words; ambiguous → None.
```

## 7. Structure

| Path | New? | Responsibility |
| --- | --- | --- |
| `services/api/app/script/__init__.py` | new | re-exports §6 |
| `services/api/app/script/model.py` | new | the dataclasses and `ScriptParseError` |
| `services/api/app/script/parser.py` | new | `parse_pdf`, `parse_text` |
| `services/api/app/script/scene_time.py` | new | `absolute_time`, `resolve_times` |
| `services/api/app/script/speakers.py` | new | `normalise`, `match_speaker` |
| `services/api/tests/script/` | new | unit tests on layout text; an end-to-end test on a PDF built with fpdf2 |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Source positions | page + line range per element | FrameFlow's none: Non-negotiable I needs a verbatim span per panel |
| Element order | one ordered `elements` tuple | FrameFlow's separate action/dialogue lists: loses the interleaving a comic page needs |
| Wrapped lines | joined into one element | FrameFlow's one entry per printed line: a speech bubble needs the whole speech |
| Line-break hyphen | joined with no space when it touches the word before it (`sea-green`); a spaced dash keeps its space | joined with a space (`sea- green`): a model copies it and the quote is not located, and a bubble letters it; dropping the hyphen (`seagreen`): a compound split at its hyphen would lose it, and grounding keeps it |
| Missing time of day | `None` | FrameFlow's `DAY` default: invents a fact |
| Page numbers | real, from per-page extraction | FrameFlow's proportional estimate: a span must point at the actual page |
| Eighths / page-length estimates | dropped | scheduling data; Panelwise doesn't schedule |
| DB linking (`link_project_dialogue`) | not ported | no models yet; `match_speaker` is the reusable part and T006/T023 call it |
| Parser | pdfplumber layout text | Docling: truncated a 150-page script to a third (FrameFlow T283) |
| Layout row height | 12 pt (`y_density=12`) | pdfplumber's 13 pt default: loses ~13% of one-line paragraph gaps in 12 pt screenplays (T031 samples) |
| Two-dash headings | last segment is the time only if it is a known time | always the last segment: `INT. HOUSE - KITCHEN` would get time `KITCHEN`; always the first: `KITCHEN - NIGHT` is no time at all |
| Wrapped parenthetical | held until a same-indent line ends `)`, else replayed as dialogue | any `(`-line opens one: an unclosed bracket in a speech would swallow the rest of it |

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none.

## 9. How this is verified

- Layout-text unit tests: every classification rule in §4, each field in §3 (including `None` time,
  cue extensions, parenthetical splitting, wrapped-line joining (line-break hyphen joined, spaced
  dash kept), furniture and transitions dropped,
  scene numbers on either side), and **every element's `Span` slicing back to text that contains the
  element's words**.
- **Every element of every sample normalises to its span's lines**: `normalize_for_grounding(e.text)
  == normalize_for_grounding("\n".join(span lines))` (T048), so a quote copied from element text
  is always located. This replaces the old check that `" ".join(span lines) == e.text`; the
  elements whose text differs from that plain join are listed per sample, so nothing else moves.
- End-to-end: a 3-scene, 2-page self-written screenplay rendered to PDF with fpdf2 parses into the
  expected scenes, with the second-page element reporting `page == 2`.
- Error paths: an image-only PDF and a text with no headings raise `ScriptParseError`.
- `resolve_times` and `match_speaker` tables, including the ambiguous-cue case.

## 10. Open questions

- [x] A parenthetical that wraps onto two lines (`(quietly, almost` / `to herself)`) was read as
  dialogue text. Fixed in T039 (§4, rule 4): `sipho-and-siphokazi` has two, of three and four
  lines.
- [ ] A spoken line that itself opens with `(` and wraps to a line ending `)` at the *dialogue*
  column (`(If you must know,` / `she said)`) reads as a wrapped parenthetical (T039 review):
  the words move to `parenthetical`, out of the speech's text. Rare; a fix needs the dialogue
  column (parentheticals sit ~0.6" right of it), which the parser doesn't track yet.
- [ ] Dual dialogue (two speakers side by side) is not detected; both columns read as one speaker's
  lines or as action. Rare in the scripts we'll demo; revisit if a sample needs it.
