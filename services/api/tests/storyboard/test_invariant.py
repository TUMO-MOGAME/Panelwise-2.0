"""Non-negotiable I on the input to the image model: storyboard.md §3.1's invariant, §9.

Over every self-written sample in samples/, every shot a planner could make (every consecutive
run of elements in every scene: a superset of any real plan), every public style, and two word
budgets (the default and one that trims nothing): every script part of the prompt cites this
shot's heading, the heading its clock came from, or an element the shot covers, and says only
what that redacted line says. No name, no dialogue, no parenthetical, no rationale.
"""

import re
from collections.abc import Iterator
from functools import cache
from itertools import cycle, pairwise

import pytest

from app.characters import name_tokens, redact_all
from app.characters.sex import CONFLICT_WORDS, SEX_TITLES
from app.grounding import EntityKind, Extraction, normalize_for_grounding
from app.script import ABSOLUTE_TIMES, Action, Dialogue, Screenplay, Span, parse_pdf, resolve_times
from app.shots import Framing, Shot
from app.shots.planner import named_in_action
from app.storyboard import (
    FRAMING_WORDS,
    PUBLIC_STYLES,
    FramePrompt,
    PartKind,
    Style,
    build_frame_prompt,
    introduced_age,
    introduced_look,
    load_styles,
    visible_characters,
)
from tests.storyboard.conftest import SENTINEL_RATIONALE, extraction_of, shot_of
from tools.build_samples import SAMPLES

K = PartKind
DEFAULT_BUDGET = 55
NO_BUDGET = 10_000
COUNTS = {"one figure", "two figures", "three figures", "four figures", "a group of figures"}
PREPOSITIONS = {"inside", "outside", "at"}

# Characters the samples name in action without ever giving them a cue; the cues supply the rest.
NON_SPEAKERS: dict[str, list[tuple[str, str]]] = {
    "the-red-kite": [],
    "lost-property": [("MARMALADE", "A ginger cat, MARMALADE, sleeps on a pile of lost scarves.")],
    "sipho-and-siphokazi": [],
}
PUBLIC = load_styles(PUBLIC_STYLES, None).public()


@cache
def sample(name: str) -> tuple[Screenplay, Extraction]:
    screenplay = parse_pdf((SAMPLES / f"{name}.pdf").read_bytes())
    return screenplay, extraction_of(screenplay, NON_SPEAKERS[name])


def characters(extraction: Extraction) -> list[str]:
    return [e.name for e in extraction.entities if e.kind is EntityKind.CHARACTER]


def every_shot(
    screenplay: Screenplay, extraction: Extraction, *, backfilled: bool = False
) -> Iterator[Shot]:
    """Every range of every scene. `backfilled` (T092): each shot's cast gains the characters
    its covered action lines name, as the planner adds them."""
    times = resolve_times(screenplay.scenes)
    framings = cycle(Framing)
    for scene in screenplay.scenes:
        cast = [
            e.name
            for e in extraction.entities
            if e.kind is EntityKind.CHARACTER and scene.index in e.scenes
        ]
        n = len(scene.elements)
        # named_in_action over a range is the union over its elements, in extraction order.
        each: list[set[str]] = [
            set(named_in_action(scene, [i], extraction, screenplay)) if backfilled else set[str]()
            for i in range(n)
        ]
        order = [e.name for e in extraction.entities]
        for first in range(n):
            for last in range(first, n):
                covered = range(first, last + 1)
                named = sorted(set[str]().union(*each[first : last + 1]), key=order.index)
                own = [*cast, *(c for c in named if c not in cast)]
                yield shot_of(
                    screenplay, scene.index, covered, characters=own,
                    time_of_day=times[scene.index], framing=next(framings),
                    rationale=SENTINEL_RATIONALE,
                )  # fmt: skip


def clock_heading(screenplay: Screenplay, scene_index: int) -> Span | None:
    """Worked out here from the headings, independently of the code under test."""
    for scene in reversed(screenplay.scenes[: scene_index + 1]):
        if (scene.time_of_day or "").strip().upper() in ABSOLUTE_TIMES:
            return Span(scene.span.page, scene.span.line_start, scene.span.line_start)
    return None


def heading_line(screenplay: Screenplay, span: Span) -> str:
    return screenplay.text.split("\n")[span.line_start - 1]


def norm(text: str) -> str:
    return normalize_for_grounding(text)


_SEX_NOUNS = {"girl": "female", "woman": "female", "her": "female", "female": "female",
              "boy": "male", "man": "male", "his": "male", "male": "male"}  # fmt: skip
_PRONOUNS = {"she": "female", "her": "female", "he": "male", "his": "male"}


