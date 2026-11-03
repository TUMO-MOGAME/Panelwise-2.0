"""T082: title_sex, character_sex, the AGE and SEX parts, and the judge's sex line
(storyboard.md §3.1, §6, §9; verify.md §3, §9), on the sipho-and-siphokazi sample."""

from functools import cache

from app.characters.sex import Sex
from app.grounding import EntityKind, Extraction, ProposedEntity, ground
from app.llm import Usage
from app.script import Action, Screenplay, parse_pdf
from app.storyboard import (
    PartKind,
    build_frame_prompt,
    character_sex,
    load_styles,
    sex_part,
    title_sex,
)
from app.storyboard.prompts import cites_this_shot
from app.storyboard.styles import PUBLIC_STYLES
from app.verify import FrameDescription
from app.verify.prompts import render_spec
from tests.script.conftest import ACTION, CUE, heading, layout
from tests.storyboard.conftest import shot_of
from tests.storyboard.test_invariant import check, keyed
from tools.build_samples import SAMPLES

SIPHOKAZI_SHE = "Siphokazi nods. She cannot stop the smile."


@cache
def sipho() -> tuple[Screenplay, Extraction]:
    screenplay = parse_pdf((SAMPLES / "sipho-and-siphokazi.pdf").read_bytes())
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {
                "kind": "character",
                "name": "SIPHOKAZI",
                "quotes": [SIPHOKAZI_SHE],
                "sex_word": "She",
            },
            {
                "kind": "character",
                "name": "MAMA THEMBI",
                "quotes": [
                    "MAMA THEMBI (60s), the shop's owner, watches her over half-moon glasses."
                ],
            },
            {"kind": "character", "name": "Gogo", "quotes": ["Gogo wrote it down. Look."]},
        )
    ]
    entities, report = ground(proposals, screenplay)
    return screenplay, Extraction(entities, report, ("m",), Usage(0, 0, 0))


def _element(screenplay: Screenplay, text: str) -> tuple[int, int]:
    for scene in screenplay.scenes:
        for i, e in enumerate(scene.elements):
            if isinstance(e, Action) and text in e.text:
                return scene.index, i
    raise AssertionError(text)


def test_title_sex() -> None:
    assert title_sex("MAMA THEMBI") is Sex.FEMALE
    assert title_sex("MR. DUBE") is Sex.MALE
    assert title_sex("OFFICER MOLOI") is None
    assert title_sex("SIPHO") is None


def test_character_sex_from_each_source_with_its_evidence() -> None:
    screenplay, extraction = sipho()
    assert character_sex("SIPHOKAZI", screenplay, extraction) == (Sex.FEMALE, SIPHOKAZI_SHE)
    assert character_sex("MAMA THEMBI", screenplay, extraction) == (Sex.FEMALE, "MAMA THEMBI")
    assert character_sex("SIPHO", screenplay, extraction) is None  # proposed by no one here


def test_the_age_part_carries_the_agreed_sex() -> None:
    screenplay, extraction = sipho()
    scene_index, i = _element(screenplay, "SIPHOKAZI (17)")
    shot = shot_of(screenplay, scene_index, [i], characters=["SIPHOKAZI", "MAMA THEMBI"])
    style = load_styles(PUBLIC_STYLES, None).get(None)
    prompt = build_frame_prompt(shot, screenplay, extraction, style, max_words=10_000)
    ages = [p.text for p in prompt.parts if p.kind is PartKind.AGE]
    assert ages == ["a 17-year-old girl", "a woman in her 60s"]
    assert cites_this_shot(prompt, shot, screenplay, extraction)


def test_a_sexed_character_with_no_age_gets_a_sex_part_that_claims_no_age() -> None:
    screenplay, extraction = sipho()
    found = sex_part("Gogo", screenplay, extraction)
    assert found is not None
    gogo = next(e for e in extraction.entities if e.name == "Gogo")
    assert found == ("a female person", gogo.quotes[0].span)  # the title, cited where she's named
    assert sex_part("SIPHOKAZI", screenplay, extraction) is None  # she has an age: AGE says it


def test_sources_that_disagree_give_no_sex() -> None:
    screenplay, extraction = sipho()
    # MAMA THEMBI's title says female; a grounded "he" would contradict it.
    from dataclasses import replace

    thembi = next(e for e in extraction.entities if e.name == "MAMA THEMBI")
    contradicted = replace(thembi, sex=Sex.MALE, sex_quote=thembi.quotes[0])
    other = replace(
        extraction,
        entities=tuple(contradicted if e is thembi else e for e in extraction.entities),
    )
    assert character_sex("MAMA THEMBI", screenplay, other) is None


ROWS = [
    (CUE - 4, "SEX PARTS"),
    None,
    (ACTION, "FADE IN:"),
    None,
    heading("1", "INT. HALL - DAY"),
    None,
    (ACTION, "MAMA NOSIPHO sweeps the step."),
    None,
    (ACTION, "NOMSA hums by the door. She waits."),
    None,
    (ACTION, "LINDA (40s), her coat wet, waits."),
    None,
    (ACTION, "LINDA, a tall man, nods."),
    None,
]


