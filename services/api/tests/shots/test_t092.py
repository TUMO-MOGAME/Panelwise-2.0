"""T092: a character the shot's own action names is in its cast (shots.md §3, §6, §9).
A self-written script; the planner's model is a MockTransport, so no network."""

import json
from typing import Any

import httpx2

from app.grounding import Extraction, ProposedEntity, ground
from app.llm import NebiusChatModel, Tier, Usage
from app.projects.codec import dump_plan, load_plan
from app.script import Screenplay, parse_text
from app.shots import PlanReport, plan_shots
from app.shots.planner import named_in_action
from app.storyboard.prompt import build_frame_prompt
from app.storyboard.prompts import cites_this_shot
from app.storyboard.styles import Style, StyleOrigin
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading, layout

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "r", Tier.VISION: "v"}


def _scene(number: str, place: str, *rows: Row) -> list[Row]:
    out: list[Row] = [heading(number, f"EXT. {place} - DAY"), None]
    for row in rows:
        out += [row] if row is not None and row[0] == CUE else [row, None]
    return out


ROWS: list[Row] = [
    (CUE - 4, "BACKFILL TESTS"),
    None,
    *_scene(
        "1",
        "PITCH",
        (ACTION, "LINDI (14), small, with oversized gloves, waits. PALESA (15) stretches."),
        (ACTION, "Lindi rolls the ball out to Palesa."),
        (ACTION, "The Lionesses' goalkeeper waves. The board reads LIONESSES 1 - EAGLES 1."),
        (CUE, "LINDI"),
        (DIALOGUE, "Palesa, run!"),
        (ACTION, "He looks across at Jabu's paper."),
    ),
    *_scene(
        "2",
        "SUBURBAN STREET",
        (ACTION, "MR. VAN DER MERWE (50s), orange overalls, waits by the truck."),
        (ACTION, "A truck pulls up. Mr. Van der Merwe climbs down with a crowbar."),
        (ACTION, "Marmalade, the ginger cat, leaves in disgust. Dube winds his watch."),
    ),
    *_scene("3", "PORCH", (ACTION, "MR. DUBE (60s) and MRS. DUBE (60s) sit.")),
    *_scene("4", "LANE", (ACTION, "Mr. Van der Merwe climbs down from the cab.")),
    *_scene("5", "YARD", (ACTION, "Oom Piet waits by the gate. MR. VAN DER MERWE (50s) waves.")),
]


def screenplay() -> Screenplay:
    return parse_text(layout(ROWS), [])


def extraction(sp: Screenplay) -> Extraction:
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {"kind": "character", "name": "LINDI", "quotes": ["LINDI (14), small"]},
            {"kind": "character", "name": "PALESA", "quotes": ["PALESA (15) stretches"]},
            {"kind": "character", "name": "LIONESSES", "quotes": ["LIONESSES 1"]},
            {"kind": "character", "name": "JABU", "quotes": ["Jabu's paper"]},
            # only scene 2's introduction: the planner of scene 2 is offered him, scene 1 isn't
            {
                "kind": "character",
                "name": "MR. VAN DER MERWE",
                "quotes": ["MR. VAN DER MERWE (50s), orange overalls"],
            },
            {
                "kind": "character",
                "name": "MARMALADE",
                "quotes": ["Marmalade, the ginger cat"],
                "species": "cat",
            },
            {"kind": "character", "name": "MR. DUBE", "quotes": ["MR. DUBE (60s)"]},
            {"kind": "character", "name": "MRS. DUBE", "quotes": ["MRS. DUBE (60s)"]},
        )
    ]
    entities, report = ground(proposals, sp)
    return Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


def test_a_title_case_name_in_a_covered_action_line_is_named() -> None:
    sp = screenplay()
    ex = extraction(sp)
    assert named_in_action(sp.scenes[0], [1], ex, sp) == ("LINDI", "PALESA")


def test_an_introduction_is_named_and_possessives_and_boards_are_not() -> None:
    sp = screenplay()
    ex = extraction(sp)
    assert named_in_action(sp.scenes[0], [0], ex, sp) == ("LINDI", "PALESA")
    assert named_in_action(sp.scenes[0], [2], ex, sp) == ()  # the goalkeeper's, the board
    assert named_in_action(sp.scenes[0], [4], ex, sp) == ()  # Jabu's paper


def test_a_paired_other_name_counts_as_its_character() -> None:
    sp = screenplay()
    proposals = [
        ProposedEntity.model_validate(
            {
                "kind": "character",
                "name": "MR. VAN DER MERWE",
                "quotes": ["MR. VAN DER MERWE (50s), orange overalls"],
                "other_names": ["Oom Piet"],
            }
        )
    ]
    entities, report = ground(proposals, sp)
    ex = Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))
    vdm = next(e for e in ex.entities if e.name == "MR. VAN DER MERWE")
    assert "Oom Piet" in vdm.other_names
    assert named_in_action(sp.scenes[4], [0], ex, sp) == ("MR. VAN DER MERWE",)


def test_dialogue_and_speakers_name_no_one() -> None:
    sp = screenplay()
    ex = extraction(sp)
    assert named_in_action(sp.scenes[0], [3], ex, sp) == ()


