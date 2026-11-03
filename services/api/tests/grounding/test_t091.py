"""T091: with no claim, a character's sex from the script's own possessive, every piece of the
evidence agreeing and at least one sentence whose subject owns the pronoun (grounding.md §3, §6,
§9). A self-written script, one scene per case so no line is another's evidence; no model."""

import pytest

from app.characters.sex import Sex
from app.grounding import Entity, EntityKind, ProposedEntity, ground
from app.grounding.filter import (  # pyright: ignore[reportPrivateUsage]
    _pronoun_evidence,  # pyright: ignore[reportPrivateUsage]
    _pronoun_pieces,  # pyright: ignore[reportPrivateUsage]
    _script_names,  # pyright: ignore[reportPrivateUsage]
)
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
    (CUE - 4, "POSSESSIVE TESTS"),
    None,
    *_scene("1", (ACTION, "AYANDA (17), braids, chews her pencil.")),
    *_scene(
        "2", (ACTION, "PIETER (17) waits. Pieter pulls his hood down and stares at his candle.")
    ),
    *_scene("3", (ACTION, "The REFEREE (50s), striped shirt, blows his whistle.")),
    *_scene(
        "4",
        (ACTION, "NOSI (16), praying with her eyes closed. Nosi drags her desk to the window."),
    ),
    *_scene("5", (ACTION, "NALEDI (30s) sits down."), (ACTION, "She opens the letter.")),
    *_scene("6", (ACTION, "ZOLA (17) nods. She smiles. Zola takes his hand.")),
    *_scene("7", (ACTION, "MILO (40s) waits. Milo hands her coffee. Milo nods. He leaves.")),
    *_scene("8", (ACTION, "BEN (9) waits. Ben stumbles out with a bag held against his chest.")),
    *_scene("9", (ACTION, "A brown dog, REX, sleeps. Rex wags his tail.")),
    *_scene("10", (ACTION, "KOOS (70s) waits. Koos taps his broom. Koos sits. He smiles.")),
    *_scene("11", (ACTION, "Grace lifts her cup."), (CUE, "GRACE"), (DIALOGUE, "More tea?")),
    *_scene(
        "12",
        (ACTION, "DANIEL (40s), a tall driver, climbs out. He stretches until his back cracks."),
    ),
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
    ("name", "quote", "sex", "evidence"),
    [
        (
            "AYANDA",
            "AYANDA (17), braids, chews her pencil.",
            Sex.FEMALE,
            "AYANDA (17), braids, chews her pencil.",
        ),
        (
            "PIETER",
            "PIETER (17) waits.",
            Sex.MALE,
            "Pieter pulls his hood down and stares at his candle.",
        ),
        (
            "REFEREE",
            "The REFEREE (50s), striped shirt, blows his whistle.",
            Sex.MALE,
            "The REFEREE (50s), striped shirt, blows his whistle.",
        ),
        (
            "NOSI",
            "NOSI (16), praying with her eyes closed.",
            Sex.FEMALE,
            "NOSI (16), praying with her eyes closed.",
        ),  # two owning sentences: the first is the quote
        ("KOOS", "KOOS (70s) waits.", Sex.MALE, "Koos taps his broom."),  # an agreeing He too
    ],
)
def test_no_claim_and_an_owning_sentence_keeps_the_sex(
    name: str, quote: str, sex: Sex, evidence: str
) -> None:
    e = grounded(person(name, quote, None))[name]
    assert e.sex is sex
    assert e.sex_quote is not None and e.sex_quote.text == evidence


@pytest.mark.parametrize(
    ("name", "quote"),
    [
        ("NALEDI", "NALEDI (30s) sits down."),  # a next-sentence She alone keeps nothing
        ("ZOLA", "ZOLA (17) nods."),  # "Zola takes his hand." against "She smiles."
        ("MILO", "MILO (40s) waits."),  # a dative "her" against "He leaves."
        ("BEN", "BEN (9) waits."),  # a determiner between: no evidence
        ("DANIEL", "DANIEL (40s), a tall driver, climbs out."),  # only a next-sentence He
    ],
)
def test_no_claim_and_no_plain_owning_evidence_keeps_nothing(name: str, quote: str) -> None:
    assert grounded(person(name, quote, None))[name].sex is None


