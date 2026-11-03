"""T092: a name's lower-case particle joins its run, and `named_as_figure` (storyboard.md §3.1,
§6, §9). Pure; no model."""

import pytest

from app.characters.redact import (
    _WORD,  # pyright: ignore[reportPrivateUsage]
    _name_runs,  # pyright: ignore[reportPrivateUsage]
    name_tokens,
    named_as_figure,
    redact,
    redact_all,
    redact_names,
)

CAST = ["MR. VAN DER MERWE", "LE ROUX", "THABO", "WET"]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Mr. Van der Merwe climbs down", "a person climbs down"),
        ("MR. VAN DER MERWE (50s), orange overalls", "a person (50s), orange overalls"),
        # two particles, both tokens of one name
        ("Jan van der Merwe waves.", "a person waves."),
        # no name word before the particle: it stays
        ("the house of le Roux", "the house of le a person"),
        # a full stop or a comma breaks the run; so does the end of the text
        ("Thabo. de Wet nods.", "a person. de a person nods."),
        ("Thabo, van Wet", "a person, van a person"),
        ("he met Thabo van", "he met a person van"),
    ],
)
def test_particles_join_a_run_only_between_two_name_words(text: str, want: str) -> None:
    assert redact_all(text, [*CAST, "JAN VAN DER MERWE"]) == want


def test_a_particle_that_is_no_token_of_the_names_stays() -> None:
    # "de" is no token of KLERK or THABO, so it never joins.
    assert redact_all("Thabo de Klerk", ["THABO", "KLERK"]) == "a person de a person"


def test_redact_names_labels_a_run_with_a_particle_as_the_characters_own() -> None:
    text = "Mr. Van der Merwe nods to Thabo."
    assert redact_names(text, "MR. VAN DER MERWE", ["THABO"]) == "a person nods to another person."


def test_labels_redact_takes_the_particle_with_the_run() -> None:
    labels = {t: "a person" for t in sorted(name_tokens(["MR. VAN DER MERWE"]))}
    assert redact("Mr. Van der Merwe levers up the cover.", labels) == (
        "a person levers up the cover."
    )


def figure(text: str, *names: str) -> bool:
    return named_as_figure(text, name_tokens(list(names)))


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("Lindi rolls the ball out to Palesa.", ["PALESA"]),
        ("Officer Van Wyk takes notes.", ["OFFICER VAN WYK"]),
        ("McDONALD waves.", ["MCDONALD"]),
        ("AYANDA (17), braids, chews her pencil.", ["AYANDA"]),
        ("AYANDA(17) waits.", ["AYANDA"]),
        ("Mr. Dube winds his watch.", ["MR. DUBE"]),
        ("Mr. Van der Merwe climbs down", ["MR. VAN DER MERWE"]),
        ("He looks at Jabu's paper. Jabu covers it with his arm.", ["JABU"]),
        ("O'BRIEN (40s) sits.", ["O'BRIEN"]),
    ],
)
def test_a_figure_run(text: str, names: list[str]) -> None:
    assert figure(text, *names)


@pytest.mark.parametrize(
    ("text", "names"),
    [
        # a title before the run is no part of it
        ("Mr. DUBE winds his watch.", ["MR. DUBE"]),
        # possessives, straight, curly and plural
        ("He looks across at Jabu's paper.", ["JABU"]),
        ("NANDI'S KITCHEN is warm.", ["NANDI"]),
        ("He takes Jabu" + chr(0x2019) + "s pen.", ["JABU"]),  # a curly apostrophe
        ("The Lionesses' goalkeeper, small, dives.", ["LIONESSES"]),
        # capitals with no introduction: a sign or a board
        ("The scoreboard is a blackboard: LIONESSES 1 - EAGLES 1.", ["LIONESSES", "EAGLES"]),
        # a newline before the parenthesis is no introduction
        ("AYANDA\n(17) waits.", ["AYANDA"]),
        ("Nobody comes.", ["THABO"]),
    ],
)
def test_no_figure_run(text: str, names: list[str]) -> None:
    assert not figure(text, *names)


def test_name_runs_are_the_runs_redact_replaces() -> None:
    word = _WORD
    fixtures = [
        ("NANDI MOLEFE pours tea for THABO.", ["NANDI MOLEFE", "THABO"], ["NANDI MOLEFE", "THABO"]),
        ("NANDI'S KITCHEN. O'BRIEN waits.", ["NANDI", "O'BRIEN"], ["NANDI", "O'BRIEN"]),
        (
            "Mr. Van der Merwe and Thabo. van Thabo",
            ["MR. VAN DER MERWE", "THABO"],
            ["Van der Merwe", "Thabo", "Thabo"],
        ),
    ]
    for text, names, want in fixtures:
        words = list(word.finditer(text))
        runs = _name_runs(text, name_tokens(names))
        assert [text[words[i].start() : words[j].end()] for i, j in runs] == want


def test_a_particle_after_a_possessive_or_a_hyphen_never_joins() -> None:
    names = ["THABO", "WET", "MR. VAN DER MERWE"]
    assert redact_all("Thabo's van Wet", names) == "a person's van a person"
    assert redact_all("Thabo van-der Wet", names) == "a person van-der a person"
