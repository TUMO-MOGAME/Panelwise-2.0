"""Redaction labels: animals, named props, `it` -- storyboard.md §3.1 Labels and §9 (T052).

The lines are modelled on samples/lost-property.fountain; self-written, like the rest."""

import pytest

from app.characters import NAME_STOP_WORDS, redact
from app.characters.labels import animals, redaction_labels
from app.grounding import (
    Entity,
    EntityKind,
    Extraction,
    GroundingReport,
    ProposedEntity,
    Source,
    ground,
)
from app.llm import Usage
from app.script import Screenplay
from app.storyboard import build_frame_prompt, visible_characters
from app.storyboard.prompt import FramePrompt, PartKind, PromptPart
from app.storyboard.prompts import cites_this_shot, names_in
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading
from tests.storyboard.conftest import STYLE, screenplay_of, shot_of

ROWS: list[Row] = [
    heading("1", "INT. LOST PROPERTY OFFICE - NIGHT"),
    None,
    (ACTION, "A ginger cat, MARMALADE, sleeps on a pile of scarves."),
    None,
    (ACTION, "AMAHLE holds a toy giraffe."),
    None,
    (CUE, "AMAHLE"),
    (DIALOGUE, "A toy one. His name is Gerald."),
    None,
    heading("2", "INT. PLATFORM - NIGHT"),
    None,
    (ACTION, "Amahle dances with Gerald. Even Marmalade comes back to the doorway."),
    None,
    (ACTION, "Marmalade's tail twitches. Gerald's leg sticks out. The VIOLIN case sits closed."),
    None,
    (ACTION, "Amahle shows the toy giraffe to the cat."),
    None,
    heading("3", "EXT. STREET - DAY"),
    None,
    (ACTION, "A man named Bob waves. Bob's hat flies off."),
]


def proposal(
    kind: str,
    name: str,
    quotes: list[str],
    species: str | None = None,
    other: list[str] | None = None,
) -> ProposedEntity:
    return ProposedEntity.model_validate(
        {
            "kind": kind,
            "name": name,
            "quotes": quotes,
            "species": species,
            "other_names": other or [],
        }
    )


@pytest.fixture
def office() -> Screenplay:
    return screenplay_of(ROWS)


@pytest.fixture
def extraction(office: Screenplay) -> Extraction:
    entities, report = ground(
        [
            proposal("character", "MARMALADE", ["A ginger cat, MARMALADE, sleeps"], "cat"),
            proposal("character", "AMAHLE", ["AMAHLE holds a toy giraffe."]),
            proposal("prop", "TOY GIRAFFE", ["holds a toy giraffe"], other=["Gerald", "Bob"]),
            proposal("prop", "VIOLIN", ["The VIOLIN case sits closed."]),
        ],
        office,
    )
    return Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


def scene_text(office: Screenplay, scene: int, element: int) -> str:
    return office.scenes[scene].elements[element].text


def test_an_animal_is_the_cat_and_a_paired_prop_name_is_the_prop(
    office: Screenplay, extraction: Extraction
) -> None:
    labels = redaction_labels(extraction, office)
    assert redact(scene_text(office, 1, 0), labels) == (
        "a person dances with the toy giraffe. Even the cat comes back to the doorway."
    )


def test_possessives_take_the_label_and_its_for_it(
    office: Screenplay, extraction: Extraction
) -> None:
    labels = redaction_labels(extraction, office)
    assert redact(scene_text(office, 1, 1), labels) == (
        "the cat's tail twitches. the toy giraffe's leg sticks out. The VIOLIN case sits closed."
    )
    # Bob shares no scene with the giraffe: unpaired, so `it`, and its possessive `its`.
    assert redact(scene_text(office, 2, 0), labels) == "A man named it waves. its hat flies off."


def test_a_prop_is_never_redacted_by_its_own_name(
    office: Screenplay, extraction: Extraction
) -> None:
    labels = redaction_labels(extraction, office)
    assert redact(scene_text(office, 1, 2), labels) == "a person shows the toy giraffe to the cat."
    assert "VIOLIN" not in labels


def test_labels_come_in_rank_order(office: Screenplay, extraction: Extraction) -> None:
    labels = list(redaction_labels(extraction, office).items())
    order = {"a person": 0, "the cat": 1, "the toy giraffe": 2, "it": 3}
    ranks = [order[label] for _, label in labels]
    assert ranks == sorted(ranks)
    assert dict(labels)["BOB"] == "it"


def test_only_limits_the_labels_to_one_character(
    office: Screenplay, extraction: Extraction
) -> None:
    assert redaction_labels(extraction, office, only="AMAHLE") == {"AMAHLE": "a person"}
    assert redaction_labels(extraction, office, only="MARMALADE") == {"MARMALADE": "the cat"}


def entity(
    kind: EntityKind, name: str, species: str | None = None, other: tuple[str, ...] = ()
) -> Entity:
    return Entity(kind, name, (), (0,), Source.MODEL, species=species, other_names=other)


def hand(*entities: Entity) -> Extraction:
    report = GroundingReport(0, 0, 1.0, 0, 0, (), 0, 0, 1.0)
    return Extraction(entities, report, ("m",), Usage(0, 0, 0))


