"""T082: a person's sex from a word the extraction copies, grounded by code (grounding.md §3
sex_word, §9). A self-written script with one line per rule; no model."""

from typing import Any

from app.characters.sex import Sex
from app.grounding import Entity, EntityKind, Extraction, ProposedEntity, ground
from app.llm import Usage
from app.projects.codec import dump_extraction, load_extraction
from app.script import Screenplay, parse_text
from tests.script.conftest import ACTION, CUE, DIALOGUE, heading, layout

ROWS = [
    (CUE - 4, "SEX TESTS"),
    None,
    (ACTION, "FADE IN:"),
    None,
    heading("1", "INT. KITCHEN - DAY"),
    None,
    (ACTION, "THANDI (30s) dries a cup. She hums."),
    None,
    (ACTION, "She waves. JOHN (40s) sits."),
    None,
    (ACTION, "PETER hands her the box."),
    None,
    (ACTION, "ZOLA laughs. She hands him the cup."),
    None,
    (ACTION, "DUBE stands. She leaves."),
    None,
    (ACTION, "THABO DUBE and LERATO DUBE wait."),
    None,
    (ACTION, "THABO MOLEFE grins. He waves."),
    None,
    (ACTION, "A quiet fisherman mends a net. This is SIPHO (50s)."),
    None,
    (ACTION, "KAYA (20s) runs. She is late."),
    None,
    (ACTION, "KAYA, a man in a coat, waits."),
    None,
    (ACTION, "LINDA (40s) dresses herself."),
    None,
    (ACTION, "BEN (50s) shaves himself."),
    None,
    (ACTION, "PETER hugs his mother."),
    None,
    (ACTION, "MR. KHUMALO (60s) waits."),
    None,
    (ACTION, "Mr. hums. He sits."),
    None,
    (ACTION, "A ginger cat, TIGER, sleeps. She purrs."),
    None,
    (ACTION, "KOOS (70s), the night cleaner, pushes a broom. She waves."),
    None,
    (CUE, "ANNA"),
    (DIALOGUE, "I am a woman of my word."),
    None,
]


def screenplay() -> Screenplay:
    return parse_text(layout(ROWS), [])


def proposal(name: str, quotes: list[str], sex_word: str | None) -> ProposedEntity:
    return ProposedEntity.model_validate(
        {"kind": "character", "name": name, "quotes": quotes, "sex_word": sex_word}
    )


def grounded(*proposals: ProposedEntity) -> dict[str, Entity]:
    entities, _ = ground(list(proposals), screenplay())
    return {e.name: e for e in entities if e.kind is EntityKind.CHARACTER}


def test_a_pronoun_after_the_name_in_a_one_character_line() -> None:
    e = grounded(proposal("THANDI", ["THANDI (30s) dries a cup. She hums."], "She"))["THANDI"]
    assert e.sex is Sex.FEMALE
    assert e.sex_quote is not None and e.sex_quote.text == "THANDI (30s) dries a cup. She hums."


def test_a_noun_may_come_before_the_name() -> None:
    quote = "A quiet fisherman mends a net. This is SIPHO (50s)."
    assert grounded(proposal("SIPHO", [quote], "fisherman"))["SIPHO"].sex is Sex.MALE


def test_a_pronoun_before_the_name_is_someone_elses() -> None:
    assert grounded(proposal("JOHN", ["She waves. JOHN (40s) sits."], "She"))["JOHN"].sex is None


def test_object_and_possessive_pronouns_are_not_in_the_vocabulary() -> None:
    assert grounded(proposal("PETER", ["PETER hands her the box."], "her"))["PETER"].sex is None


def test_two_sexes_in_one_quote_give_none() -> None:
    quote = "ZOLA laughs. She hands him the cup."
    zola = grounded(proposal("ZOLA", [quote], "She"))["ZOLA"]
    # T082's rule (e) refuses this quote; T088 keeps the claim from the script's own pronoun: "She"
    # opens the sentence right after the one that opens with ZOLA.
    assert zola.sex_quote is not None and zola.sex_quote.text == "She hands him the cup."


def test_a_shared_token_names_the_other_character() -> None:
    found = grounded(
        proposal(
            "THABO DUBE", ["THABO DUBE and LERATO DUBE wait.", "DUBE stands. She leaves."], "She"
        ),
        proposal(
            "LERATO DUBE", ["THABO DUBE and LERATO DUBE wait.", "DUBE stands. She leaves."], "She"
        ),
    )
    assert found["THABO DUBE"].sex is None and found["LERATO DUBE"].sex is None


