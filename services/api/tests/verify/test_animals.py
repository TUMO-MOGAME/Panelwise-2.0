"""An animal character in the audit: described as an object, never a person (verify.md, T052)."""

from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.script import Screenplay, Span
from app.shots import Framing, Movement, Shot
from app.verify import JUDGE_PROMPT, Check, render_spec, run_checks
from tests.script.conftest import ACTION, Row, heading
from tests.storyboard.conftest import screenplay_of
from tests.verify.conftest import described, judged

ROWS: list[Row] = [
    heading("1", "INT. LOST PROPERTY OFFICE - NIGHT"),
    None,
    (ACTION, "A ginger cat, MARMALADE, sleeps on a pile of scarves. ZANELE reads."),
]


def office() -> tuple[Screenplay, Extraction, Shot]:
    screenplay = screenplay_of(ROWS)
    proposals = [
        ProposedEntity.model_validate(
            {
                "kind": "character",
                "name": name,
                "quotes": [quote],
                "species": species,
                "other_names": [],
            }
        )
        for name, quote, species in (
            ("MARMALADE", "A ginger cat, MARMALADE, sleeps", "cat"),
            ("ZANELE", "ZANELE reads.", None),
        )
    ]
    entities, report = ground(proposals, screenplay)
    extraction = Extraction(entities, report, ("m",), Usage(0, 0, 0))
    element = screenplay.scenes[0].elements[0]
    shot = Shot(
        0,
        1,
        Framing.MEDIUM,
        Movement.STATIC,
        (0,),
        ("ZANELE", "MARMALADE"),
        (),
        "NIGHT",
        "",
        Span(element.span.page, element.span.line_start, element.span.line_end),
        element.text,
    )
    return screenplay, extraction, shot


def test_the_spec_lists_an_animal_apart_from_the_characters() -> None:
    screenplay, extraction, shot = office()
    spec = render_spec(shot, screenplay.scenes[0], screenplay, extraction, described())
    characters = spec.split("Characters in this shot:")[1].split("Animals in this shot:")[0]
    assert "ZANELE" in characters and "MARMALADE" not in characters
    animals = spec.split("Animals in this shot:")[1].split("Props in this shot:")[0]
    assert "MARMALADE (cat)" in animals


def test_the_cat_described_as_an_animal_object_passes_and_is_not_missing() -> None:
    screenplay, extraction, shot = office()
    description = described(
        people=[{"position": "left", "appearance": "young woman reading"}],
        objects=[{"name": "cat", "category": "animal", "held": False}],
    )
    judgement = judged(
        people=[{"person": 0, "character": "ZANELE", "support": None}],
        objects=[{"object": 0, "kind": "scripted_prop", "support": "A ginger cat, MARMALADE"}],
    )
    checks, _, _ = run_checks(shot, screenplay.scenes[0], description, judgement, extraction)
    failed = {c.check for c in checks if not c.ok}
    assert Check.UNSCRIPTED_OBJECT not in failed
    assert Check.MISSING_CHARACTER not in failed
    assert Check.UNSCRIPTED_PERSON not in failed


def test_a_person_cannot_be_called_the_cat() -> None:
    screenplay, extraction, shot = office()
    description = described(
        people=[
            {"position": "left", "appearance": "young woman reading"},
            {"position": "right", "appearance": "man in a ginger coat"},
        ],
        objects=[],
    )
    judgement = judged(
        people=[
            {"person": 0, "character": "ZANELE", "support": None},
            {"person": 1, "character": "MARMALADE", "support": None},
        ],
        objects=[],
    )
    checks, _, _ = run_checks(shot, screenplay.scenes[0], description, judgement, extraction)
    assert Check.UNSCRIPTED_PERSON in {c.check for c in checks if not c.ok}


def test_the_judge_is_told_how_to_call_an_animal() -> None:
    assert "Animals in this shot" in JUDGE_PROMPT and "scripted_prop" in JUDGE_PROMPT
