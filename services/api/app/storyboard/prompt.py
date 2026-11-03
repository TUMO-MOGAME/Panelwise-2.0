"""The frame prompt: Non-negotiable I on the input to the image model. docs/design/storyboard.md
§3.1.

A pure function of the shot, the screenplay, the extraction and the style. Its script words come
only from this shot's scene heading and the Action elements it covers, each part tagged with the
span it came from, so a test (and a reader) can check every word against the script. It takes no
free text: not the shot's rationale, not a model's description, not a character's introduction
from another shot (it would carry that moment's event into this frame). Dialogue, parentheticals
and camera movement never enter it: speech isn't visible and puts letters in the art, and a still
can't pan. Names are redacted before anything else happens to the text.

Ported from FrameFlow's storyboard_service.py: comma phrases (how CLIP reads captions), the medium
first, the setting as "inside <place>" straight after the framing, the resolved clock, the framing
vocabulary. Not ported: the free-text frame description and its fallback to the scene's first 400
characters of action, the movement words, and the `classic` prompt's negations.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from app.characters import name_tokens, redact
from app.characters.labels import animals, redaction_labels
from app.characters.sex import CONFLICT_WORDS, PRONOUNS, SEX_TITLES, SEX_WORDS, Sex
from app.grounding import NOT_POSSESSED, SENTENCE_END, Entity, EntityKind, Extraction
from app.script import (
    Action,
    Dialogue,
    IntExt,
    Scene,
    Screenplay,
    Span,
    absolute_time,
    match_speaker,
    normalise,
)
from app.shots import Framing, Shot
from app.storyboard.styles import Style


class PartKind(StrEnum):
    STYLE = "style"
    FRAMING = "framing"
    SETTING = "setting"
    TIME = "time"
    COUNT = "count"
    AGE = "age"  # T074: a visible character's age, from the script's introduction
    SEX = "sex"  # T082: "a female person" for a character the script sexes but gives no age
    LOOK = "look"  # T079: their description, verbatim from that introduction
    PLACEMENT = "placement"
    ACTION = "action"


@dataclass(frozen=True)
class PromptPart:
    kind: PartKind
    text: str
    span: Span | None  # where a script part came from; None for the style's and code's words


@dataclass(frozen=True)
class FramePrompt:
    parts: tuple[PromptPart, ...]
    trimmed: int  # ACTION parts dropped or cut to fit the word budget

    def text(self) -> str:
        return ", ".join(p.text for p in self.parts)


class PromptError(ValueError):
    """The fixed parts alone exceed the word budget: a style or location too long for the encoder
    is a configuration error, never a silently truncated prompt."""


FRAMING_WORDS: Mapping[Framing, str] = MappingProxyType(
    {
        Framing.WIDE: "wide shot",
        Framing.MEDIUM: "medium shot",
        Framing.CLOSE_UP: "close-up",
        Framing.EXTREME_CLOSE_UP: "extreme close-up",
        Framing.OVER_SHOULDER: "over-the-shoulder shot",
        Framing.POV: "point-of-view shot",
        Framing.INSERT: "close-up insert shot",
    }
)
PLACEMENT_PHRASES: frozenset[str] = frozenset({"one figure on the left, one on the right"})
OFF_SCREEN_MARKS: tuple[str, ...] = ("V.O.", "O.S.", "O.C.", "OFF")

_PREPOSITIONS: Mapping[IntExt, str] = MappingProxyType(
    {IntExt.INT: "inside", IntExt.EXT: "outside", IntExt.INT_EXT: "at"}
)
_COUNTS: Mapping[int, str] = MappingProxyType(
    {1: "one figure", 2: "two figures", 3: "three figures", 4: "four figures"}
)
_GROUP = "a group of figures"
_CLOSERS = "\"')]\u201d\u2019"


def heading_span(scene: Scene) -> Span:
    """The heading line alone: `Scene.span` runs on to the scene's last element."""
    return Span(scene.span.page, scene.span.line_start, scene.span.line_start)