def keyed(text: str, character: str, intro: str | None, extraction: Extraction) -> bool:
    """T082: the sex word in an AGE or SEX part is keyed by a word of the script: a pronoun of the
    introducing line, a sex title as the name's first word, a sex noun before the name in the
    introducing line (T096), or the grounded sex_quote holding a vocabulary word of that sex. A
    part with no sex word is keyed trivially."""
    said = {_SEX_NOUNS[w] for w in re.findall(r"[a-z]+", text) if w in _SEX_NOUNS}
    if not said:
        return True
    assert len(said) == 1, text
    sex = said.pop()
    if intro is not None and sex in {
        _PRONOUNS[w] for w in re.findall(r"[a-z]+", intro.lower()) if w in _PRONOUNS
    }:
        return True
    words = re.sub(r"[^A-Z ]", " ", character.upper()).split()
    if words and SEX_TITLES.get(words[0]) == sex:
        return True
    # T096: a sex noun of that sex in the introducing line, before the name ("A boy …, THABO (9)").
    if intro is not None:
        before = intro.split(character, 1)[0].lower()
        if sex in {_SEX_NOUNS[w] for w in re.findall(r"[a-z]+", before) if w in _SEX_NOUNS}:
            return True
    entity = next((e for e in extraction.entities if e.name == character), None)
    if entity is not None and entity.sex_quote is not None and entity.sex == sex:
        quoted = re.findall(r"[a-z]+", entity.sex_quote.text.lower())
        # T088: a sex_quote from sex_pronoun_quote may hold only his, her, him or hers.
        return any(CONFLICT_WORDS.get(w) == sex for w in quoted)
    return False


@cache
def redacted(text: str, names: tuple[str, ...]) -> str:
    """`redact_all`, normalised, once per text: the same lines are checked for every shot that
    covers them, and redacting them again each time made this file take minutes."""
    return norm(redact_all(text, list(names)))


def check(
    prompt: FramePrompt,
    shot: Shot,
    screenplay: Screenplay,
    extraction: Extraction,
    style: Style,
    max_words: int,
) -> None:
    scene = screenplay.scenes[shot.scene_index]
    names = tuple(characters(extraction))
    heading = Span(scene.span.page, scene.span.line_start, scene.span.line_start)
    covered = {scene.elements[i].span: scene.elements[i] for i in shot.elements}
    fixed = {
        K.STYLE: {f"{style.medium}, {style.finish}"},
        K.FRAMING: set(FRAMING_WORDS.values()),
        K.COUNT: COUNTS,
    }
    where = f"shot {shot.scene_index}.{shot.elements}"

    for part in prompt.parts:
        if part.span is None:
            assert part.text in fixed.get(part.kind, set()), f"{where}: unspanned {part}"
            continue
        text = part.text
        if part.kind is K.SETTING:
            assert part.span == heading, where
            preposition, text = text.split(" ", 1)
            assert preposition in PREPOSITIONS, where
            source = heading_line(screenplay, heading)
        elif part.kind is K.TIME:
            assert part.span == clock_heading(screenplay, scene.index), where
            # A closed vocabulary, never redacted: the clock word itself, from that heading.
            assert text.upper() in ABSOLUTE_TIMES, where
            assert norm(text) in norm(heading_line(screenplay, part.span)), where
            continue
        elif part.kind is K.AGE:
            # T074: the line that introduces one of the shot's visible characters, and the age's
            # number in a parenthesis right after that character's name there.
            visible = visible_characters(shot, screenplay, extraction)
            # Two characters can share an age phrase and a line: keep every name for each.
            names_for: dict[tuple[str, Span], list[str]] = {}
            for c in visible:
                if (age := introduced_age(c, screenplay, extraction)) is not None:
                    names_for.setdefault(age, []).append(c)
            assert (part.text, part.span) in names_for, f"{where}: {part} introduces no one shown"
            name = names_for[(part.text, part.span)][0]
            number = re.search(r"\d+", part.text)
            assert number is not None, where
            line = next(
                e.text for s in screenplay.scenes for e in s.elements if e.span == part.span
            )
            assert re.search(rf"{re.escape(name)}\s*\(\s*{number.group()}", line), where
            assert any(
                keyed(text, c, line, extraction) for c in names_for[(part.text, part.span)]
            ), f"{where}: {part}'s sex word is keyed by no word of the script"
            continue
        elif part.kind is K.SEX:
            # T082: a sexed character with no age; the code's phrase, cited with the grounded
            # quote's span or, for a title, the character's first located quote's.
            assert text in {"a female person", "a male person"}, f"{where}: {part}"
            visible = visible_characters(shot, screenplay, extraction)
            owners = [
                c
                for c in visible
                for e in extraction.entities
                if e.name == c
                and part.span in {e.quotes[0].span, *([e.sex_quote.span] if e.sex_quote else [])}
            ]
            assert owners, f"{where}: {part} cites no sexed character shown"
            assert any(keyed(text, c, None, extraction) for c in owners), f"{where}: {part}"
            continue
        elif part.kind is K.LOOK:
            # T079: the line that introduces one of the shot's visible characters; each of the
            # look's comma items is a verbatim, redacted piece of that line.
            visible = visible_characters(shot, screenplay, extraction)
            spans = {look[1] for c in visible if (look := introduced_look(c, screenplay))}
            assert part.span in spans, f"{where}: {part} introduces no one shown"
            line = next(
                e.text for s in screenplay.scenes for e in s.elements if e.span == part.span
            )
            for item in text.split(", "):
                assert norm(item) in redacted(line, names), f"{where}: {part}"
            continue
        elif part.kind is K.ACTION:
            element = covered.get(part.span)
            assert isinstance(element, Action), f"{where}: {part} cites no covered action"
            source = element.text
        else:
            raise AssertionError(f"{where}: a {part.kind} part with a span")
        assert norm(text) in redacted(source, names), f"{where}: {part}"

    whole = prompt.text()
    # No name, in the form screenplays write names (a lower-case common word is not one).
    tokens = name_tokens(names)
    named = [w for w in re.findall(r"\w+", whole) if w.upper() in tokens and w[0].isupper()]
    assert not named, f"{where}: names {named} in {whole!r}"
    # No speech and no parenthetical, from anywhere in the script, unless a covered action line
    # happens to say the same words (both redacted: "Van Wyk." and "VAN WYK" are "a person").
    actions = " | ".join(redacted(e.text, names) for e in covered.values() if isinstance(e, Action))
    for other in screenplay.scenes:
        for element in other.elements:
            if not isinstance(element, Dialogue):
                continue
            for said in (element.text, element.parenthetical or ""):
                if len(said.split()) >= 2 and redacted(said, names) not in actions:
                    assert redacted(said, names) not in norm(whole), f"{where}: {said!r}"
    assert norm(SENTINEL_RATIONALE) not in norm(whole)
    assert len(whole.split()) <= max_words


