"""T109: the describer's answer capped in its grammar (verify.md § T109 contracts, §9 T109).

The limits go to `response_format` only; the prompt's schema text and `FrameDescription` stay as
they are. A list that reaches its limit is never passed silently.
"""

import copy
import json
from typing import Any

import httpx2

from app.grounding import Extraction
from app.llm import NebiusChatModel, Tier
from app.script import Screenplay
from app.verify import Check, describe_frame, run_checks
from app.verify.schema import (
    DESCRIPTION_LIMITS,
    DescriptionLimits,
    FrameDescription,
    description_grammar,
)
from tests.verify.conftest import described, judged, kitchen_shot

LIMITS = DESCRIPTION_LIMITS
PNG = b"\x89PNG\r\n\x1a\nnot-really-a-frame"
ACTION = "Rain hammers the window."  # an action line of the kitchen shot, no he/she


def _without_limits(schema: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    props, defs = out["properties"], out["$defs"]
    for key in ("people", "objects", "text", "signature_text"):
        props[key].pop("maxItems", None)
    for key in ("text", "signature_text"):
        props[key]["items"].pop("maxLength", None)
    defs["SeenPerson"]["properties"]["appearance"].pop("maxLength", None)
    defs["SeenObject"]["properties"]["name"].pop("maxLength", None)
    return out


def test_the_limits_are_the_contract_s() -> None:
    assert DESCRIPTION_LIMITS == DescriptionLimits(
        people=24,
        objects=40,
        text=40,
        text_chars=100,
        appearance_chars=200,
        object_name_chars=60,
        signature=5,
        signature_chars=60,
    )


def test_the_grammar_sets_the_limits_and_nothing_else() -> None:
    grammar = description_grammar()
    props, defs = grammar["properties"], grammar["$defs"]

    assert props["people"]["maxItems"] == 24
    assert props["objects"]["maxItems"] == 40
    assert props["text"]["maxItems"] == 40
    assert props["text"]["items"]["maxLength"] == 100
    # T107's signature_text: a name or initials, 5 entries of 60 (verify.md §3; Katlego, #212)
    assert props["signature_text"]["maxItems"] == 5
    assert props["signature_text"]["items"]["maxLength"] == 60
    assert defs["SeenPerson"]["properties"]["appearance"]["maxLength"] == 200
    assert defs["SeenObject"]["properties"]["name"]["maxLength"] == 60
    assert _without_limits(grammar) == FrameDescription.model_json_schema()


def test_the_grammar_follows_the_limits_it_is_given() -> None:
    small = DescriptionLimits(
        people=2,
        objects=3,
        text=4,
        text_chars=5,
        appearance_chars=6,
        object_name_chars=7,
        signature=8,
        signature_chars=9,
    )
    props = description_grammar(small)["properties"]
    assert (props["people"]["maxItems"], props["objects"]["maxItems"]) == (2, 3)
    assert (props["text"]["maxItems"], props["text"]["items"]["maxLength"]) == (4, 5)
    signature = props["signature_text"]
    assert (signature["maxItems"], signature["items"]["maxLength"]) == (8, 9)


def test_the_model_s_own_schema_has_no_limits() -> None:
    sent = json.dumps(FrameDescription.model_json_schema())
    assert "maxItems" not in sent and "maxLength" not in sent
    description_grammar()  # building a grammar never touches the model's schema
    assert json.dumps(FrameDescription.model_json_schema()) == sent


async def test_describe_frame_sends_the_grammar_and_shows_the_plain_schema() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "model": "vision-model",
                "choices": [{"message": {"content": described().model_dump_json()}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    model = NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models={Tier.FAST: "f", Tier.REASONING: "r", Tier.VISION: "vision-model"},
        transport=httpx2.MockTransport(handler),
        max_attempts=1,
    )
    description, _ = await describe_frame(model, PNG)

    assert description == described()
    (body,) = bodies
    assert body["response_format"]["json_schema"]["schema"] == description_grammar()
    assert body["max_tokens"] == 4096
    system = body["messages"][0]["content"]
    assert json.dumps(FrameDescription.model_json_schema()) in system
    assert "maxItems" not in system


# --- a list at its limit is never passed silently ---------------------------------------------


def _people(n: int) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """n described people: NANDI first, every other one supported by an action line."""
    people = [{"position": "left", "appearance": "older woman"}] + [
        {"position": "right", "appearance": "a man in a coat"} for _ in range(n - 1)
    ]
    calls = [{"person": 0, "character": "NANDI", "support": None}] + [
        {"person": i, "character": None, "support": ACTION} for i in range(1, n)
    ]
    return people, calls


def _check(results: tuple[Any, ...], check: Check) -> Any:
    return next(r for r in results if r.check is check)


def test_people_at_the_limit_fail_unscripted_person_with_the_limit_detail(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    people, calls = _people(LIMITS.people)
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=people),
        judged(people=calls),
        extraction,
    )

    result = _check(results, Check.UNSCRIPTED_PERSON)
    assert not result.ok
    assert result.detail == "24 people described, the limit: any more were not checked"


def test_people_under_the_limit_pass(screenplay: Screenplay, extraction: Extraction) -> None:
    people, calls = _people(LIMITS.people - 1)
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=people),
        judged(people=calls),
        extraction,
    )

    assert _check(results, Check.UNSCRIPTED_PERSON).ok


def test_the_limit_detail_joins_the_check_s_other_details(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    people, calls = _people(LIMITS.people)
    calls[1] = {"person": 1, "character": None, "support": None}  # a stranger, no support
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(people=people),
        judged(people=calls),
        extraction,
    )

    detail = _check(results, Check.UNSCRIPTED_PERSON).detail
    assert "person 1 (right, a man in a coat): no shot character, no support" in detail
    assert detail.endswith("24 people described, the limit: any more were not checked")


def _objects(n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """n unheld mugs, each a scripted prop the shot's own text supports: every one is checked
    (not clothing, which the object checks skip) and passes."""
    objects = [{"name": "mug", "category": "other", "held": False} for _ in range(n)]
    call = {"kind": "scripted_prop", "support": "two chipped mugs"}
    calls = [{"object": i, **call} for i in range(n)]
    return objects, calls


def test_an_object_the_checks_refuse_still_fails_under_the_limit(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    objects, calls = _objects(LIMITS.objects - 1)
    calls[0] = {"object": 0, "kind": "scripted_prop", "support": "no such line"}
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(objects=objects),
        judged(objects=calls),
        extraction,
    )

    result = _check(results, Check.BACKGROUND_OBJECT)
    assert result.detail == "object 0 (mug, other): prop without support"


def test_objects_at_the_limit_fail_background_object_soft(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    objects, calls = _objects(LIMITS.objects)
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(objects=objects),
        judged(objects=calls),
        extraction,
    )

    result = _check(results, Check.BACKGROUND_OBJECT)
    assert not result.ok
    assert result.detail == "40 objects described, the limit: any more were not checked"
    assert result.severity.value == "soft"


def test_objects_under_the_limit_pass(screenplay: Screenplay, extraction: Extraction) -> None:
    objects, calls = _objects(LIMITS.objects - 1)
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(objects=objects),
        judged(objects=calls),
        extraction,
    )

    assert _check(results, Check.BACKGROUND_OBJECT).ok


def test_text_at_its_limit_adds_nothing(screenplay: Screenplay, extraction: Extraction) -> None:
    results, _, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(has_text=True, text=["pours tea"] * LIMITS.text),  # the shot's own words
        judged(),
        extraction,
    )

    assert _check(results, Check.TEXT_IN_FRAME).ok
