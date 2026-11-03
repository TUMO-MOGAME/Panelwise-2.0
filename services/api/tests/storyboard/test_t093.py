"""T093: a He or She with no one drawn is the one cast person of that sex; one against every drawn
figure is left out (storyboard.md §3.1, §6, §9). A self-written script; no model."""

import pytest

from app.characters.labels import redaction_labels
from app.characters.sex import Sex
from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.script import Screenplay
from app.storyboard import PartKind as K
from app.storyboard import build_frame_prompt
from app.storyboard.prompt import (
    _script_text,  # pyright: ignore[reportPrivateUsage]
    pronoun_figure,
    pronoun_sentences,
    visible_characters,
)
from app.storyboard.prompts import cites_this_shot
from app.verify import Check, run_checks
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading
from tests.storyboard.conftest import STYLE, screenplay_of, shot_of
from tests.verify.conftest import described, judged

ROWS: list[Row] = [
    heading("1", "INT. DEPOT - DAY"),
    None,
    (ACTION, "MR. VAN DER MERWE (50s), orange overalls, waits."),  # 0
    None,
    (ACTION, "MR. DUBE (60s) and MS. MOLEFE (40s) sit. SAM (30s) stands."),  # 1
    None,
    (ACTION, "A small scruffy terrier, BISCUIT, sleeps."),  # 2
    None,
    (ACTION, "He looks at the ball. He puts it in his pocket."),  # 3
    None,
    (ACTION, "He looks up. She waves."),  # 4
    None,
    (CUE, "MR. VAN DER MERWE (V.O.)"),  # 5
    (DIALOGUE, "Keep it."),
    None,
    (ACTION, "Ms. Molefe nods. He shines his torch. She smiles."),  # 6
    None,
    (ACTION, "Mr. Dube waves. He nods. She smiles."),  # 7
    None,
    (ACTION, "Sam waves. She smiles."),  # 8
    None,
    (CUE, "MR. DUBE"),  # 9
    (DIALOGUE, "Well."),
    None,
    (ACTION, "She smiles. She waves."),  # 10
    None,
    (ACTION, "Mr. Dube waves. She smiles. Mr. Dube nods and sits down slowly by the door."),  # 11
    None,
    (ACTION, "She waves."),  # 12
]

VDM, DUBE, MOLEFE, SAM, BISCUIT = "MR. VAN DER MERWE", "MR. DUBE", "MS. MOLEFE", "SAM", "BISCUIT"


def setup() -> tuple[Screenplay, Extraction]:
    sp = screenplay_of(ROWS)
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {
                "kind": "character",
                "name": VDM,
                "quotes": ["MR. VAN DER MERWE (50s), orange overalls"],
            },
            {"kind": "character", "name": DUBE, "quotes": ["MR. DUBE (60s)"]},
            {"kind": "character", "name": MOLEFE, "quotes": ["MS. MOLEFE (40s)"]},
            {"kind": "character", "name": SAM, "quotes": ["SAM (30s) stands"]},
            {
                "kind": "character",
                "name": BISCUIT,
                "quotes": ["A small scruffy terrier, BISCUIT"],
                "species": "terrier",
            },
        )
    ]
    entities, report = ground(proposals, sp)
    return sp, Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("Mr. Dube nods. She waves.", [("Mr. Dube nods.", None), ("She waves.", Sex.FEMALE)]),
        ("He goes. She's here.", [("He goes.", Sex.MALE), ("She's here.", Sex.FEMALE)]),
        ("Hesitant, she waits.", [("Hesitant, she waits.", None)]),
        ("Then he goes.", [("Then he goes.", None)]),
        ("They go.", [("They go.", None)]),
        ('"He goes."', [('"He goes."', None)]),
        ('"Go." He nods.', [('"Go." He nods.', None)]),
        ("Helen waves.", [("Helen waves.", None)]),
    ],
)
def test_pronoun_sentences(given: str, want: list[tuple[str, Sex | None]]) -> None:
    got = pronoun_sentences(given)
    assert list(got) == want
    assert " ".join(p for p, _ in got) == given


def test_rule_1_draws_the_one_cast_person_of_that_sex() -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, [3], characters=[VDM])
    assert visible_characters(shot, sp, ex) == (VDM,)
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    kinds = {p.kind: p.text for p in prompt.parts}
    assert kinds[K.COUNT] == "one figure"
    assert kinds[K.AGE] == "a man in his 50s"
    assert kinds[K.LOOK] == "orange overalls"
    assert cites_this_shot(prompt, shot, sp, ex)