@cache
def hall() -> tuple[Screenplay, Extraction]:
    from app.script import parse_text

    screenplay = parse_text(layout(ROWS), [])
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {
                "kind": "character",
                "name": "MAMA NOSIPHO",
                "quotes": ["MAMA NOSIPHO sweeps the step."],
            },
            {
                "kind": "character",
                "name": "NOMSA",
                "quotes": ["NOMSA hums by the door. She waits."],
                "sex_word": "She",
            },
            {
                "kind": "character",
                "name": "LINDA",
                "quotes": ["LINDA (40s), her coat wet, waits.", "LINDA, a tall man, nods."],
                "sex_word": "man",
            },
        )
    ]
    entities, report = ground(proposals, screenplay)
    return screenplay, Extraction(entities, report, ("m",), Usage(0, 0, 0))


def _prompt(text: str, character: str):
    screenplay, extraction = hall()
    scene_index, i = _element(screenplay, text)
    shot = shot_of(screenplay, scene_index, [i], characters=[character])
    style = load_styles(PUBLIC_STYLES, None).get(None)
    return shot, style, build_frame_prompt(shot, screenplay, extraction, style, max_words=10_000)


def test_an_ageless_titled_character_gets_a_sex_part_and_no_age() -> None:
    screenplay, extraction = hall()
    shot, style, prompt = _prompt("MAMA NOSIPHO sweeps", "MAMA NOSIPHO")
    kinds = [p.kind for p in prompt.parts]
    assert PartKind.SEX in kinds and PartKind.AGE not in kinds
    sex = next(p for p in prompt.parts if p.kind is PartKind.SEX)
    nosipho = next(e for e in extraction.entities if e.name == "MAMA NOSIPHO")
    assert (sex.text, sex.span) == ("a female person", nosipho.quotes[0].span)
    assert cites_this_shot(prompt, shot, screenplay, extraction)
    check(prompt, shot, screenplay, extraction, style, 10_000)


def test_a_grounded_sex_part_cites_its_quote() -> None:
    screenplay, extraction = hall()
    shot, style, prompt = _prompt("NOMSA hums", "NOMSA")
    nomsa = next(e for e in extraction.entities if e.name == "NOMSA")
    assert nomsa.sex_quote is not None
    sex = next(p for p in prompt.parts if p.kind is PartKind.SEX)
    assert sex.span == nomsa.sex_quote.span
    check(prompt, shot, screenplay, extraction, style, 10_000)


def test_a_sex_part_with_another_span_or_text_is_refused() -> None:
    from dataclasses import replace

    import pytest

    screenplay, extraction = hall()
    shot, style, prompt = _prompt("MAMA NOSIPHO sweeps", "MAMA NOSIPHO")
    other_span = next(e for e in extraction.entities if e.name == "LINDA").quotes[0].span
    for bad in (
        replace(
            prompt,
            parts=tuple(
                replace(p, span=other_span) if p.kind is PartKind.SEX else p for p in prompt.parts
            ),
        ),
        replace(
            prompt,
            parts=tuple(
                replace(p, text="a male person") if p.kind is PartKind.SEX else p
                for p in prompt.parts
            ),
        ),
    ):
        assert not cites_this_shot(bad, shot, screenplay, extraction)
        with pytest.raises(AssertionError):
            check(bad, shot, screenplay, extraction, style, 10_000)


def test_keyed_refuses_a_sex_word_nothing_in_the_script_gives() -> None:
    _, extraction = sipho()
    assert not keyed("a female person", "OFFICER MOLOI", None, extraction)
    assert keyed("a female person", "MAMA THEMBI", None, extraction)


def test_the_introduction_against_a_grounded_word_gives_no_sex_and_a_sexless_age() -> None:
    screenplay, extraction = hall()
    linda = next(e for e in extraction.entities if e.name == "LINDA")
    assert linda.sex is Sex.MALE  # "a tall man": grounded, but the introduction says "her"
    assert character_sex("LINDA", screenplay, extraction) is None
    from app.storyboard import introduced_age

    assert introduced_age("LINDA", screenplay, extraction) is not None
    assert introduced_age("LINDA", screenplay, extraction)[0] == "a person in their 40s"  # type: ignore[index]


def _described() -> FrameDescription:
    return FrameDescription.model_validate(
        {
            "people": [{"position": "left", "appearance": "a teenage girl"}],
            "setting": "interior",
            "light": "day",
            "shot_size": "medium",
            "objects": [],
            "has_text": False,
            "text": [],
            "signature": False,
        }
    )


def test_the_judge_is_told_each_persons_sex_with_its_quote() -> None:
    screenplay, extraction = sipho()
    scene_index, i = _element(screenplay, SIPHOKAZI_SHE)
    shot = shot_of(screenplay, scene_index, [i], characters=["SIPHOKAZI", "SIPHO"])
    spec = render_spec(shot, screenplay.scenes[scene_index], screenplay, extraction, _described())
    assert f'sex (from the script): female, "{SIPHOKAZI_SHE}"' in spec
    assert spec.count("sex (from the script)") == 1  # nothing for SIPHO, who has none here
    assert any(e.kind is EntityKind.CHARACTER and e.name == "SIPHO" for e in extraction.entities)