def time_source(scenes: Sequence[Scene], scene_index: int) -> int | None:
    """The scene whose own heading supplied `resolve_times`' clock for this one: itself, else the
    nearest earlier scene with an absolute time, else None. A CONTINUOUS scene's night cites the
    heading that says NIGHT."""
    for i in range(scene_index, -1, -1):
        if absolute_time(scenes[i].time_of_day) is not None:
            return i
    return None


def visible_characters(
    shot: Shot, screenplay: Screenplay, extraction: Extraction
) -> tuple[str, ...]:
    """The planner's characters that the covered elements put on screen, in the planner's order:
    an on-screen speaker (not V.O., O.S., O.C. or OFF), or a character an action line names by
    its name or a paired other name. People only: an animal is never a figure (T052). T093: with
    no one else on screen, the one cast person a covered He or She means (`pronoun_figure`)."""
    if shown := _shown_characters(shot, screenplay, extraction):
        return shown
    figure = pronoun_figure(shot, screenplay, extraction)
    return (figure,) if figure is not None else ()


# T093: a sentence that opens with exactly He or She (He, She's, He: but not Hesitant or Then he).
_PRONOUN_OPENING = re.compile(r"(He|She)(?![A-Za-z])")


def pronoun_sentences(text: str) -> tuple[tuple[str, Sex | None], ...]:
    """`text`, already redacted and collapsed, split at `SENTENCE_END` (T093): joined by one space
    the pieces give `text` back. Each with the sex of an opening exact He or She, else None."""
    out: list[tuple[str, Sex | None]] = []
    for piece in SENTENCE_END.split(text):
        if not piece:
            continue
        m = _PRONOUN_OPENING.match(piece)
        sex = None if m is None else Sex.MALE if m.group(1) == "He" else Sex.FEMALE
        out.append((piece, sex))
    return tuple(out)


def _script_text(text: str, labels: Mapping[str, str]) -> str:
    """A script span as a prompt part says it: redacted, before any lower-casing, and collapsed."""
    return " ".join(redact(text, labels).split())


def _heard(shot: Shot, scene: Scene) -> set[str]:
    """The shot's characters who speak off screen in it (T079)."""
    heard: set[str] = set()
    for i in shot.elements:
        element = scene.elements[i]
        if isinstance(element, Dialogue) and any(
            mark in (element.extension or "").upper() for mark in OFF_SCREEN_MARKS
        ):
            if (who := match_speaker(element.cue, shot.characters)) is not None:
                heard.add(who)
    return heard


def pronoun_figure(shot: Shot, screenplay: Screenplay, extraction: Extraction) -> str | None:
    """T093 (storyboard.md §3.1): when the covered elements put no one on screen, the one candidate
    (the shot's people, less its off-screen speakers) whose sex every covered He or She gives, when
    every candidate's sex is known and exactly one has it. Else None."""
    if _shown_characters(shot, screenplay, extraction):
        return None
    scene = screenplay.scenes[shot.scene_index]
    labels = redaction_labels(extraction, screenplay)
    sexes = {
        sex
        for i in shot.elements
        if isinstance(element := scene.elements[i], Action)
        for _, sex in pronoun_sentences(_script_text(element.text, labels))
        if sex is not None
    }
    if len(sexes) != 1:
        return None
    wanted = sexes.pop()
    beings, heard = animals(extraction), _heard(shot, scene)
    candidates = [c for c in shot.characters if c not in beings and c not in heard]
    known = [character_sex(c, screenplay, extraction) for c in candidates]
    if not candidates or any(k is None for k in known):
        return None
    match = [c for c, k in zip(candidates, known, strict=True) if k is not None and k[0] is wanted]
    return match[0] if len(match) == 1 else None


