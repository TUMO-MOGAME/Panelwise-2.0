"""The grounding filter: only what the script says survives, each quote at a located span.

docs/design/grounding.md §4. Ported from FrameFlow's extraction_service (merge, filter) and
governance_service (faithfulness, recall), and changed where they failed:

* Filtering is per quote, not per entity. FrameFlow dropped an entity if any one quote failed,
  and lost its lead character to a single quote broken by a line-break hyphen.
* A quote must sit inside one element, so every kept quote has a span a panel can cite.
* Recall matches cues with `match_speaker` ("THABO" finds "THABO MOLEFE"); FrameFlow compared
  exact names. Speaking characters the model missed are added from the cues, but don't count
  toward the model's recall.
* Locations come from the scene headings: the parser already knows them exactly.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.characters.redact import NAME_STOP_WORDS, TITLE_WORDS, name_tokens
from app.characters.sex import CONFLICT_WORDS, PRONOUNS, SEX_WORDS, Sex
from app.grounding.model import Dropped, Entity, EntityKind, GroundingReport, Quote, Source
from app.grounding.schema import ProposedEntity
from app.grounding.text import (
    build_cue_index,
    build_index,
    locate_quote,
    normalize_for_grounding,
)
from app.script import Action, Dialogue, Screenplay, Span, match_speaker, normalise


def ground(
    proposals: Sequence[ProposedEntity], screenplay: Screenplay
) -> tuple[tuple[Entity, ...], GroundingReport]:
    index = build_index(screenplay)
    cues = build_cue_index(screenplay)
    script = normalize_for_grounding(screenplay.text)

    # Merge across chunks on (kind, name), keeping the first spelling and every distinct quote,
    # every proposed species in order, and every proposed other name.
    groups: dict[tuple[str, str], _Group] = {}
    for p in proposals:
        key = (p.kind, normalise(p.name))
        if not key[1]:
            continue
        group = groups.setdefault(key, _Group(p.name.strip(), EntityKind(p.kind)))
        seen = {normalize_for_grounding(q) for q in group.quotes}
        group.quotes.extend(q for q in p.quotes if normalize_for_grounding(q) not in seen)
        if p.species is not None:
            group.species.append(p.species)
        group.other_names.extend(p.other_names)
        if p.sex_word is not None:
            group.sex_words.append(p.sex_word)
    groups, bare_names = _fold_titled(groups, screenplay, script)

    # What a species may not be: a word for a person, or a word of a different character's name.
    actions = {e.span for sc in screenplay.scenes for e in sc.elements if isinstance(e, Action)}
    character_names = [g.name for g in groups.values() if g.kind is EntityKind.CHARACTER] + [
        e.cue for sc in screenplay.scenes for e in sc.elements if isinstance(e, Dialogue)
    ]

    kept: list[_Kept] = []
    dropped: list[Dropped] = []
    fully_grounded = quotes_total = quotes_located = 0
    for group in groups.values():
        name, kind, quotes = group.name, group.kind, group.quotes
        found = [f for q in quotes if (f := locate_quote(index, cues, q)) is not None]
        quotes_total += len(quotes)
        quotes_located += len(found)
        located = _unique(found)
        name_found = _mentions(script, name)
        # Every quote located, counted before `_unique` folds repeats into one.
        if name_found and found and len(found) == len(quotes):
            fully_grounded += 1
        if not name_found:
            dropped.append(Dropped(name, kind, "name not found in the script"))
        elif not located:
            dropped.append(Dropped(name, kind, "no quote found in the script"))
        else:
            kept.append(
                _Kept(
                    kind,
                    name,
                    located,
                    _species(group, located, actions, _not_species(name, character_names))
                    if kind is EntityKind.CHARACTER
                    else None,
                    _other_names(group, script),
                )
            )

    characters, recall_found, cues_total = _characters(kept, screenplay)
    # T082: a person's sex from a copied word; needs the whole cast, so after _characters.
    sex_words = {
        normalise(g.name): g.sex_words for g in groups.values() if g.kind is EntityKind.CHARACTER
    }
    names = _script_names(screenplay)
    characters = [
        _with_sex(
            c,
            sex_words.get(normalise(c.name), []),
            characters,
            actions,
            _claimed_sex(
                c,
                sex_words.get(normalise(c.name), []),
                characters,
                screenplay,
                names,
                openers=bare_names.get(normalise(c.name), ()),
            ),
        )
        for c in characters
    ]
    props = [
        Entity(
            EntityKind.PROP,
            k.name,
            tuple(k.quotes),
            _scenes(k.quotes),
            Source.MODEL,
            other_names=k.other_names,
        )
        for k in kept
        if k.kind is EntityKind.PROP
    ]
    entities = (
        *sorted(characters, key=_order),
        *sorted(props, key=_order),
        *_locations(screenplay),
    )
    proposed = len(groups)
    report = GroundingReport(
        entities_proposed=proposed,
        entities_grounded=fully_grounded,
        faithfulness=fully_grounded / proposed if proposed else 1.0,
        quotes_proposed=quotes_total,
        quotes_located=quotes_located,
        dropped=tuple(dropped),
        cues_total=cues_total,
        cues_found_by_model=recall_found,
        recall=recall_found / cues_total if cues_total else 1.0,
    )
    return entities, report


# A species names no person: the stop words (MAN, GIRL, OFFICER...) and these.
PERSON_WORDS = NAME_STOP_WORDS | frozenset(
    {
        "PERSON",
        "PEOPLE",
        "MEN",
        "WOMEN",
        "CHILD",
        "CHILDREN",
        "KID",
        "KIDS",
        "BABY",
        "TEENAGER",
        "FIGURE",
        "CROWD",
    }
)
_ARTICLE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)


@dataclass
class _Group:
    """One entity's proposals, merged across chunks."""

    name: str
    kind: EntityKind
    quotes: list[str] = field(default_factory=list[str])
    species: list[str] = field(default_factory=list[str])
    other_names: list[str] = field(default_factory=list[str])
    sex_words: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class _Kept:
    kind: EntityKind
    name: str
    quotes: list[Quote]
    species: str | None
    other_names: tuple[str, ...]