def test_only_covered_elements_are_read() -> None:
    sp = screenplay()
    ex = extraction(sp)
    assert named_in_action(sp.scenes[1], [0], ex, sp) == ("MR. VAN DER MERWE",)
    assert named_in_action(sp.scenes[1], [2], ex, sp) == ("MARMALADE",)


def test_a_token_two_characters_share_names_neither() -> None:
    sp = screenplay()
    ex = extraction(sp)
    names = [e.name for e in ex.entities]
    assert "MR. DUBE" in names and "MRS. DUBE" in names  # both grounded, so DUBE is shared
    # DUBE is both MR. DUBE's and MRS. DUBE's: neither is added; the cat still is.
    assert "MR. DUBE" not in named_in_action(sp.scenes[1], [2], ex, sp)
    assert "MRS. DUBE" not in named_in_action(sp.scenes[1], [2], ex, sp)


def shot(first: int, last: int, characters: list[str]) -> dict[str, Any]:
    return {
        "first": first,
        "last": last,
        "framing": "medium",
        "movement": "static",
        "characters": characters,
        "props": [],
        "rationale": "covers the beat",
    }


class Scripted:
    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        scene = json.loads(request.content)["messages"][-1]["content"]
        if "PITCH" in scene:
            shots = [shot(0, 0, []), shot(1, 1, ["PALESA"]), shot(2, 4, ["LINDI"])]
        elif "YARD" in scene:
            shots = [shot(0, 0, [])]
        elif "LANE" in scene:
            shots = [shot(0, 0, [])]
        elif "PORCH" in scene:
            shots = [shot(0, 0, ["MR. DUBE", "MRS. DUBE"])]
        else:
            shots = [shot(0, 0, ["MR. VAN DER MERWE"]), shot(1, 2, [])]
        return httpx2.Response(
            200,
            json={
                "model": "fast-model",
                "choices": [{"message": {"content": json.dumps({"shots": shots})}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            },
        )


def make() -> NebiusChatModel:
    async def no_sleep(_: float) -> None:
        return None

    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(Scripted()),
        sleep=no_sleep,
    )


async def test_plan_shots_appends_the_named_after_the_models_and_counts_them() -> None:
    sp = screenplay()
    plan = await plan_shots(make(), sp, extraction(sp))
    ex = extraction(sp)
    order = [e.name for e in ex.entities]
    vdm_cat = tuple(sorted(["MR. VAN DER MERWE", "MARMALADE"], key=order.index))
    casts = [s.characters for s in plan.shots]
    assert casts == [
        ("LINDI", "PALESA"),  # the model listed no one
        ("PALESA", "LINDI"),  # the model's first, then extraction order
        ("LINDI",),  # nothing new: the possessive and the board add no one
        ("MR. VAN DER MERWE",),  # already the model's: not twice
        vdm_cat,  # the model listed no one: extraction order
        ("MR. DUBE", "MRS. DUBE"),
        ("MR. VAN DER MERWE",),  # L019: never offered to this scene's planner
        ("MR. VAN DER MERWE",),
    ]
    assert plan.report.characters_added == 2 + 1 + 0 + 0 + 2 + 0 + 1 + 1
    vdm = next(e for e in ex.entities if e.name == "MR. VAN DER MERWE")
    assert 3 not in vdm.scenes  # so `_allowed` never offered him in the lane


def test_a_name_in_two_shots_of_one_scene_counts_in_each() -> None:
    sp = screenplay()
    ex = extraction(sp)
    assert named_in_action(sp.scenes[0], [0], ex, sp) == ("LINDI", "PALESA")
    assert named_in_action(sp.scenes[0], [1], ex, sp) == ("LINDI", "PALESA")
    # the plan above: scene 1's first two shots add LINDI and PALESA to each (2 + 1)


def test_an_older_plan_report_with_no_characters_added_loads_as_zero() -> None:
    report = PlanReport(scenes=1, shots=1, ranges_repaired=0, characters_dropped=0, props_dropped=0)
    assert report.characters_added == 0


async def test_an_older_stored_plan_loads() -> None:
    sp = screenplay()
    plan = await plan_shots(make(), sp, extraction(sp))
    data = dump_plan(plan)
    del data["report"]["characters_added"]
    assert load_plan(data).report.characters_added == 0


async def test_the_backfilled_shot_draws_and_cites_the_named() -> None:
    sp = screenplay()
    ex = extraction(sp)
    plan = await plan_shots(make(), sp, ex)
    climb = plan.shots[4]
    assert "MARMALADE" in climb.characters  # an animal joins the cast, never a figure
    style = Style("s", "S", "d", "storyboard sketch", "", None, "", True, True, StyleOrigin.PUBLIC)
    prompt = build_frame_prompt(climb, sp, ex, style, max_words=80)
    text = ", ".join(p.text for p in prompt.parts)
    assert "one figure" in text
    assert "a man in his 50s" in text or "a person in their 50s" in text
    assert "a person climbs down" in text and "der" not in text.split()
    assert cites_this_shot(prompt, climb, sp, ex)