@pytest.mark.parametrize(
    ("elements", "cast"),
    [
        ([3], [VDM, DUBE]),  # two men
        ([3], [VDM, SAM]),  # one of unknown sex
        ([4], [VDM, MOLEFE]),  # He and She pieces
        ([3], [BISCUIT]),  # an animal is never the figure
        ([5, 3], [VDM]),  # the only man speaks off screen
    ],
)
def test_rule_1_draws_no_one(elements: list[int], cast: list[str]) -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, elements, characters=cast)
    assert pronoun_figure(shot, sp, ex) is None
    assert visible_characters(shot, sp, ex) == ()


def test_listeners_win_and_rule_2_reads_them() -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, [5, 12], characters=[VDM, MOLEFE])
    assert visible_characters(shot, sp, ex) == (MOLEFE,)  # T079: she hears the line
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.ACTION] == ["She waves."]


def actions(shot_elements: list[int], cast: list[str], budget: int = 100) -> list[str]:
    sp, ex = setup()
    shot = shot_of(sp, 0, shot_elements, characters=cast)
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=budget)
    assert cites_this_shot(prompt, shot, sp, ex)
    return [p.text for p in prompt.parts if p.kind is K.ACTION]


def test_rule_2_leaves_out_a_he_no_drawn_figure_has() -> None:
    assert actions([6], [MOLEFE]) == ["a person nods.", "She smiles."]


def test_rule_2_leaves_out_only_the_absent_sex() -> None:
    assert actions([7], [DUBE]) == ["a person waves. He nods."]


def test_rule_2_keeps_a_she_when_a_drawn_sex_is_unknown() -> None:
    assert actions([8], [SAM]) == ["a person waves. She smiles."]


def test_an_element_with_every_piece_left_out_gives_no_part() -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, [9, 10], characters=[DUBE])
    prompt = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    assert [p for p in prompt.parts if p.kind is K.ACTION] == []
    assert prompt.trimmed == 0
    assert cites_this_shot(prompt, shot, sp, ex)


def test_parts_follow_element_then_sentence_order() -> None:
    assert actions([7, 11], [DUBE]) == [
        "a person waves. He nods.",
        "a person waves.",
        "a person nods and sits down slowly by the door.",
    ]


def test_the_budget_works_on_the_split_parts() -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, [11], characters=[DUBE])
    full = build_frame_prompt(shot, sp, ex, STYLE, max_words=100)
    fixed = sum(len(p.text.split()) for p in full.parts if p.kind is not K.ACTION)
    # Room for the first run only: the tail run is dropped.
    one = build_frame_prompt(shot, sp, ex, STYLE, max_words=fixed + 3)
    assert [p.text for p in one.parts if p.kind is K.ACTION] == ["a person waves."]
    assert one.trimmed == 1
    # Less: the first run is cut too, and each counts.
    two = build_frame_prompt(shot, sp, ex, STYLE, max_words=fixed + 2)
    assert [p.text for p in two.parts if p.kind is K.ACTION] == ["a person"]
    assert two.trimmed == 2
    assert cites_this_shot(two, shot, sp, ex)


def test_the_audit_sees_the_pronoun_figure_on_screen() -> None:
    sp, ex = setup()
    shot = shot_of(sp, 0, [3], characters=[VDM])
    on_screen = visible_characters(shot, sp, ex)
    assert on_screen == (VDM,)
    description = described(
        people=[{"position": "centre", "appearance": "an adult man with a beard"}], objects=[]
    )
    judgement = judged(people=[{"person": 0, "character": None, "support": None}], objects=[])
    checks, _, _ = run_checks(shot, sp.scenes[0], description, judgement, ex, on_screen=on_screen)
    failed = {c.check: c.detail for c in checks if not c.ok}
    assert failed[Check.NO_CHARACTER] == f"none of {VDM} in frame"


def test_the_pronouns_are_read_on_the_redacted_text() -> None:
    sp, ex = setup()
    labels = redaction_labels(ex, sp)
    pieces = pronoun_sentences(_script_text("Mr. Dube nods. He waves.", labels))
    assert pieces == (("a person nods.", None), ("He waves.", Sex.MALE))