def _fold_titled(
    groups: dict[tuple[str, str], _Group], screenplay: Screenplay, script: str
) -> tuple[dict[tuple[str, str], _Group], dict[str, tuple[str, ...]]]:
    """A bare character name folds into the one titled spelling whose words are it plus forms of
    address: FORTUIN into MR. FORTUIN (grounding.md §3, T101). The spellings are the cues and the
    characters' names the script writes. No fold for a bare name the script cues itself, or one
    another name holds with more words than titles. Merged into an existing group in that group's
    place, else renamed in its own. Returns the groups and, per folded character, its bare names."""
    character = EntityKind.CHARACTER.value
    cues = [e.cue for sc in screenplay.scenes for e in sc.elements if isinstance(e, Dialogue)]
    names = [g.name for g in groups.values() if g.kind is EntityKind.CHARACTER]
    spellings: dict[str, str] = {}
    for name in [n for n in names if _mentions(script, n)] + cues:
        words = set(normalise(name).split())
        if words & TITLE_WORDS and words - TITLE_WORDS:
            spellings.setdefault(normalise(name), name.strip())
    cue_keys = {normalise(c) for c in cues}
    every = {normalise(n) for n in names + cues}
    folded = dict(groups)
    bare: dict[str, list[str]] = {}
    for key, group in groups.items():
        words = set(key[1].split())
        if key[0] != character or not words or words & TITLE_WORDS or key[1] in cue_keys:
            continue
        targets = [k for k in spellings if set(k.split()) - TITLE_WORDS == words]
        if len(targets) != 1 or any(words < set(n.split()) for n in every if n != targets[0]):
            continue
        target = (character, targets[0])
        if target in folded:
            del folded[key]
            into = folded[target]
            seen = {normalize_for_grounding(q) for q in into.quotes}
            into.quotes.extend(q for q in group.quotes if normalize_for_grounding(q) not in seen)
            into.species.extend(group.species)
            into.sex_words.extend(group.sex_words)
            into.other_names.extend([group.name, *group.other_names])
        else:
            renamed = replace(
                group, name=spellings[targets[0]], other_names=[group.name, *group.other_names]
            )
            folded = {
                (target if k == key else k): (renamed if k == key else g) for k, g in folded.items()
            }
        bare.setdefault(targets[0], []).append(group.name)
    return folded, {k: tuple(v) for k, v in bare.items()}