def _shown_characters(
    shot: Shot, screenplay: Screenplay, extraction: Extraction
) -> tuple[str, ...]:
    """`visible_characters` before T093: speakers on screen, people an action line names, and the
    T079 listeners."""
    scene = screenplay.scenes[shot.scene_index]
    beings = animals(extraction)
    own = {c: _own_labels(c, screenplay, extraction) for c in shot.characters}
    shown: set[str] = set()
    heard: set[str] = set()  # T079: planner characters who speak off screen here
    off_screen = False  # T079: any covered line spoken off screen, by anyone
    for i in shot.elements:
        element = scene.elements[i]
        if isinstance(element, Dialogue):
            extension = (element.extension or "").upper()
            if any(mark in extension for mark in OFF_SCREEN_MARKS):
                off_screen = True
                if (who := match_speaker(element.cue, shot.characters)) is not None:
                    heard.add(who)
                continue
            if (who := match_speaker(element.cue, shot.characters)) is not None:
                shown.add(who)
        else:
            # Named in the line exactly when redacting that one character changes it.
            shown.update(c for c in shot.characters if redact(element.text, own[c]) != element.text)
    people = tuple(c for c in shot.characters if c in shown and c not in beings)
    if people or not off_screen:
        return people
    # T079: a line heard off screen and no one on screen: the planner's others are listening.
    return tuple(c for c in shot.characters if c not in heard and c not in beings)


# A character introduced the way screenplays do: `NAME (` and an age in years (T074). A number, an
# optional `s`, an optional years word, then , ; or ): `(5 months)` is no age.
def _introduction(character: str, screenplay: Screenplay) -> tuple[Action, re.Match[str]] | None:
    # One scan per character and screenplay: every prompt part asks again (see _names_cache).
    entry = _intro_cache[0] if _intro_cache else None
    if entry is None or entry[0] is not screenplay:
        found: dict[str, tuple[Action, re.Match[str]] | None] = {}
        entry = (screenplay, found)
        _intro_cache[:] = [entry]
    if character not in entry[1]:
        entry[1][character] = _scan_introduction(character, screenplay)
    return entry[1][character]


_intro_cache: list[tuple[Screenplay, dict[str, tuple[Action, re.Match[str]] | None]]] = []


def _scan_introduction(
    character: str, screenplay: Screenplay
) -> tuple[Action, re.Match[str]] | None:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(character)}\s*\(\s*(\d{{1,3}})(s?)"
        rf"\s*(?:years?[- ]old|yrs?|yo|y/o)?\s*[,;)]"
    )
    for scene in screenplay.scenes:
        for element in scene.elements:
            if isinstance(element, Action) and (m := pattern.search(element.text)):
                return element, m
    return None


def _other_names(character: str, screenplay: Screenplay) -> frozenset[str]:
    """Other characters' name words, lower case (T079 review): every dialogue cue and every
    `NAME (` introduction, less `character`'s own words and titles. Props in capitals (RED KITE)
    are neither, so they bound nothing."""
    own = set(character.lower().split())
    return frozenset(w for w in _name_words(screenplay) - own - _TITLES if len(w) > 1)


# The last screenplay's name words: a prompt asks for them per character and per shot, and
# scanning a whole feature each time made the invariant test take minutes. Held by identity,
# with the screenplay itself, as labels.py's scene words are, so a new screenplay never reads a
# stale entry.
_names_cache: list[tuple[Screenplay, frozenset[str]]] = []


def _name_words(screenplay: Screenplay) -> frozenset[str]:
    """Every word of every dialogue cue and `NAME (` introduction, lower case."""
    entry = _names_cache[0] if _names_cache else None  # one read: another thread may replace it
    if entry is not None and entry[0] is screenplay:
        return entry[1]
    names: set[str] = set()
    for scene in screenplay.scenes:
        for element in scene.elements:
            if isinstance(element, Dialogue):
                names.add(element.cue)
            else:
                names.update(m.group(1) for m in _INTRODUCED.finditer(element.text))
    words = frozenset(w for n in names for w in re.findall(r"[a-z]+", n.lower()))
    _names_cache[:] = [(screenplay, words)]
    return words