@pytest.mark.parametrize("budget", [DEFAULT_BUDGET, NO_BUDGET])
@pytest.mark.parametrize("style", PUBLIC, ids=[s.key for s in PUBLIC])
@pytest.mark.parametrize("name", sorted(NON_SPEAKERS))
def test_every_script_part_of_every_prompt_cites_this_shot(
    name: str, style: Style, budget: int
) -> None:
    screenplay, extraction = sample(name)
    shots = 0
    for shot in every_shot(screenplay, extraction):
        prompt = build_frame_prompt(shot, screenplay, extraction, style, max_words=budget)
        check(prompt, shot, screenplay, extraction, style, budget)
        shots += 1
    assert shots > 0


@pytest.mark.parametrize("name", sorted(NON_SPEAKERS))
def test_the_invariant_holds_on_backfilled_casts(name: str) -> None:
    """T092: the planner adds whoever a covered action line names; the prompt still cites only
    this shot."""
    screenplay, extraction = sample(name)
    shots = 0
    for shot in every_shot(screenplay, extraction, backfilled=True):
        prompt = build_frame_prompt(
            shot, screenplay, extraction, PUBLIC[0], max_words=DEFAULT_BUDGET
        )
        check(prompt, shot, screenplay, extraction, PUBLIC[0], DEFAULT_BUDGET)
        shots += 1
    assert shots > 0


def test_the_samples_cover_what_the_invariant_must_see() -> None:
    """A CONTINUOUS scene after a night scene (a borrowed clock), a heading with no time, a
    possessive name in a heading, V.O. and O.S. speakers, and parentheticals."""
    red_kite, _ = sample("the-red-kite")
    lost, _ = sample("lost-property")
    sipho, _ = sample("sipho-and-siphokazi")
    times = [s.time_of_day for s in lost.scenes]
    assert any(a == "NIGHT" and b == "CONTINUOUS" for a, b in pairwise(times))
    assert any(s.time_of_day is None for s in sipho.scenes)
    assert any("'S " in s.location for s in (*red_kite.scenes, *sipho.scenes))
    speeches = [e for s in red_kite.scenes for e in s.elements if isinstance(e, Dialogue)]
    assert {"V.O.", "O.S."} <= {d.extension for d in speeches}
    assert any(d.parenthetical for d in speeches)


def test_budgeted_prompts_really_are_trimmed_somewhere() -> None:
    """The default budget must exercise the trimming path, or the invariant never saw a cut."""
    screenplay, extraction = sample("lost-property")
    trimmed = [
        build_frame_prompt(s, screenplay, extraction, PUBLIC[0], max_words=DEFAULT_BUDGET).trimmed
        for s in every_shot(screenplay, extraction)
    ]
    assert any(trimmed)