def _words(text: str) -> str:
    """Normalised, padded with spaces, so a whole-word test is a substring test."""
    return f" {' '.join(re.findall(r'[^\W_]+', normalize_for_grounding(text)))} "


def _not_species(name: str, character_names: Sequence[str]) -> frozenset[str]:
    """PERSON_WORDS, and the name tokens of every *other* character: a speaking animal cued CAT
    keeps `cat` (grounding.md §3)."""
    own = normalise(name)
    others = [
        n for n in character_names if match_speaker(n, [name]) is None and normalise(n) != own
    ]
    return PERSON_WORDS | name_tokens(others)


def _species(
    group: _Group, located: Sequence[Quote], actions: set[Span], not_species: frozenset[str]
) -> str | None:
    """The first proposed species that, without a leading article, is 1-3 words with a letter,
    names no person (`PERSON_WORDS`, any character's name token), and is whole words inside one
    of this entity's located quotes that sits in an Action element: a description, not someone's
    speech (grounding.md §3, T051)."""
    descriptions = [_words(q.text) for q in located if q.span in actions]
    for proposed in group.species:
        species = _ARTICLE.sub("", proposed.strip())
        words = _words(species)
        has_letter = any(c.isalpha() for c in words)
        if not has_letter or not 1 <= len(words.split()) <= 3 or set(words.split()) & not_species:
            continue
        if any(words in d for d in descriptions):
            return species
    return None


def _tokens(entity: Entity) -> frozenset[str]:
    return name_tokens([entity.name]) | name_tokens(entity.other_names)


def _quote_sex(word: str, quote: Quote, entity: Entity, cast: Sequence[Entity]) -> Sex | None:
    """The sex `word` gives in `quote` when every rule of grounding.md §3 (sex_word, 2a-e) holds:
    the word is a whole word of it; it names this character and no other (aliases, one's tokens
    containing the other's, excepted); a pronoun comes after this character's first mention;
    and every sex word in it agrees."""
    words = normalise(quote.text).split()
    own = _tokens(entity)
    mentions = [i for i, w in enumerate(words) if w in own]
    if not mentions:
        return None
    for other in cast:
        if other is entity or other.kind is not EntityKind.CHARACTER:
            continue
        theirs = _tokens(other)
        if theirs and not (theirs <= own or own <= theirs) and theirs & set(words):
            return None
    lower = word.strip().rstrip(".").lower()
    sex = SEX_WORDS.get(lower)
    found = [i for i, w in enumerate(words) if w.lower() == lower]
    if sex is None or not found:
        return None
    if lower in PRONOUNS and not any(i > mentions[0] for i in found):
        return None
    if {CONFLICT_WORDS[w.lower()] for w in words if w.lower() in CONFLICT_WORDS} != {sex}:
        return None
    return sex


def _with_sex(
    entity: Entity,
    proposed: Sequence[str],
    cast: Sequence[Entity],
    actions: set[Span],
    pronoun_sexes: Sequence[tuple[Sex, Quote]] = (),
) -> Entity:
    """The entity with the sex its copied words ground, all agreeing (grounding.md §3, T082);
    T088: and its checked pronoun sentences, after them. Unchanged for an animal, a CUE backfill
    or no proposal."""
    if entity.species is not None or entity.source is not Source.MODEL:
        return entity
    kept: list[tuple[Sex, Quote]] = []
    for word in proposed:
        for quote in entity.quotes:
            if quote.span in actions and (sex := _quote_sex(word, quote, entity, cast)):
                kept.append((sex, quote))
                break
    kept.extend(pronoun_sexes)
    if not kept or len({sex for sex, _ in kept}) != 1:
        return entity
    return replace(entity, sex=kept[0][0], sex_quote=kept[0][1])