_INTRODUCED = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z'. -]*[A-Z])\s*\(\s*\d")
_TITLES = frozenset({"mr", "mrs", "ms", "dr", "officer", "mama", "papa", "the"})
_NOT_A_LOOK = re.compile(r"[(\d]|^(?:and|who|then|as|while|but)\b", re.IGNORECASE)
_NEXT_INTRODUCTION = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z'. -]*[A-Z]\s*\(")
_LOOK_MAX_WORDS = 8
_ACTION_FLOOR = 12  # words a shot's action keeps before any look (T079)


def _look_of(element: Action, m: re.Match[str], name: str, screenplay: Screenplay) -> str | None:
    """§3.1's LOOK, read from an introduction's match: the parenthesis's items after the age, then
    the comma phrase right after it when a comma closes that phrase before the sentence ends."""
    text = element.text
    close = text.find(")", m.end() - 1)
    # No closing parenthesis in the introducing sentence: nothing here is surely a look.
    if close < 0 or re.search(r"[.!?]", text[m.end() - 1 : close]):
        return None
    items = [i.strip() for i in re.split(r"[,;]", text[m.end() - 1 : close].lstrip(",;)"))]
    after = re.match(r"\s*,\s*([^,.;!?]+),", text[close + 1 :])
    if after:
        items.append(after.group(1).strip())
    others = _other_names(name, screenplay)
    kept = [
        " ".join(i.split())
        for i in items
        if i
        and len(i.split()) <= _LOOK_MAX_WORDS
        and not _NOT_A_LOOK.search(i)  # a conjunction, a parenthesis or a number: not a look
        and not others & set(re.findall(r"[a-z]+", i.lower()))  # nor someone else's
    ]
    return ", ".join(kept) or None


def introduced_look(character: str, screenplay: Screenplay) -> tuple[str, Span] | None:
    """The description the introduction gives (T079), verbatim: `LERATO (10), braids tied back,
    grips…` -> "braids tied back"; `NANDI (60s, oilskin coat)` -> "oilskin coat"; with the
    introducing element's span. Its action (`grips a RED KITE`) is that moment's event: left out."""
    found = _introduction(character, screenplay)
    if found is None:
        return None
    look = _look_of(*found, character, screenplay)
    return (look, found[0].span) if look else None


def introduced_sex(character: str, screenplay: Screenplay) -> Literal["female", "male"] | None:
    """The sex the introduction's own pronouns give (T079): "she"/"he" in the introducing sentence
    (to its end or the next introduction), "her"/"his" inside its look. One sex only, else None:
    `MAMA THEMBI (60s), the shop's owner, watches her` is someone else's "her"; a later sentence's
    "She waves" may be anyone."""
    found = _introduction(character, screenplay)
    if found is None:
        return None
    element, m = found
    rest = element.text[m.end() :]
    if nxt := _NEXT_INTRODUCTION.search(rest):
        rest = rest[: nxt.start()]
    # T079 review: a "he" after another character's name may be theirs ("watches SIPHO as he").
    others = _other_names(character, screenplay)
    if hit := next(
        (w for w in re.finditer(r"[A-Za-z]+", rest) if w.group().lower() in others), None
    ):
        rest = rest[: hit.start()]
    if end := re.search(r"[.!?](?:\s|$)", rest):
        rest = rest[: end.start()]
    words = set(re.findall(r"[a-z]+", rest.lower()) if rest else [])
    look = set(re.findall(r"[a-z]+", (_look_of(element, m, character, screenplay) or "").lower()))
    noun = _appositive_sex(element.text[: m.start()])  # T096: "A boy in a blazer, THABO (9)"
    after = _next_sentence_sex(character, element, m, screenplay)  # T100: "… Her little brother"
    female = "she" in words or "her" in look or noun is Sex.FEMALE or after is Sex.FEMALE
    male = "he" in words or "his" in look or noun is Sex.MALE or after is Sex.MALE
    if female == male:
        return None
    return "female" if female else "male"


