"""Taking character names out of text before it enters an image prompt. docs/design/characters.md
§3 rules 1 and 2, storyboard.md §3.1.

An image model reads a name as a likeness cue, and screenplays introduce characters by name inside
the very lines a frame is drawn from ("NANDI (60s, oilskin coat) pours tea"). So every name is
replaced, and nothing else changes: redaction only removes words. Names are matched the way
screenplays write them, in UPPER or Title case as whole words; a lower-case "will" is a verb, not
WILL. A cue made only of words that aren't names on their own (THE STRANGER) redacts nothing, or
every "The" would become a person.
"""

import re
from collections.abc import Callable, Collection, Mapping, Sequence

from app.script import normalise

NAME_STOP_WORDS = frozenset(
    {
        "THE",
        "A",
        "AN",
        "OLD",
        "YOUNG",
        "LITTLE",
        "BIG",
        "MR",
        "MRS",
        "MS",
        "MISS",
        "DR",
        "SIR",
        "LADY",
        "MAN",
        "WOMAN",
        "BOY",
        "GIRL",
        "STRANGER",
        "OFFICER",
        "NURSE",
        "DOCTOR",
    }
)

# Forms of address: stop words on their own, but redacted with the name they precede, so
# "MR. DUBE" becomes "a person", not "MR. a person" (T050, storyboard.md §3.1).
TITLE_WORDS = frozenset(
    {"MR", "MRS", "MS", "MISS", "DR", "SIR", "LADY", "OFFICER", "NURSE", "DOCTOR"}
)
# Only abbreviations take a full stop: "the OFFICER. Moloi turns" is a sentence end, not a title.
_ABBREVIATIONS = frozenset({"MR", "MRS", "MS", "DR"})

# Lower-case words that join a name's run between two name words when they are its tokens (T092,
# storyboard.md §3.1): "Mr. Van der Merwe" is one run, not "a person der a person".
NAME_PARTICLES = frozenset(
    {"van", "der", "de", "du", "da", "von", "le", "la", "del", "dos", "den", "ter", "bin"}
)

# Word characters except U+02BC, the modifier-letter apostrophe that \w counts as a letter:
# NANDI\u02bcS must tokenise as NANDI then S, like NANDI'S (PR #27 review).
_WORD = re.compile(r"[^\W\u02bc]+")
_APOSTROPHES = frozenset({"'", "\u2019", "\u02bc"})


def name_tokens(names: Sequence[str]) -> frozenset[str]:
    return frozenset(
        t for name in names for t in normalise(name).split() if t not in NAME_STOP_WORDS
    )


def redact_names(text: str, character: str, others: Sequence[str]) -> str:
    """This character's names become "a person", any other character's "another person"."""
    own = name_tokens([character])
    return _redact(
        text,
        own | name_tokens(others),
        lambda run: "a person" if set(run) <= own else "another person",
    )


def redact_all(text: str, characters: Sequence[str]) -> str:
    """Every character's names become "a person"."""
    return _redact(text, name_tokens(characters), lambda _: "a person")


def redact(text: str, labels: Mapping[str, str]) -> str:
    """`redact_all`'s matching with a label per name token (storyboard.md §3.1 Labels, T052).
    `labels` is in rank order, and a run takes the label of its token that comes first in it."""
    rank = {token: i for i, token in enumerate(labels)}
    return _redact(text, labels.keys(), lambda run: labels[min(run, key=rank.__getitem__)])


def _is_name(word: str, tokens: Collection[str]) -> bool:
    # UPPER or Title case: a capital first letter. "McDONALD" counts too; "will" never does.
    return word[0].isupper() and word.upper() in tokens


def _is_particle(word: str, tokens: Collection[str]) -> bool:
    return word in NAME_PARTICLES and word.upper() in tokens


def _joins(gap: str) -> bool:
    """Two name words of one run: whitespace, a hyphen or an apostrophe (O'BRIEN) between."""
    return gap == "-" or gap in _APOSTROPHES or (bool(gap) and gap.isspace())