# T088: the pronoun evidence for a claimed sex. Pronouns, and the words that stop a stretch: another
# possible owner of the pronoun stands between the name and it.
_PERSON_PRONOUNS = frozenset({"he", "him", "his", "himself", "she", "her", "hers", "herself"})
_POSSESSIVES = frozenset({"his", "her", "hers", "their", "theirs", "my", "your", "our"})
_DETERMINERS = frozenset({"a", "an", "the", "this", "that", "these", "those", "another", "some"})
# After "her", a word that makes it an object ("hands her the box"), not a possessive. Public
# (T100): storyboard's introduced_sex reads a sentence-opening Her the same way.
NOT_POSSESSED = frozenset(
    {
        "a", "an", "the", "to", "and", "or", "but", "in", "on", "at", "by", "for", "from", "with",
        "of", "into", "onto", "up", "down", "back", "out", "off", "over", "away", "again", "too",
        "gently", "slowly", "softly", "close", "closer", "go", "be", "that", "this", "it", "as",
        "so", "if", "once", "twice", "all",
    }
)  # fmt: skip
# A sentence ends at . ! ? and whitespace, never after a title's abbreviation ("Mr. Dube").
SENTENCE_END = re.compile(r"(?<=[.!?])(?<!\bMr\.)(?<!\bMrs\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)\s+")
_WORD = re.compile(r"[A-Za-z']+")
# An introduction's own description, dropped first: "DANIEL (40s), a tall driver, climbs out."
# reads as "DANIEL climbs out.", so its "a" is no unnamed person.
_INTRODUCTION = re.compile(r"([A-Za-z.']+)\s*\([^)]*\)(?:\s*,[^,.;!?]*,)?")
# A screenplay's names: an all-caps cue or `NAME (` introduction.
_INTRODUCED_NAME = re.compile(r"(?<![A-Za-z])([A-Z][A-Z'. -]*[A-Z])\s*\(")


def _script_names(screenplay: Screenplay) -> frozenset[str]:
    """Every name word the script itself writes (T088): its dialogue cues and `NAME (`
    introductions, normalised, stop words out. A name the extraction missed is still a name."""
    names: set[str] = set()
    for scene in screenplay.scenes:
        for element in scene.elements:
            if isinstance(element, Dialogue):
                names.update(normalise(element.cue).split())
            else:
                names.update(
                    w
                    for m in _INTRODUCED_NAME.finditer(element.text)
                    for w in normalise(m.group(1)).split()
                )
    return frozenset(names - NAME_STOP_WORDS)


def _title_case(word: str) -> bool:
    """A word written as a name is ("Lerato"): a capital, then lower case. A prop in capitals
    (RED KITE) is not one."""
    return word[:1].isupper() and word[1:].islower()


def _opens_with(words: Sequence[str], name: Sequence[str]) -> int | None:
    """Where the words after a sentence-opening name begin (an optional "The" first), or None."""
    start = 1 if words[:1] and words[0].lower() == "the" else 0
    return (
        start + len(name)
        if [normalise(w) for w in words[start : start + len(name)]] == list(name)
        else None
    )


def _first_opening(words: Sequence[str], starts: Sequence[Sequence[str]]) -> int | None:
    """`_opens_with` for the first of the names a sentence opens with (T101), or None."""
    return next((end for name in starts if (end := _opens_with(words, name)) is not None), None)


def _clear(words: Sequence[str], own: frozenset[str], others: frozenset[str]) -> bool:
    """No other possible owner of a pronoun among `words` (T088): another name (the cast's, the
    script's, or any Title-case word), a possessive, a determiner or a sex noun."""
    for word in words:
        low, key = word.lower(), normalise(word)
        if key in own:
            continue
        if low.endswith("'s") or low in _POSSESSIVES or low in _DETERMINERS:
            return False
        if low in SEX_WORDS and low not in PRONOUNS:
            return False
        if word[:1].isupper() and (
            key in others or (_title_case(word) and key not in NAME_STOP_WORDS)
        ):
            return False
    return True


def _owned(rest: Sequence[str]) -> Sex | None:
    """The sex the first third-person pronoun after a sentence's subject gives, when it is the
    subject's own: his, himself, herself, or a possessive her. He, she, him and an object her
    give nothing here."""
    for k, word in enumerate(rest):
        low = word.lower()
        if low not in _PERSON_PRONOUNS:
            continue
        if low in ("his", "himself"):
            return Sex.MALE
        if low == "herself":
            return Sex.FEMALE
        following = rest[k + 1].lower() if k + 1 < len(rest) else ""
        if low == "her" and following and following not in NOT_POSSESSED:
            return Sex.FEMALE
        return None
    return None


