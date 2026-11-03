"""T100: a possessive Her or His opening the sentence after an introduction gives the introduced
character's sex (storyboard.md §3.1, §9; learning-log L023). Self-written lines; no model."""

import pytest

from app.grounding import NOT_POSSESSED
from app.storyboard.prompt import introduced_age, introduced_sex
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading
from tests.storyboard.conftest import screenplay_of

NALEDI = (
    "NALEDI (12), dungarees, scraped knees, stares at it. Her little brother TSHEPO (8), shorts "
    "down past his knees, stands beside her."
)


def sex_of(name: str, *rows: Row) -> str | None:
    return introduced_sex(name, screenplay_of([heading("1", "EXT. YARD - DAY"), *rows]))


def one(line: str, name: str = "SAM") -> str | None:
    return sex_of(name, (ACTION, line))


@pytest.mark.parametrize(
    ("line", "want"),
    [
        ("SAM (40) sits down. His hands shake.", "male"),
        ("SAM (40) sits down! His hands shake.", "male"),
        ("SAM (40) sits down? His hands shake.", "male"),
        ("SAM (40) sits down… His hands shake.", "male"),
        ("SAM (40) sits down. Her hands shake.", "female"),
        # the one-sex rule: the appositive's girl (T096) against the next sentence's His
        ("A girl, SAM (12), sits down. His hands shake.", None),
        # a pronoun in the introducing sentence is a possible owner: the next sentence isn't read
        ("SAM (40) waits as he sits down. Her hands shake.", "male"),
    ],
)
def test_the_next_sentence_gives_a_sex(line: str, want: str | None) -> None:
    assert one(line) == want


def test_naledi_is_a_girl_and_tshepo_keeps_his_own() -> None:
    assert one(NALEDI, "NALEDI") == "female"
    assert one(NALEDI, "TSHEPO") == "male"  # his own look, "shorts down past his knees"


def test_tshepo_is_not_read_from_the_her_before_his_name() -> None:
    line = "NALEDI (12) stares at it. Her little brother TSHEPO (8) waits."
    assert one(line, "TSHEPO") is None


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("MAMA (60s) hugs SIPHO. His shirt is wet.", "MAMA"),  # another name
        ("NANDI (60s) waves to THABO (9). His cap falls.", "NANDI"),  # a next introduction
        ("SAM (40) kisses the woman. Her eyes close.", "SAM"),  # a sex noun
        ("NALEDI (12) hands the man a coin. His hand shakes.", "NALEDI"),  # a sex noun
        ("SAM (40) holds the baby. His face softens.", "SAM"),  # a person noun
        ("SAM (40) watches them go. His face falls.", "SAM"),  # them
        ("SAM (40) watches her go. His face falls.", "SAM"),  # him/her/his
        ("SAM (40) greets Dr. Dube. His hand is cold.", "SAM"),  # Dr. ends no sentence
        ("SAM (40) sits. Rain falls. His hands shake.", "SAM"),  # not the next sentence
        ("SAM (40) sits. Her to the left, a door.", "SAM"),  # not a possessive
        ("SAM (40) sits. Her.", "SAM"),  # nothing owned
        ("SAM (40) sits. HER HANDS SHAKE.", "SAM"),  # not capitalised as a sentence opens
        ("SAM (40) sits. his hands shake.", "SAM"),
        ("SAM (40) sits.", "SAM"),  # the element's last sentence
        ("SAM (40) sits. Her, then silence.", "SAM"),  # punctuation: nothing owned
        ("SAM (40) greets \u00c9milie. His hand shakes.", "SAM"),  # an accented name
        ("NALEDI (12) hands the clerk a coin. His hand shakes.", "NALEDI"),  # an article
        ("SAM (40) pats a dog. Her tail wags.", "SAM"),  # an article
    ],
)
def test_nothing_from_the_next_sentence(line: str, name: str) -> None:
    assert one(line, name) is None


def test_another_element_is_never_read() -> None:
    rows: list[Row] = [
        (ACTION, "SAM (40) sits."),
        None,
        (CUE, "SAM"),
        (DIALOGUE, "Well."),
        None,
        (ACTION, "His hands shake."),
    ]
    assert sex_of("SAM", *rows) is None


def test_naledis_age_phrase_says_girl() -> None:
    sp = screenplay_of([heading("1", "EXT. YARD - DAY"), (ACTION, NALEDI)])
    found = introduced_age("NALEDI", sp)
    assert found is not None and found[0] == "a 12-year-old girl"


def test_not_possessed_is_public() -> None:
    assert {"to", "a", "the"} <= NOT_POSSESSED


def test_the_girl_in_the_prompt_cites_the_introduction() -> None:
    from app.grounding import Extraction, ProposedEntity, ground
    from app.llm import Usage
    from app.storyboard import build_frame_prompt
    from app.storyboard.prompts import cites_this_shot
    from tests.storyboard.conftest import STYLE, shot_of

    sp = screenplay_of([heading("1", "EXT. YARD - DAY"), (ACTION, NALEDI)])
    proposals = [
        ProposedEntity.model_validate({"kind": "character", "name": "NALEDI", "quotes": [NALEDI]})
    ]
    entities, report = ground(proposals, sp)
    ex = Extraction(entities, report, ("m",), Usage(0, 0, 0))
    shot = shot_of(sp, 0, [0], characters=["NALEDI"])
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    assert "a 12-year-old girl" in [p.text for p in prompt.parts]
    assert cites_this_shot(prompt, shot, sp, ex)