def _after_particles(words: list[re.Match[str]], text: str, j: int, tokens: Collection[str]) -> int:
    """T092: the index of the name word after one or more lower-case particles that follow word
    `j`, every gap whitespace; or `j` when there is no such name word (a particle never ends or
    starts a run)."""
    k = j + 1
    while k < len(words) and _is_particle(words[k].group(), tokens):
        if not text[words[k - 1].end() : words[k].start()].isspace():
            return j
        k += 1
    if k == j + 1 or k >= len(words) or not _is_name(words[k].group(), tokens):
        return j
    return k if text[words[k - 1].end() : words[k].start()].isspace() else j


def _runs(words: list[re.Match[str]], text: str, tokens: Collection[str]) -> list[tuple[int, int]]:
    """`_name_runs` on words already found."""
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(words):
        if not _is_name(words[i].group(), tokens):
            i += 1
            continue
        j = i
        while True:
            if j + 1 < len(words) and _is_name(words[j + 1].group(), tokens):
                if not _joins(text[words[j].end() : words[j + 1].start()]):
                    break
                j += 1
            elif (k := _after_particles(words, text, j, tokens)) > j:
                j = k
            else:
                break
        runs.append((i, j))
        i = j + 1
    return runs


def _name_runs(text: str, tokens: Collection[str]) -> list[tuple[int, int]]:
    """Each maximal run of name tokens in `text`, as its first and last word's index among
    `_WORD`'s words: joined by whitespace, a hyphen or an apostrophe (O'BRIEN), and lower-case
    particles between two name words (T092). `_redact` and `named_as_figure` both read these."""
    if not tokens:
        return []
    return _runs(list(_WORD.finditer(text)), text, tokens)


def named_as_figure(text: str, tokens: Collection[str]) -> bool:
    """Some run of `tokens` names someone as a figure (T092, storyboard.md §3.1): not possessive
    (no apostrophe right after it), and Title case ("Lindi", "McDONALD") or an UPPER-case
    introduction followed by "(" ("AYANDA (17)"). A title before the run is no part of it."""
    if not tokens:
        return False
    words = list(_WORD.finditer(text))
    for i, j in _name_runs(text, tokens):
        after = text[words[j].end() :]
        if after[:1] in _APOSTROPHES:
            continue
        run = [w.group() for w in words[i : j + 1] if w.group() not in NAME_PARTICLES]
        if any(w != w.upper() for w in run) or re.match(r"[ \t]*\(", after):
            return True
    return False


def _redact(text: str, tokens: Collection[str], label: Callable[[list[str]], str]) -> str:
    """Each maximal run of name tokens (`_name_runs`, with an optional possessive 's on the last)
    becomes one label."""
    if not tokens:
        return text
    words = list(_WORD.finditer(text))
    out: list[str] = []
    pos = 0
    for i, j in _name_runs(text, tokens):
        if words[i].start() < pos:
            continue  # its first word went with the last run's possessive 's
        replacement = label([w.group().upper() for w in words[i : j + 1]])
        start = _title_start(text, words, i, pos)
        end = words[j].end()
        after = j + 1
        # "NANDI'S": the tokeniser sees NANDI, then S after an apostrophe.
        if (
            after < len(words)
            and words[after].group() in ("s", "S")
            and text[end : words[after].start()] in _APOSTROPHES
        ):
            # `it` has no apostrophe in its possessive: "Gerald's leg" -> "its leg".
            replacement += "s" if replacement == "it" else text[end] + "s"
            end = words[after].end()
        out += [text[pos:start], replacement]
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _title_start(text: str, words: list[re.Match[str]], i: int, floor: int) -> int:
    """Where the name run at word `i` starts once the titles directly before it join it: each a
    capitalised title word (an abbreviation optionally with a ".") separated by whitespace, and
    never reaching back before `floor`, the end of the last replacement. (Defensive: titles are
    stop words, never name tokens, so a walk back stops at the previous run anyway.)"""
    start = words[i].start()
    k = i - 1
    while k >= 0 and words[k].start() >= floor:
        word = words[k].group()
        gap = text[words[k].end() : start]
        if gap.startswith(".") and word.upper() in _ABBREVIATIONS:
            gap = gap[1:]
        if not (word[0].isupper() and word.upper() in TITLE_WORDS and gap and gap.isspace()):
            break
        start = words[k].start()
        k -= 1
    return start
