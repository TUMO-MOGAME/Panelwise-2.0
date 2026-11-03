"""Which extracted character a dialogue cue belongs to.

Ported from FrameFlow's dialogue_linker.py (the matching; the DB linking waits for models).
Screenplays cue speakers by short name ("THABO") while extraction names them in full
("THABO MOLEFE"), so an exact match alone drops half the cast -- but a substring test binds
SIPHO to SIPHOKAZI. A cue matches when its words are a subset of exactly one name's words, and an
ambiguous cue matches nobody: an unattributed line is recoverable, a speech bubble on the wrong
character is not.
"""

import re
from collections.abc import Sequence

_PUNCT = re.compile(r"[^\w\s]+")


def normalise(name: str) -> str:
    """Upper-case, punctuation-free, single-spaced: the form both sides are compared in."""
    return " ".join(_PUNCT.sub(" ", (name or "").upper()).split())


def match_speaker(cue: str, names: Sequence[str]) -> str | None:
    cue_n = normalise(cue)
    if not cue_n:
        return None

    exact = [n for n in names if normalise(n) == cue_n]
    if exact:
        return exact[0] if len(exact) == 1 else None

    cue_words = set(cue_n.split())
    partial = [n for n in names if cue_words <= set(normalise(n).split())]
    return partial[0] if len(partial) == 1 else None
