"""T088: a sex the extraction claims with its sex_word, kept only when the script's own subject
pronouns support it and none contradicts it (grounding.md §3, §9). A self-written script, one
scene per case so no line is another's evidence; no model."""

import pytest

from app.characters.sex import Sex
from app.grounding import Entity, EntityKind, ProposedEntity, ground
from app.script import Screenplay, parse_text
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading, layout


def _scene(number: str, *rows: Row) -> list[Row]:
    """A scene: its heading, then each row with a blank line after it, except a cue, which its
    speech follows directly."""
    out: list[Row] = [heading(number, f"INT. ROOM {number} - DAY"), None]
    for row in rows:
        out += [row] if row is not None and row[0] == CUE else [row, None]
    return out


ROWS: list[Row] = [
    (CUE - 4, "PRONOUN TESTS"),
    None,
    *_scene(
        "1",
        (ACTION, "DANIEL (40s), a tall driver, climbs out. He stretches until his back cracks."),
    ),
    *_scene("2", (ACTION, "SIPHO (50s) waits. Sipho does not take his eyes off the water.")),
    *_scene("3", (ACTION, "KAZI (17) nods. She cannot stop the smile.")),
    *_scene("4", (ACTION, "AMAHLE (8) waits. Amahle tugs at her mother's scrubs.")),
    *_scene("5", (ACTION, "ZOLA (17) nods. She smiles. Zola takes his hand.")),
    *_scene(
        "6", (CUE, "PRIYA"), (DIALOGUE, "No. No, no, no."), (ACTION, "She spots the sign and runs.")
    ),
    *_scene("7", (ACTION, "NOMSA (30s) and THEO (9) wait. Nomsa pulls Theo onto her lap.")),
    *_scene("8", (ACTION, "LINDA (20s) waits. Linda scrambles in behind him.")),
    *_scene("9", (ACTION, "PETER (30s) waits. Peter hands her the box.")),
    *_scene("10", (ACTION, "BEN (9) waits. Ben stumbles out with a bag held against his chest.")),
    *_scene("11", (ACTION, "OMAR (40s) pays the cashier. She smiles.")),
    *_scene("12", (ACTION, "THABO (30s) hugs LERATO (10). She smiles.")),
    *_scene("13", (ACTION, "MR. DUBE (60s) waits. Mr. Dube takes off his cap.")),
    *_scene(
        "14", (ACTION, "A quiet fisherman mends a net. This is JOHN (50s). John rubs his eyes.")
    ),
    *_scene("15", (ACTION, "A brown dog, REX, sleeps. Rex licks his paws.")),
    *_scene("16", (ACTION, "ZARA (8) waits. ZARA (8) tugs at her sleeve.")),
    *_scene("17", (ACTION, "MIKE (40s) waits. Mike hands her coffee.")),
    *_scene("18", (ACTION, "NALEDI (30s) sits down."), (ACTION, "She opens the letter.")),
]


def screenplay() -> Screenplay:
    return parse_text(layout(ROWS), [])


def person(name: str, quote: str, word: str | None) -> ProposedEntity:
    return ProposedEntity.model_validate(
        {"kind": "character", "name": name, "quotes": [quote], "sex_word": word}
    )


def grounded(*proposals: ProposedEntity) -> dict[str, Entity]:
    entities, _ = ground(list(proposals), screenplay())
    return {e.name: e for e in entities if e.kind is EntityKind.CHARACTER}


@pytest.mark.parametrize(
    ("name", "quote", "word", "sex", "evidence"),
    [
        # The claim's quote doesn't hold the word (T082 can't keep it); the script's pronoun does.
        (
            "DANIEL",
            "DANIEL (40s), a tall driver, climbs out.",
            "he",
            Sex.MALE,
            "He stretches until his back cracks.",
        ),
        (
            "SIPHO",
            "SIPHO (50s) waits.",
            "he",
            Sex.MALE,
            "Sipho does not take his eyes off the water.",
        ),
        ("KAZI", "KAZI (17) nods.", "she", Sex.FEMALE, "She cannot stop the smile."),
        ("AMAHLE", "AMAHLE (8) waits.", "she", Sex.FEMALE, "Amahle tugs at her mother's scrubs."),
        (
            "MR. DUBE",
            "MR. DUBE (60s) waits.",
            "he",
            Sex.MALE,
            "Mr. Dube takes off his cap.",
        ),  # one sentence
        (
            "JOHN",
            "This is JOHN (50s).",
            "fisherman",
            Sex.MALE,
            "John rubs his eyes.",
        ),  # a noun claim
    ],
)
def test_a_claim_the_scripts_pronouns_support_is_kept(
    name: str, quote: str, word: str, sex: Sex, evidence: str
) -> None:
    e = grounded(person(name, quote, word))[name]
    assert e.sex is sex
    assert e.sex_quote is not None and e.sex_quote.text == evidence


