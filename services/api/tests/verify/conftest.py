"""The self-written lighthouse script (tests/script/conftest.py), its extraction, its shots."""

from typing import Any

import pytest

from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.script import Screenplay, Span, parse_text
from app.shots import Framing, Movement, Shot
from app.verify import FrameDescription, Judgement
from tests.script.conftest import two_page_text


@pytest.fixture
def screenplay() -> Screenplay:
    text, breaks = two_page_text()
    return parse_text(text, breaks)


@pytest.fixture
def extraction(screenplay: Screenplay) -> Extraction:
    proposals = [
        ProposedEntity.model_validate(p)
        for p in (
            {"kind": "character", "name": "NANDI", "quotes": ["NANDI (60s, oilskin coat)"]},
            {"kind": "character", "name": "THABO", "quotes": ["holding a torn map"]},
            {"kind": "prop", "name": "oilskin coat", "quotes": ["oilskin coat"]},
            {"kind": "prop", "name": "torn map", "quotes": ["a torn map"]},
        )
    ]
    entities, report = ground(proposals, screenplay)
    return Extraction(entities, report, ("fast-model",), Usage(0, 0, 0))


def kitchen_shot(**kw: Any) -> Shot:
    """Scene 0, element 0: 'Rain hammers the window. NANDI (60s, oilskin coat) pours tea…'"""
    return Shot(
        scene_index=0,
        number=1,
        framing=kw.get("framing", Framing.MEDIUM),
        movement=Movement.STATIC,
        elements=(0,),
        characters=kw.get("characters", ("NANDI",)),
        props=kw.get("props", ("oilskin coat",)),
        time_of_day=kw.get("time_of_day", "NIGHT"),
        rationale="Nandi at the stove.",
        span=Span(1, 7, 8),
        source=(
            "Rain hammers the window. NANDI (60s, oilskin coat) pours tea into two chipped mugs."
        ),
    )


def described(**kw: Any) -> FrameDescription:
    return FrameDescription.model_validate(
        {
            "people": kw.get("people", [{"position": "left", "appearance": "older woman"}]),
            "setting": kw.get("setting", "interior"),
            "light": kw.get("light", "night"),
            "shot_size": kw.get("shot_size", "medium"),
            "objects": kw.get("objects", [{"name": "coat", "category": "clothing", "held": False}]),
            "has_text": kw.get("has_text", False),
            "text": kw.get("text", []),
            "signature": kw.get("signature", False),
            "signature_text": kw.get("signature_text", []),
        }
    )


def judged(**kw: Any) -> Judgement:
    return Judgement.model_validate(
        {
            "people": kw.get("people", [{"person": 0, "character": "NANDI", "support": None}]),
            "objects": kw.get(
                "objects", [{"object": 0, "kind": "scripted_prop", "support": "oilskin coat"}]
            ),
        }
    )