def test_aliases_do_not_reject_each_other() -> None:
    found = grounded(
        proposal("THABO", ["THABO MOLEFE grins. He waves."], "He"),
        proposal("THABO MOLEFE", ["THABO MOLEFE grins. He waves."], "He"),
    )
    assert found["THABO"].sex is Sex.MALE and found["THABO MOLEFE"].sex is Sex.MALE


def test_proposals_that_disagree_keep_none() -> None:
    found = grounded(
        proposal("KAYA", ["KAYA (20s) runs. She is late."], "She"),
        proposal("KAYA", ["KAYA, a man in a coat, waits."], "man"),
    )
    assert found["KAYA"].sex is None


def test_a_word_in_dialogue_is_not_a_description() -> None:
    found = grounded(proposal("ANNA", ["I am a woman of my word."], "woman"))
    assert found["ANNA"].sex is None


def test_a_word_outside_the_vocabulary_or_the_quote_gives_none() -> None:
    quote = "THANDI (30s) dries a cup. She hums."
    assert grounded(proposal("THANDI", [quote], "teacher"))["THANDI"].sex is None
    assert grounded(proposal("THANDI", [quote], "he"))["THANDI"].sex is None
    assert grounded(proposal("THANDI", [quote], None))["THANDI"].sex is None


def test_a_backfilled_speaker_gets_no_sex() -> None:
    # ANNA proposed by no one: the cue backfill, with only her speech.
    assert grounded()["ANNA"].sex is None


def test_reflexive_pronouns_give_a_sex() -> None:
    found = grounded(
        proposal("LINDA", ["LINDA (40s) dresses herself."], "herself"),
        proposal("BEN", ["BEN (50s) shaves himself."], "himself"),
    )
    assert found["LINDA"].sex is Sex.FEMALE and found["BEN"].sex is Sex.MALE


def test_relational_nouns_are_not_in_the_vocabulary() -> None:
    found = grounded(proposal("PETER", ["PETER hugs his mother."], "mother"))
    # "mother" is no word for PETER's sex (never female); since T091 his own "his" makes him male.
    assert found["PETER"].sex is Sex.MALE


def test_a_title_alone_names_no_one() -> None:
    quotes = ["MR. KHUMALO (60s) waits.", "Mr. hums. He sits."]
    assert grounded(proposal("MR. KHUMALO", quotes, "He"))["MR. KHUMALO"].sex is None


def test_an_animal_gets_no_sex() -> None:
    cat = ProposedEntity.model_validate(
        {
            "kind": "character",
            "name": "TIGER",
            "quotes": ["A ginger cat, TIGER, sleeps. She purrs."],
            "species": "cat",
            "sex_word": "She",
        }
    )
    tiger = grounded(cat)["TIGER"]
    assert tiger.species == "cat" and tiger.sex is None


def test_a_cue_backfill_gets_no_sex_whatever_it_is_given() -> None:
    from app.grounding.filter import _with_sex  # pyright: ignore[reportPrivateUsage]

    anna = grounded()["ANNA"]
    assert anna.source.value == "cue"
    actions = {q.span for q in anna.quotes}  # even were its quote an action line
    assert _with_sex(anna, ["woman"], [anna], actions).sex is None


def test_the_recorded_residual_risk_a_passer_by_pronoun() -> None:
    # grounding.md §3: "KOOS ... pushes a broom. She waves." passes if the model copies "She";
    # the model is asked for the word about Koos, and storyboard's character_sex drops a sex
    # another source contradicts. Pinned so a change to this rule is a deliberate one.
    quote = "KOOS (70s), the night cleaner, pushes a broom. She waves."
    assert grounded(proposal("KOOS", [quote], "She"))["KOOS"].sex is Sex.FEMALE


def _extraction(*proposals: ProposedEntity) -> Extraction:
    entities, report = ground(list(proposals), screenplay())
    return Extraction(entities, report, ("m",), Usage(0, 0, 0))


def test_an_extraction_stored_before_t082_still_loads() -> None:
    stored: dict[str, Any] = dump_extraction(
        _extraction(proposal("THANDI", ["THANDI (30s) dries a cup. She hums."], "She"))
    )
    for entity in stored["entities"]:
        for key in ("sex", "sex_quote", "species", "other_names"):
            entity.pop(key, None)
    loaded = load_extraction(stored)
    assert all(e.sex is None and e.sex_quote is None for e in loaded.entities)


def test_a_female_entity_round_trips() -> None:
    extraction = _extraction(proposal("THANDI", ["THANDI (30s) dries a cup. She hums."], "She"))
    again = load_extraction(dump_extraction(extraction))
    thandi = next(e for e in again.entities if e.name == "THANDI")
    assert thandi.sex is Sex.FEMALE and thandi.sex_quote is not None