# T096: an introducing sentence that opens "A"/"An", at most three words, a sex noun, then its own
# describing phrase (bounded in `_appositive_sex`) up to the comma right before the name.
_APOSTROPHES = "'\u2019"
_SEX_NOUNS = sorted((w for w in SEX_WORDS if w not in PRONOUNS), key=len, reverse=True)
_APPOSITIVE = re.compile(
    rf"(?:^|(?<=[.!?]\s))(?:A|An)\s+(?:[\w'-]+\s+){{0,3}}?({'|'.join(map(re.escape, _SEX_NOUNS))})"
    rf"\b(?![{_APOSTROPHES}])[^.!?()]*,\s*$"
)


# T096's bounds: the words that may open the noun's own phrase, and words that mean the phrase is
# about someone else (general English, not any sample's).
_DESCRIBING = frozenset({"in", "with", "wearing", "dressed", "of", "from"})
_CLAUSE_WORDS = frozenset({"and", "or", "but", "who", "whose", "that", "which", "while"})
_PERSON_NOUNS = frozenset(
    {
        "baby",
        "babies",
        "child",
        "children",
        "kid",
        "kids",
        "toddler",
        "infant",
        "teenager",
        "friend",
        "friends",
        "people",
        "person",
        "family",
    }
)


def _appositive_sex(before: str) -> Sex | None:
    """The sex noun of an appositive opening the sentence that ends at the name (T096), or None.
    `before` is the element's text up to the name."""
    sentence = re.split(r"(?<=[.!?])\s+", before)[-1]
    m = _APPOSITIVE.match(sentence)
    if m is None:
        return None
    # The noun's own phrase, not a clause about someone else: nothing, or at most six words that
    # open with a describing word ("in a blazer", "wearing a cap") and hold no second sex noun,
    # no him/his/her, no conjunction and no other person ("A woman hands the boy a letter",
    # "A woman and her child", "A man holding a baby" name no one's sex).
    after = [w.lower() for w in re.findall(rf"[A-Za-z{_APOSTROPHES}-]+", sentence[m.end(1) :])]
    if not after:
        return SEX_WORDS[m.group(1)]
    if (
        len(after) > 6
        or after[0] not in _DESCRIBING
        or any(w in CONFLICT_WORDS or w in _CLAUSE_WORDS or w in _PERSON_NOUNS for w in after)
    ):
        return None
    return SEX_WORDS[m.group(1)]


# T100: the introducing sentence ends where grounding's do (never after "Mr." or "Dr."), or at "…".
_T100_END = re.compile(SENTENCE_END.pattern.replace("(?<=[.!?])", "(?<=[.!?\u2026])", 1))
# T100: words in the introducing sentence that mean someone else is (or may be) in it, whom a Her
# or His opening the next sentence could belong to; an article or determiner may bring in anyone
# no list holds ("hands the clerk a coin", "pats a dog"), so it blocks too.
_SOMEONE_ELSE = (
    frozenset(SEX_WORDS)
    | frozenset(CONFLICT_WORDS)
    | _PERSON_NOUNS
    | frozenset({"them", "the", "a", "an", "this", "that", "these", "those", "another", "some"})
)
# A word of any script: letters (accented too), then letters, digits or either apostrophe.
_T100_WORD = r"[^\W\d_][\w'\u2019]*"