def _pronoun_evidence(
    entity: Entity,
    cast: Sequence[Entity],
    screenplay: Screenplay,
    names: frozenset[str],
    openers: Sequence[str] = (),
) -> list[tuple[Sex, Quote]]:
    """`_pronoun_pieces` without the flag (T088's evidence; grounding.md §6)."""
    return [
        (sex, quote) for sex, quote, _ in _pronoun_pieces(entity, cast, screenplay, names, openers)
    ]


def _pronoun_pieces(
    entity: Entity,
    cast: Sequence[Entity],
    screenplay: Screenplay,
    names: frozenset[str],
    openers: Sequence[str] = (),
) -> list[tuple[Sex, Quote, bool]]:
    """Every place an Action sentence's pronoun is plainly this character's (grounding.md §3,
    T088): a sentence opening with the name whose first pronoun after it is the subject's own
    with nothing that could own it between ("Koos taps his broom."), or a sentence opening with
    He or She right after a sentence of the same element (or the last of the Action element just
    before) that opens with the name and holds no other possible owner ("Siphokazi nods. She
    cannot stop the smile."). A speech between breaks the chain: a pronoun after one is often the
    listener's. Each piece says whether its sentence's subject owns the pronoun (T091): True for
    the first kind, False for a He or She opening the next sentence. T101: a sentence may also
    open with one of `openers`, the bare names folded into this character."""
    starts = [normalise(n).split() for n in (entity.name, *openers)]
    own = _tokens(entity)
    others = (names | {t for c in cast if c is not entity for t in _tokens(c)}) - own
    found: list[tuple[Sex, Quote, bool]] = []
    for scene_index, scene in enumerate(screenplay.scenes):
        previous: list[str] | None = None
        for element in scene.elements:
            if not isinstance(element, Action):
                previous = None
                continue
            # The quote is the script's own sentence; only its words are read with an
            # introduction's description left out.
            for sentence in (s for s in SENTENCE_END.split(element.text) if _WORD.search(s)):
                words = _WORD.findall(_INTRODUCTION.sub(r"\1", sentence))
                end = _first_opening(words, starts)
                quote = Quote(sentence.strip(), scene_index, element.span)
                if end is not None and (sex := _owned(words[end:])) is not None:
                    pronoun = next(
                        i for i, w in enumerate(words[end:]) if w.lower() in _PERSON_PRONOUNS
                    )
                    if _clear(words[end : end + pronoun], own, others):
                        found.append((sex, quote, True))
                if words[:1] in (["He"], ["She"]) and previous is not None:
                    before = _first_opening(previous, starts)
                    if before is not None and _clear(previous[before:], own, others):
                        found.append((Sex.MALE if words[0] == "He" else Sex.FEMALE, quote, False))
                previous = words
    return found


def _claimed_sex(
    entity: Entity,
    proposed: Sequence[str],
    cast: Sequence[Entity],
    screenplay: Screenplay,
    names: frozenset[str],
    openers: Sequence[str] = (),
) -> list[tuple[Sex, Quote]]:
    """The sex the model claims with its sex_word, kept when the script's own pronouns support it
    and none contradicts it (grounding.md §3, T088), with the first supporting sentence as the
    quote. With no claim at all (T091), the evidence alone: every piece one sex and at least one
    sentence whose subject owns the pronoun, that sentence the quote. Else nothing; never for an
    animal or a CUE backfill."""
    if entity.species is not None or entity.source is not Source.MODEL:
        return []
    # A claim may be a possessive too (his, her): only T088's evidence keeps it, never the word.
    claims = {CONFLICT_WORDS.get(w.strip().rstrip(".").lower()) for w in proposed} - {None}
    if len(claims) > 1:
        return []
    if not claims:  # T091: a next-sentence He/She alone keeps nothing without a claim
        pieces = _pronoun_pieces(entity, cast, screenplay, names, openers)
        sexes = {sex for sex, _, _ in pieces}
        owning = [quote for _, quote, owns in pieces if owns]
        return [(sexes.pop(), owning[0])] if len(sexes) == 1 and owning else []
    claim = next(iter(claims))
    assert claim is not None
    evidence = _pronoun_evidence(entity, cast, screenplay, names, openers)
    support = [quote for sex, quote in evidence if sex is claim]
    if not support or any(sex is not claim for sex, _ in evidence):
        return []
    return [(claim, support[0])]