def test_a_species_less_entry_bound_to_an_animal_is_that_animal() -> None:
    # A CUE backfill or a second entry of the same cat has no species of its own.
    extraction = hand(
        entity(EntityKind.CHARACTER, "MARMALADE THE CAT", species="cat"),
        entity(EntityKind.CHARACTER, "MARMALADE"),
        entity(EntityKind.CHARACTER, "NANDI"),
    )
    assert animals(extraction) == {"MARMALADE THE CAT": "cat", "MARMALADE": "cat"}


def test_a_token_shared_by_a_person_and_an_animal_is_a_person(office: Screenplay) -> None:
    # MAX POWER is not bound to MAX (his words are not a subset of the dog's), so both stand.
    extraction = hand(
        entity(EntityKind.CHARACTER, "MAX", species="dog"),
        entity(EntityKind.CHARACTER, "MAX POWER"),
    )
    labels = redaction_labels(extraction, office)
    assert labels["MAX"] == "a person" and labels["POWER"] == "a person"
    assert redact("Max barks.", labels) == "a person barks."


def test_two_animals_sharing_a_token_take_the_earlier_entity(office: Screenplay) -> None:
    extraction = hand(
        entity(EntityKind.CHARACTER, "REX", species="dog"),
        entity(EntityKind.CHARACTER, "REX JUNIOR", species="puppy"),
    )
    labels = redaction_labels(extraction, office)
    assert labels["REX"] == "the dog" and labels["JUNIOR"] == "the puppy"
    assert redact("Rex Junior naps.", labels) == "the dog naps."


def test_a_label_holding_a_name_token_is_it() -> None:
    rows: list[Row] = [
        heading("1", "INT. HALL - DAY"),
        None,
        (ACTION, "NANDI'S UMBRELLA, called Brolly, leans by the door. Nandi waits."),
    ]
    screenplay = screenplay_of(rows)
    extraction = hand(
        entity(EntityKind.CHARACTER, "NANDI"),
        entity(EntityKind.PROP, "NANDI'S UMBRELLA", other=("Brolly",)),
    )
    labels = redaction_labels(extraction, screenplay)
    assert labels["BROLLY"] == "it"
    assert "nandi" not in " ".join(labels.values()).lower()


def test_count_and_placement_count_people_not_animals(
    office: Screenplay, extraction: Extraction
) -> None:
    shot = shot_of(office, 1, [0], characters=("AMAHLE", "MARMALADE"), time_of_day="NIGHT")
    assert visible_characters(shot, office, extraction) == ("AMAHLE",)
    prompt = build_frame_prompt(shot, office, extraction, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is PartKind.COUNT] == ["one figure"]
    with pytest.raises(ValueError, match="exactly two figures"):
        build_frame_prompt(
            shot,
            office,
            extraction,
            STYLE,
            max_words=100,
            placement="one figure on the left, one on the right",
        )


@pytest.mark.parametrize(("scene", "elements"), [(0, [0, 1, 2]), (1, [0, 1, 2]), (2, [0])])
def test_the_invariant_and_names_hold_with_labels(
    office: Screenplay, extraction: Extraction, scene: int, elements: list[int]
) -> None:
    shot = shot_of(
        office,
        scene,
        elements,
        characters=("AMAHLE", "MARMALADE"),
        time_of_day="NIGHT" if scene < 2 else "DAY",
    )
    prompt = build_frame_prompt(shot, office, extraction, STYLE, max_words=100)
    assert cites_this_shot(prompt, shot, office, extraction)
    assert names_in(prompt, extraction) == []
    text = prompt.text()
    for name in ("Gerald", "Marmalade", "Amahle", "Bob", "GERALD", "MARMALADE"):
        assert name not in text


def test_names_in_finds_an_other_name_left_in_a_prompt(extraction: Extraction) -> None:
    leaked = FramePrompt((PromptPart(PartKind.ACTION, "Gerald waves.", None),), 0)
    assert names_in(leaked, extraction) == ["Gerald"]


def test_stop_words_never_become_labels(office: Screenplay, extraction: Extraction) -> None:
    assert not set(redaction_labels(extraction, office)) & NAME_STOP_WORDS


def test_a_speaking_animal_cued_cat_is_the_cat(office: Screenplay) -> None:
    labels = redaction_labels(hand(entity(EntityKind.CHARACTER, "CAT", species="cat")), office)
    assert labels == {"CAT": "the cat"}


def test_scene_words_are_computed_once_per_screenplay(
    office: Screenplay, extraction: Extraction
) -> None:
    from app.characters import labels as module

    first = redaction_labels(extraction, office)
    cached = module._cache[0][1]  # pyright: ignore[reportPrivateUsage]
    assert redaction_labels(extraction, office) == first
    assert module._cache[0][1] is cached  # pyright: ignore[reportPrivateUsage]
    other = screenplay_of(ROWS)  # equal text, a different object: recomputed, not reused
    redaction_labels(extraction, other)
    assert module._cache[0][0] is other  # pyright: ignore[reportPrivateUsage]
