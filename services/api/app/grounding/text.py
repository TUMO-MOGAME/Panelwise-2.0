"""Comparing a model's quote with the screenplay, and finding where it sits.

`normalize_for_grounding` is ported from FrameFlow's grounding.py. Screenplays are hard-wrapped,
so an accurate quote comes back with the wrap collapsed to a space, and a compound split across a
line break ("broad-" / "shouldered") comes back joined. Ignoring whitespace amount, case, and a
line-break hyphen does not weaken grounding: the complete word sequence must still appear, in
order. Invented or re-ordered content still fails. FrameFlow's lead character was dropped from
two runs in three by a line-break hyphen before this was fixed. Panelwise also folds curly
quotes, dashes and the ellipsis to ASCII, on both sides (PR #10 review: a prettified apostrophe
would otherwise drop an accurate quote).
"""

import re

from app.script import Dialogue, Screenplay, Span

_WHITESPACE = re.compile(r"\s+")
# Only a dash run touching the word before it: "sea-" / "green" is one word, but a spaced dash at
# the end of a line ("LOST PROPERTY -" / "PLATFORM 9", "WAIT --" / "NO") is punctuation and keeps
# its space (T039, T048). The parser joins element text by the same rule (script.md §3).
_LINEBREAK_HYPHEN = re.compile(r"(?<=[^\s-])(-+)[ \t]*\r?\n[ \t]*")
_DASH_RUN = re.compile(r"-{2,}")
# Typographic punctuation a model "prettifies" into: the same quote, so fold it to plain ASCII.
# Applied to both the quote and the script, so it can only ever match what the script says.
_TYPOGRAPHIC = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u2212": "-",
        "\u2026": "...",
    }
)


def normalize_for_grounding(text: str) -> str:
    folded = (text or "").translate(_TYPOGRAPHIC)
    joined = _LINEBREAK_HYPHEN.sub(r"\1", folded)
    # "--" and an em dash are the same dash in a screenplay.
    return _WHITESPACE.sub(" ", _DASH_RUN.sub("-", joined)).strip().upper()


type Index = list[tuple[int, Span, str]]
# (scene_index, speech span, the speech's normalised headers, its normalised source lines)
type CueIndex = list[tuple[int, Span, frozenset[str], str]]


def _source(lines: list[str], span: Span) -> str:
    # The raw lines a span names (not the joined element text), so a line-break hyphen is still
    # a line break here and gets joined.
    return normalize_for_grounding("\n".join(lines[span.line_start - 1 : span.line_end]))


def build_index(screenplay: Screenplay) -> Index:
    """Every heading and element in script order, with its normalised source text."""
    lines = screenplay.text.split("\n")
    index: Index = []
    for scene in screenplay.scenes:
        heading = Span(scene.span.page, scene.span.line_start, scene.span.line_start)
        for span in (heading, *(e.span for e in scene.elements)):
            index.append((scene.index, span, _source(lines, span)))
    return index


def headers(speech: Dialogue) -> frozenset[str]:
    """The lines `render_chunk` writes above a speech's text, normalised, in every form a model
    copies them: the cue with or without its extension, then optionally the speech's own
    parenthetical -- or that parenthetical alone. Normalised, so `CUE` / `(paren)` on two lines
    equals `CUE (paren)` on one."""
    cues = {speech.cue}
    if speech.extension:
        cues.add(f"{speech.cue} ({speech.extension})")
    forms = set(cues)
    if speech.parenthetical:
        paren = f"({speech.parenthetical})"
        forms |= {f"{cue} {paren}" for cue in cues} | {paren}
    return frozenset(normalize_for_grounding(f) for f in forms)


def build_cue_index(screenplay: Screenplay) -> CueIndex:
    """Every speech in script order, with its headers and normalised source text."""
    lines = screenplay.text.split("\n")
    return [
        (scene.index, e.span, headers(e), _source(lines, e.span))
        for scene in screenplay.scenes
        for e in scene.elements
        if isinstance(e, Dialogue)
    ]


def locate_in(index: Index, quote: str) -> tuple[int, Span] | None:
    needle = normalize_for_grounding(quote)
    if not needle:
        return None
    for scene_index, span, text in index:
        if needle in text:
            return scene_index, span
    return None


def locate_after_cue(cues: CueIndex, quote: str) -> tuple[str, int, Span] | None:
    """A dialogue quote the model began with its speech's header (`"LERATO\\nI promise."`).

    Kept only when the quote's leading line(s) -- one line, or two for cue then parenthetical --
    are exactly one speech's own header, and the rest is non-empty and inside *that same
    speech*. Returns the rest as the text to keep: the header is dropped, so what is kept is
    still verbatim script text located to one span. No other prefix is ever stripped.
    """
    lines = quote.strip().splitlines()
    for k in (1, 2):
        if len(lines) <= k:
            break
        header = normalize_for_grounding(" ".join(lines[:k]))
        rest = "\n".join(lines[k:]).strip()
        needle = normalize_for_grounding(rest)
        if not needle:
            continue
        for scene_index, span, own, text in cues:
            if header in own and needle in text:
                return rest, scene_index, span
    return None


def locate_quote(index: Index, cues: CueIndex, quote: str) -> tuple[str, int, Span] | None:
    """The text to keep for a quote, and where it sits: the quote as given if it is inside one
    element or heading, else the quote without its speech's header (`locate_after_cue`)."""
    if (found := locate_in(index, quote)) is not None:
        return quote, *found
    return locate_after_cue(cues, quote)


def locate(quote: str, screenplay: Screenplay) -> tuple[int, Span] | None:
    """The first scene heading or element, in script order, whose text contains the quote.

    Only a match inside one element counts: a quote stitched across two speeches is not
    something the script says, and "somewhere in the script" is not a span a panel can cite.
    """
    return locate_in(build_index(screenplay), quote)