def _other_names(group: _Group, script: str) -> tuple[str, ...]:
    """Other names the script mentions as whole words, not the entity's name, with a name token
    (grounding.md §3, T051). In first-proposed order, once each."""
    kept: dict[str, str] = {}
    for other in group.other_names:
        key = normalise(other)
        if (
            key
            and key != normalise(group.name)
            and key not in kept
            and name_tokens([other])
            and _mentions(script, other)
        ):
            kept[key] = other.strip()
    return tuple(kept.values())


def _unique(found: Sequence[tuple[str, int, Span]]) -> list[Quote]:
    """One Quote per text and span: `"LERATO\\nI promise."` and `"I promise."` keep the same
    text at the same speech once the cue is stripped."""
    seen: set[tuple[str, Span]] = set()
    quotes: list[Quote] = []
    for text, scene_index, span in found:
        key = (normalize_for_grounding(text), span)
        if key not in seen:
            seen.add(key)
            quotes.append(Quote(text, scene_index, span))
    return quotes


def _mentions(script: str, name: str) -> bool:
    needle = normalize_for_grounding(name)
    return bool(needle) and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", script) is not None


def _scenes(quotes: Sequence[Quote], extra: Sequence[int] = ()) -> tuple[int, ...]:
    return tuple(sorted({q.scene_index for q in quotes} | set(extra)))


def _order(entity: Entity) -> tuple[int, str]:
    return (entity.scenes[0] if entity.scenes else 0, entity.name)


def _characters(kept: Sequence[_Kept], screenplay: Screenplay) -> tuple[list[Entity], int, int]:
    """Grounded model characters with the scenes they speak in, plus the speakers the model
    missed. Returns (characters, cues found by the model, cues in the script)."""
    names = [k.name for k in kept if k.kind is EntityKind.CHARACTER]

    # Every speech: which distinct cue it is, and which model character (if any) it belongs to.
    speaking: dict[str, list[tuple[int, Dialogue]]] = {}
    for scene in screenplay.scenes:
        for element in scene.elements:
            if isinstance(element, Dialogue) and normalise(element.cue):
                speaking.setdefault(normalise(element.cue), []).append((scene.index, element))
    owner = {cue: match_speaker(cue, names) for cue in speaking}

    characters: list[Entity] = []
    for k in kept:
        if k.kind is not EntityKind.CHARACTER:
            continue
        spoke = [
            i for cue, speeches in speaking.items() if owner[cue] == k.name for i, _ in speeches
        ]
        characters.append(
            Entity(
                EntityKind.CHARACTER,
                k.name,
                tuple(k.quotes),
                _scenes(k.quotes, spoke),
                Source.MODEL,
                species=k.species,
                other_names=k.other_names,
            )
        )

    for cue, speeches in speaking.items():
        if owner[cue] is not None:
            continue
        scene_index, first = speeches[0]
        quote = Quote(first.text, scene_index, first.span)
        characters.append(
            Entity(
                EntityKind.CHARACTER,
                first.cue,
                (quote,),
                tuple(sorted({i for i, _ in speeches})),
                Source.CUE,
            )
        )
    found = sum(1 for cue in speaking if owner[cue] is not None)
    return characters, found, len(speaking)


def _locations(screenplay: Screenplay) -> list[Entity]:
    groups: dict[str, tuple[str, list[Quote]]] = {}
    for scene in screenplay.scenes:
        key = normalise(scene.location)
        if not key:
            continue
        heading = Quote(
            scene.heading,
            scene.index,
            Span(scene.span.page, scene.span.line_start, scene.span.line_start),
        )
        groups.setdefault(key, (scene.location, []))[1].append(heading)
    return [
        Entity(EntityKind.LOCATION, name, tuple(quotes), _scenes(quotes), Source.HEADING)
        for name, quotes in groups.values()
    ]