def _next_sentence_sex(
    character: str, element: Action, m: re.Match[str], screenplay: Screenplay
) -> Sex | None:
    """T100 (storyboard.md §3.1): the sex a possessive Her or His opening the sentence right after
    the introducing one gives, when the introducing sentence, from just after its parenthesis to
    its end, holds no one else: no other name (a known one, or any capitalised word: a name the
    script never introduced), no next introduction, no sex noun or pronoun, no person noun, no
    them, no article or determiner. None otherwise, and when the introducing sentence is the
    element's last."""
    text = element.text
    close = text.find(")", m.start())
    if close < 0:
        return None
    end = _T100_END.search(text, close)
    if end is None:
        return None
    tail = text[close + 1 : end.start()]
    if _NEXT_INTRODUCTION.search(tail):
        return None
    found = re.findall(_T100_WORD, tail)
    words = {w.lower() for w in found}
    if words & _other_names(character, screenplay) or words & _SOMEONE_ELSE:
        return None
    if any(w[0].isupper() for w in found):
        return None
    nxt = _T100_END.split(text[end.end() :], maxsplit=1)[0]
    # Only whitespace between Her and the word it owns: "Her, then silence." owns nothing.
    opening = re.match(rf"(Her|His)\b(?:[ \t]+({_T100_WORD}))?", nxt)
    if opening is None:
        return None
    if opening.group(1) == "His":
        return Sex.MALE
    following = (opening.group(2) or "").lower()
    return Sex.FEMALE if following and following not in NOT_POSSESSED else None


def title_sex(character: str) -> Sex | None:
    """The sex the name's first word gives when it is a sex title (T082): `MAMA THEMBI` female,
    `MR. DUBE` male, `OFFICER MOLOI` None."""
    words = normalise(character).split()
    return SEX_TITLES.get(words[0]) if words else None


def _entity(character: str, extraction: Extraction) -> Entity | None:
    key = normalise(character)
    return next(
        (
            e
            for e in extraction.entities
            if e.kind is EntityKind.CHARACTER and normalise(e.name) == key
        ),
        None,
    )


_EVIDENCE_MAX = 160


def character_sex(
    character: str, screenplay: Screenplay, extraction: Extraction
) -> tuple[Sex, str] | None:
    """The sex every source that gives one agrees on, with its evidence (T082): the grounded
    sex_word (its quote), the introduction's pronouns (that element), a sex title (the name).
    None when none gives one, or two disagree."""
    entity = _entity(character, extraction)
    sources: list[tuple[Sex, str]] = []
    if entity is not None and entity.sex is not None and entity.sex_quote is not None:
        sources.append((Sex(entity.sex), entity.sex_quote.text))
    if (intro := introduced_sex(character, screenplay)) is not None:
        found = _introduction(character, screenplay)
        sources.append((Sex(intro), found[0].text if found else character))
    if (title := title_sex(character)) is not None:
        sources.append((title, character))
    if not sources or len({sex for sex, _ in sources}) != 1:
        return None
    sex, evidence = sources[0]
    if len(evidence) > _EVIDENCE_MAX:
        evidence = evidence[:_EVIDENCE_MAX].rsplit(" ", 1)[0] + "…"
    return sex, evidence


def sex_part(
    character: str, screenplay: Screenplay, extraction: Extraction
) -> tuple[str, Span] | None:
    """The SEX part for a character the script sexes but gives no age (T082): "a female person"
    / "a male person", which claim no age, cited with the grounded quote's span or, for a title,
    the character's first located quote's. None when there is an age (AGE says it) or no span."""
    if _introduction(character, screenplay) is not None:
        return None
    found = character_sex(character, screenplay, extraction)
    entity = _entity(character, extraction)
    if found is None or entity is None:
        return None
    if entity.sex_quote is not None and entity.sex is not None:
        span = entity.sex_quote.span
    elif entity.quotes:
        span = entity.quotes[0].span
    else:
        return None
    return f"a {found[0].value} person", span


def introduced_years(character: str, screenplay: Screenplay) -> int | None:
    """The age in years the introduction gives (T086): `THEO (9)` -> 9, `DANIEL (40s)` -> 40;
    None when no introduction gives one. The audit checks a matched person's age against it."""
    found = _introduction(character, screenplay)
    return int(found[1].group(1)) if found else None


