"""T096: a sex noun in the introduction's appositive, "A boy in a too-big school blazer, THABO (9)"
(storyboard.md §3.1, §9). Self-written lines, one scene each; no model."""

import pytest

from app.storyboard.prompt import introduced_age, introduced_sex
from tests.script.conftest import ACTION, heading
from tests.storyboard.conftest import screenplay_of


def sex_of(line: str, name: str) -> str | None:
    return introduced_sex(name, screenplay_of([heading("1", "EXT. RANK - NIGHT"), (ACTION, line)]))


@pytest.mark.parametrize(
    ("line", "name", "want"),
    [
        ("A boy in a too-big school blazer, THABO (9), stands alone.", "THABO", "male"),
        ("A small boy, KAMO (7), tugs at her skirt.", "KAMO", "male"),
        ("A small girl, AMA (7), waits.", "AMA", "female"),
        ("An old woman, NANDI (60s), sits.", "NANDI", "female"),
        ("Six learners wait. A tall girl, ZOLA (17), yawns.", "ZOLA", "female"),
        # no appositive, or not this one's
        ("The boy, THABO (9), waits.", "THABO", None),
        ("A very small young shy girl, AMA (7), waits.", "AMA", None),  # four words before
        ("A woman hands the boy a letter, THABO (9), reads.", "THABO", None),  # a second noun
        ("A man who has walked for a very long time, SAM (40s), sits.", "SAM", None),
        ("THABO (9) waits beside a boy.", "THABO", None),  # the noun after the name
        # a noun and a pronoun that disagree give nothing, as two pronouns do
        ("A boy, SAM (9), waits, and she smiles at him.", "SAM", None),
        # two people in one sentence: the second appositive is no one's
        ("A boy, THABO (9), and a girl, AMA (7), play.", "AMA", None),
        ("A man helps a girl, AMA (7), up.", "AMA", None),
        # the noun's own describing phrase only: never a clause, a possessive or another person
        ("A woman and her child, ZANELE (6), waits.", "ZANELE", None),
        ("A man holding a baby, NOMSA (1), sleeps.", "NOMSA", None),
        ("A man hands the driver a note, SIPHO (30s), reads.", "SIPHO", None),
        ("A boy's teacher, SAM (40), waits.", "SAM", None),
        ("A boy\u2019s teacher, SAM (40), waits.", "SAM", None),
        ("A woman with a baby, LUMKA (1), cries.", "LUMKA", None),
        ("A man wearing a cap, SIPHO (30s), waits.", "SIPHO", "male"),
        ("A girl with braids, AMA (7), waits.", "AMA", "female"),
    ],
)
def test_the_appositive_noun(line: str, name: str, want: str | None) -> None:
    assert sex_of(line, name) == want


def test_the_age_phrase_says_boy() -> None:
    sp = screenplay_of(
        [heading("1", "EXT. RANK - NIGHT"), (ACTION, "A small boy, KAMO (7), waits.")]
    )
    found = introduced_age("KAMO", sp)
    assert found is not None and found[0] == "a 7-year-old boy"


def test_the_boy_in_the_prompt_cites_the_introduction() -> None:
    from app.grounding import Extraction, ProposedEntity, ground
    from app.llm import Usage
    from app.storyboard import build_frame_prompt
    from app.storyboard.prompts import cites_this_shot
    from tests.storyboard.conftest import STYLE, shot_of

    line = "A boy in a too-big school blazer, THABO (9), stands alone."
    sp = screenplay_of([heading("1", "EXT. RANK - NIGHT"), (ACTION, line)])
    proposals = [
        ProposedEntity.model_validate({"kind": "character", "name": "THABO", "quotes": [line]})
    ]
    entities, report = ground(proposals, sp)
    ex = Extraction(entities, report, ("m",), Usage(0, 0, 0))
    shot = shot_of(sp, 0, [0], characters=["THABO"])
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    assert "a 9-year-old boy" in [p.text for p in prompt.parts]
    assert cites_this_shot(prompt, shot, sp, ex)