def test_an_animal_with_no_claim_gets_no_sex() -> None:
    dog = ProposedEntity.model_validate(
        {
            "kind": "character",
            "name": "REX",
            "quotes": ["A brown dog, REX, sleeps."],
            "species": "dog",
            "sex_word": None,
        }
    )
    assert grounded(dog)["REX"].sex is None


def test_a_cue_backfill_gets_no_sex_from_its_own_sentence() -> None:
    grace = grounded()["GRACE"]  # never proposed: a Source.CUE backfill
    assert grace.sex is None


def test_a_word_that_keys_to_no_sex_is_no_claim() -> None:
    e = grounded(person("KOOS", "KOOS (70s) waits.", "teen"))["KOOS"]
    assert e.sex is Sex.MALE


@pytest.mark.parametrize("word", ["her", "she"])
def test_a_claim_the_evidence_contradicts_still_keeps_nothing(word: str) -> None:
    assert grounded(person("KOOS", "KOOS (70s) waits.", word))["KOOS"].sex is None


def test_a_null_chunk_beside_a_contradicted_claim_keeps_nothing() -> None:
    quote = "KOOS (70s) waits."
    found = grounded(person("KOOS", quote, None), person("KOOS", quote, "she"))
    assert found["KOOS"].sex is None


def test_a_claim_still_works_as_t088() -> None:
    e = grounded(person("DANIEL", "DANIEL (40s), a tall driver, climbs out.", "he"))["DANIEL"]
    assert e.sex is Sex.MALE
    assert e.sex_quote is not None and e.sex_quote.text == "He stretches until his back cracks."


def _pieces(name: str, quote: str) -> list[tuple[Sex, str, bool]]:
    play = screenplay()
    cast = [
        e for e in ground([person(name, quote, None)], play)[0] if e.kind is EntityKind.CHARACTER
    ]
    entity = next(e for e in cast if e.name == name)
    names = _script_names(play)
    return [(s, q.text, owns) for s, q, owns in _pronoun_pieces(entity, cast, play, names)]


def test_pronoun_pieces_marks_which_sentences_own() -> None:
    assert _pieces("AYANDA", "AYANDA (17), braids, chews her pencil.") == [
        (Sex.FEMALE, "AYANDA (17), braids, chews her pencil.", True)
    ]
    assert _pieces("NALEDI", "NALEDI (30s) sits down.") == [
        (Sex.FEMALE, "She opens the letter.", False)
    ]
    assert _pieces("REFEREE", "The REFEREE (50s), striped shirt, blows his whistle.") == [
        (Sex.MALE, "The REFEREE (50s), striped shirt, blows his whistle.", True)
    ]
    assert _pieces("KOOS", "KOOS (70s) waits.") == [
        (Sex.MALE, "Koos taps his broom.", True),
        (Sex.MALE, "He smiles.", False),
    ]


QUOTES = {
    "AYANDA": "AYANDA (17), braids, chews her pencil.",
    "PIETER": "PIETER (17) waits.",
    "NALEDI": "NALEDI (30s) sits down.",
    "ZOLA": "ZOLA (17) nods.",
    "MILO": "MILO (40s) waits.",
    "KOOS": "KOOS (70s) waits.",
    "DANIEL": "DANIEL (40s), a tall driver, climbs out.",
}


@pytest.mark.parametrize("name", list(QUOTES))
def test_pronoun_evidence_is_the_pieces_without_the_flag(name: str) -> None:
    play = screenplay()
    cast = [
        e
        for e in ground([person(name, QUOTES[name], None)], play)[0]
        if e.kind is EntityKind.CHARACTER
    ]
    entity = next(e for e in cast if e.name == name)
    names = _script_names(play)
    pieces = _pronoun_pieces(entity, cast, play, names)
    assert _pronoun_evidence(entity, cast, play, names) == [(s, q) for s, q, _ in pieces]