def introduced_age(
    character: str, screenplay: Screenplay, extraction: Extraction | None = None
) -> tuple[str, Span] | None:
    """The age the script gives where an Action line introduces `character` (T074): `LERATO (10)`
    -> "a 10-year-old", `MOKGOSI (70s)` -> "a person in their 70s", with that element's span; T079:
    with the sex `introduced_sex` reads, "a 10-year-old girl", "a man in his 70s"; T082: with an
    extraction, the sex `character_sex` gives. Only the parenthesis's own number and the code's
    fixed sex words."""
    found = _introduction(character, screenplay)
    if found is None:
        return None
    element, m = found
    number, decade = int(m.group(1)), m.group(2)
    if extraction is not None:
        agreed = character_sex(character, screenplay, extraction)
        sex = agreed[0].value if agreed is not None else None
    else:
        sex = introduced_sex(character, screenplay)
    young = number < 18
    noun = {
        "female": "girl" if young else "woman",
        "male": "boy" if young else "man",
    }.get(sex or "")
    if decade:
        own = {"female": "her", "male": "his"}.get(sex or "", "their")
        age = f"a {noun or 'person'} in {own} {number}s"
    else:
        age = f"a {number}-year-old" + (f" {noun}" if noun else "")
    return age, element.span


def _own_labels(character: str, screenplay: Screenplay, extraction: Extraction) -> dict[str, str]:
    """One character's labels; a planner name the extraction lacks still redacts as a name."""
    return redaction_labels(extraction, screenplay, only=character) or {
        token: "a person" for token in name_tokens([character])
    }


def build_frame_prompt(
    shot: Shot,
    screenplay: Screenplay,
    extraction: Extraction,
    style: Style,
    *,
    max_words: int,
    placement: str | None = None,
) -> FramePrompt:
    scene = screenplay.scenes[shot.scene_index]
    labels = redaction_labels(extraction, screenplay)
    visible = visible_characters(shot, screenplay, extraction)
    where = f"shot {shot.number} of scene {scene.number or scene.index + 1}"

    def script(text: str) -> str:
        # Redacted first, before any lower-casing: names are found by their capitals.
        return _script_text(text, labels)

    parts = [
        PromptPart(
            PartKind.STYLE,
            f"{style.medium}, {style.finish}" if style.finish else style.medium,
            None,
        ),
        PromptPart(PartKind.FRAMING, FRAMING_WORDS[shot.framing], None),
    ]
    if location := script(scene.location).lower():
        parts.append(
            PromptPart(
                PartKind.SETTING, f"{_PREPOSITIONS[scene.int_ext]} {location}", heading_span(scene)
            )
        )
    if shot.time_of_day is not None:
        source = time_source(screenplay.scenes, scene.index)
        clock = absolute_time(screenplay.scenes[source].time_of_day) if source is not None else None
        # The planner copies resolve_times' clock; any other value is not what the headings say.
        if source is None or clock is None or clock != shot.time_of_day.strip().upper():
            raise ValueError(
                f"{where}: time of day {shot.time_of_day!r} is not the clock its headings give "
                f"({clock!r})"
            )
        parts.append(
            PromptPart(
                # Not redacted: `absolute_time` already limits it to ABSOLUTE_TIMES, and a
                # character named DAWN must not turn the clock into "a person" (PR #27 review).
                PartKind.TIME,
                clock.lower(),
                heading_span(screenplay.scenes[source]),
            )
        )
    covered = {scene.elements[i].span for i in shot.elements}
    if visible:
        parts.append(PromptPart(PartKind.COUNT, _COUNTS.get(len(visible), _GROUP), None))
        for character in visible:  # T074, T079: each one's age, then look, as the script gives them
            if (age := introduced_age(character, screenplay, extraction)) is not None:
                parts.append(PromptPart(PartKind.AGE, age[0], age[1]))
            elif (sex := sex_part(character, screenplay, extraction)) is not None:
                parts.append(PromptPart(PartKind.SEX, sex[0], sex[1]))  # T082
            # Not when the shot covers that line: its ACTION part already says it, word for word.
            look = introduced_look(character, screenplay)
            if look is not None and look[1] not in covered:
                parts.append(PromptPart(PartKind.LOOK, script(look[0]), look[1]))
    if placement is not None:
        if placement not in PLACEMENT_PHRASES:
            raise ValueError(f"{where}: unknown placement {placement!r}")
        if len(visible) != 2:
            raise ValueError(
                f"{where}: a placement needs exactly two figures on screen, not {len(visible)}"
            )
        parts.append(PromptPart(PartKind.PLACEMENT, placement, None))

    fixed = _words([p for p in parts if p.kind is not PartKind.LOOK])
    if fixed > max_words:
        raise PromptError(
            f"{where}: the style, framing, setting, time and figure words alone are {fixed} "
            f"words, over the budget of {max_words}"
        )

    actions = _action_parts(shot, scene, visible, script, screenplay, extraction)
    # T079: looks give way to the budget, from the last character back, so the shot's action
    # keeps at least _ACTION_FLOOR words; a look never fails a render.
    while (k := [i for i, p in enumerate(parts) if p.kind is PartKind.LOOK]) and (
        _words(parts) > max_words - _ACTION_FLOOR
    ):
        del parts[k[-1]]
    actions, trimmed = _fit(actions, max_words - _words(parts))
    return FramePrompt(tuple(parts + actions), trimmed)


