"""A character's sex, as words of the script (T082; docs/design/grounding.md §3, storyboard.md §6).

Pure, and importing nothing from app.grounding or app.storyboard: both use it. The words are a
fixed, general vocabulary; a word outside it gives no sex (fails closed), never a guess. One
place to add a language or a word.
"""

from enum import StrEnum


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"


# Words that, in one character's own description, are about that character: subject and
# reflexive pronouns, and nouns for the person. Left out on purpose (the T082 review): her, him,
# his ("SIPHO hands her the box"), relational nouns ("hugs his mother"), plurals, and titles,
# which SEX_TITLES reads from the name instead ("miss" is also a verb).
SEX_WORDS: dict[str, Sex] = {
    **dict.fromkeys(
        (
            "she", "herself", "woman", "girl", "lady", "fisherwoman", "policewoman",
            "businesswoman", "waitress", "actress",
        ),
        Sex.FEMALE,
    ),
    **dict.fromkeys(
        (
            "he", "himself", "man", "boy", "gentleman", "fisherman", "policeman", "businessman",
            "waiter", "actor",
        ),
        Sex.MALE,
    ),
}  # fmt: skip

PRONOUNS = frozenset({"she", "herself", "he", "himself"})

# Rule (e) of grounding.md §3: words that never give a sex but still contradict one ("She hands
# him the cup" names no sex at all, a safe miss rather than a guess).
CONFLICT_WORDS: dict[str, Sex] = {
    **SEX_WORDS,
    "her": Sex.FEMALE,
    "hers": Sex.FEMALE,
    "him": Sex.MALE,
    "his": Sex.MALE,
}

# A name's first word that gives a sex (storyboard.md §6, title_sex), upper case.
SEX_TITLES: dict[str, Sex] = {
    **dict.fromkeys(
        (
            "MRS", "MS", "MISS", "MADAM", "MADAME", "LADY", "MAMA", "GOGO", "OUMA", "AUNTIE",
            "AUNT", "TANNIE", "SISTER", "QUEEN", "PRINCESS",
        ),
        Sex.FEMALE,
    ),
    **dict.fromkeys(
        (
            "MR", "SIR", "LORD", "BABA", "OUPA", "UNCLE", "OOM", "BROTHER", "KING", "PRINCE",
        ),
        Sex.MALE,
    ),
}  # fmt: skip