@pytest.mark.parametrize(
    ("name", "quote", "word"),
    [
        ("ZOLA", "ZOLA (17) nods.", "she"),  # "Zola takes his hand." contradicts her "She smiles."
        ("PRIYA", "No. No, no, no.", "she"),  # a speech between: the "She" may be the listener's
        ("THEO", "NOMSA (30s) and THEO (9) wait.", "he"),  # "Nomsa pulls Theo onto her lap."
        (
            "NOMSA",
            "NOMSA (30s) and THEO (9) wait.",
            "she",
        ),  # ... Theo stands between Nomsa and "her"
        ("LINDA", "LINDA (20s) waits.", "she"),  # "behind him": an object pronoun is someone else
        ("PETER", "PETER (30s) waits.", "he"),  # "hands her the box": an object her
        ("BEN", "BEN (9) waits.", "he"),  # "with a bag … his chest": a determiner between
        ("OMAR", "OMAR (40s) pays the cashier.", "she"),  # "the cashier" may own "She"
        (
            "THABO",
            "THABO (30s) hugs LERATO (10).",
            "she",
        ),  # a name the script writes, not extracted
    ],
)
def test_no_sex_without_plain_support(name: str, quote: str, word: str) -> None:
    assert grounded(person(name, quote, word))[name].sex is None


def test_no_claim_no_sex() -> None:
    daniel = person("DANIEL", "DANIEL (40s), a tall driver, climbs out.", None)
    assert grounded(daniel)["DANIEL"].sex is None


def test_claims_that_disagree_across_chunks_give_nothing() -> None:
    quote = "DANIEL (40s), a tall driver, climbs out."
    found = grounded(person("DANIEL", quote, "he"), person("DANIEL", quote, "she"))
    assert found["DANIEL"].sex is None


def test_a_claim_against_the_evidence_gives_nothing() -> None:
    daniel = person("DANIEL", "DANIEL (40s), a tall driver, climbs out.", "she")
    assert grounded(daniel)["DANIEL"].sex is None


def test_an_animal_claimant_gets_no_sex() -> None:
    dog = ProposedEntity.model_validate(
        {
            "kind": "character",
            "name": "REX",
            "quotes": ["A brown dog, REX, sleeps."],
            "species": "dog",
            "sex_word": "he",
        }
    )
    rex = grounded(dog)["REX"]
    assert rex.species == "dog"
    assert rex.sex is None


def test_the_evidence_is_the_scripts_own_sentence_verbatim() -> None:
    # The sentence holds an introduction: its words are read without "(8)", but the quote kept
    # is the script's text as written, located at its element.
    e = grounded(person("ZARA", "ZARA (8) waits.", "she"))["ZARA"]
    assert e.sex is Sex.FEMALE
    assert e.sex_quote is not None and e.sex_quote.text == "ZARA (8) tugs at her sleeve."


def test_a_dative_her_is_read_as_a_possessive_and_only_a_matching_claim_survives() -> None:
    # Known gap (grounding.md §3): "hands her coffee" reads as Mike's own "her". A true claim
    # ("he") is contradicted by it, so Mike gets no sex rather than a wrong one.
    assert grounded(person("MIKE", "MIKE (40s) waits.", "he"))["MIKE"].sex is None


def test_the_chain_reaches_the_last_sentence_of_the_action_before() -> None:
    e = grounded(person("NALEDI", "NALEDI (30s) sits down.", "she"))["NALEDI"]
    assert e.sex is Sex.FEMALE
    assert e.sex_quote is not None and e.sex_quote.text == "She opens the letter."
