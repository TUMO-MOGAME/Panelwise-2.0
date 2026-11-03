"""Which label each name becomes in an image prompt: storyboard.md §3.1 Labels (T052).

A person is "a person", an animal "the <species>", a named prop's other name "the <prop name>",
and anything unsure "it": no label adds a person or a thing the script doesn't have. Its own
module because it reads the extraction, and app.grounding's filter imports redact.py: so
app/characters/__init__.py must never import this one, or the two packages import in a circle.
"""

import re
from collections.abc import Sequence

from app.characters.redact import name_tokens
from app.grounding import Entity, EntityKind, Extraction, normalize_for_grounding
from app.script import Screenplay, match_speaker

_ARTICLE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)
_PERSON, _ANIMAL, _PROP, _IT = range(4)


def animals(extraction: Extraction) -> dict[str, str]:
    """Character name -> species, for every animal: its own species, or a species-less entry
    (a cue backfill, a second spelling) that `match_speaker` binds to an animal's name."""
    # Asked per shot and per character; held by identity like _scene_words, a copy returned.
    entry = _animals_cache[0] if _animals_cache else None
    if entry is not None and entry[0] is extraction:
        return dict(entry[1])
    found = _find_animals(extraction)
    _animals_cache[:] = [(extraction, found)]
    return dict(found)


_animals_cache: list[tuple[Extraction, dict[str, str]]] = []


def _find_animals(extraction: Extraction) -> dict[str, str]:
    characters = [e for e in extraction.entities if e.kind is EntityKind.CHARACTER]
    own = {e.name: e.species for e in characters if e.species}
    out: dict[str, str] = {}
    for e in characters:
        if e.species:
            out[e.name] = e.species
        elif (bound := match_speaker(e.name, list(own))) is not None:
            out[e.name] = own[bound]
    return out


def redaction_labels(
    extraction: Extraction, screenplay: Screenplay, only: str | None = None
) -> dict[str, str]:
    """Name token -> label, in rank order: persons, animals, named props, `it`, and extraction
    order within each. A token goes to the first label that claims it. `only` keeps one
    character's name and paired other names (`visible_characters` asks about one at a time)."""
    beings = animals(extraction)
    named = [e for e in extraction.entities if e.kind in (EntityKind.CHARACTER, EntityKind.PROP)]
    every_name = [e.name for e in named if e.kind is EntityKind.CHARACTER] + [
        o for e in named for o in e.other_names
    ]
    scenes = _scene_words(screenplay)
    entries: list[tuple[int, int, list[str], str]] = []
    for order, e in enumerate(named):
        if only is not None and e.name != only:
            continue
        paired = [o for o in e.other_names if _paired(o, e, beings.get(e.name), scenes)]
        unpaired = [o for o in e.other_names if o not in paired]
        if e.kind is EntityKind.CHARACTER:
            rank = _ANIMAL if e.name in beings else _PERSON
            words = beings[e.name] if e.name in beings else ""
            label = _label(words, e, every_name) if words else "a person"
            entries.append((rank, order, [e.name, *paired], label))
        elif paired:
            entries.append((_PROP, order, paired, _label(_ARTICLE.sub("", e.name), e, every_name)))
        if only is None and unpaired:
            entries.append((_IT, order, unpaired, "it"))
    labels: dict[str, str] = {}
    for _, _, names, label in sorted(entries, key=lambda x: (x[0], x[1])):
        for token in sorted(name_tokens(names)):
            labels.setdefault(token, label)
    return labels


def _label(words: str, entity: Entity, every_name: Sequence[str]) -> str:
    """`the <words>`, lower-cased -- or `it` when the words hold another name's token, so a
    lower-cased label never carries a name past `names_in` ("NANDI'S UMBRELLA")."""
    # Only a character's own name is exempt (a speaking animal cued CAT is "the cat"); a prop's
    # name is the label itself, so exempting it would let NANDI through.
    own = name_tokens([entity.name] if entity.kind is EntityKind.CHARACTER else [])
    others = name_tokens(every_name) - own
    if set(name_tokens([words])) & others:
        return "it"
    return f"the {' '.join(words.split()).lower()}"


def _words(text: str) -> str:
    return f" {' '.join(re.findall(r'[^\W_]+', normalize_for_grounding(text)))} "


# The last screenplay's scene words: a prompt run asks for labels once per shot and character,
# and re-normalising a whole feature each time would be quadratic in its length (PR #43 review).
# Held by identity, with the screenplay itself, so a new screenplay never reads a stale entry.
_cache: list[tuple[Screenplay, list[str]]] = []


def _scene_words(screenplay: Screenplay) -> list[str]:
    """Each scene's heading and element text, as padded words for whole-word tests."""
    entry = _cache[0] if _cache else None  # one read: another thread may replace it
    if entry is not None and entry[0] is screenplay:
        return entry[1]
    words = [
        _words(" ".join([scene.heading, *(e.text for e in scene.elements)]))
        for scene in screenplay.scenes
    ]
    _cache[:] = [(screenplay, words)]
    return words


def _paired(other: str, entity: Entity, species: str | None, scenes: list[str]) -> bool:
    """The other name shares a scene with the entity: its name, its species, or one of its
    located quotes (storyboard.md §3.1 Pairing)."""
    needle = _words(other)
    marks = [_words(entity.name)] + ([_words(species)] if species else [])
    quoted = {q.scene_index for q in entity.quotes}
    return any(
        needle in text and (i in quoted or any(m in text for m in marks))
        for i, text in enumerate(scenes)
    )