def _action_parts(
    shot: Shot,
    scene: Scene,
    visible: Sequence[str],
    script: Callable[[str], str],
    screenplay: Screenplay,
    extraction: Extraction,
) -> list[PromptPart]:
    """Each covered Action element's text, in order. T093: when every drawn person's sex is
    known, a sentence opening with a He or She none of them has is left out, and the element's
    kept sentences become one part per run, each with the element's span."""
    sexes = [character_sex(c, screenplay, extraction) for c in visible]
    drawn = {k[0] for k in sexes if k is not None} if visible and None not in sexes else None
    parts: list[PromptPart] = []
    for i in sorted(shot.elements):
        element = scene.elements[i]
        if not isinstance(element, Action) or not (text := script(element.text)):
            continue
        if drawn is None:
            parts.append(PromptPart(PartKind.ACTION, text, element.span))
            continue
        run: list[str] = []
        for piece, sex in pronoun_sentences(text):
            if sex is not None and sex not in drawn:
                if run:
                    parts.append(PromptPart(PartKind.ACTION, " ".join(run), element.span))
                run = []
            else:
                run.append(piece)
        if run:
            parts.append(PromptPart(PartKind.ACTION, " ".join(run), element.span))
    return parts


def _words(parts: Sequence[PromptPart]) -> int:
    # ", " joins parts without adding a word, so a prompt's words are its parts' words.
    return sum(len(p.text.split()) for p in parts)


def _fit(actions: list[PromptPart], budget: int) -> tuple[list[PromptPart], int]:
    """Drop whole parts from the tail, never the first; then cut the first to its longest prefix
    that fits, ending at a sentence end if one fits, else at a word; drop it if no word fits.
    Only script words are removed: what is kept is a verbatim prefix."""
    trimmed = 0
    while len(actions) > 1 and _words(actions) > budget:
        actions.pop()
        trimmed += 1
    if not actions or _words(actions) <= budget:
        return actions, trimmed
    words = actions[0].text.split()[: max(budget, 0)]
    ends = [
        k
        for k in range(len(words), 0, -1)
        if words[k - 1].rstrip(_CLOSERS).endswith((".", "!", "?"))
    ]
    cut = " ".join(words[: ends[0]] if ends else words)
    return ([replace(actions[0], text=cut)] if cut else []), trimmed + 1
