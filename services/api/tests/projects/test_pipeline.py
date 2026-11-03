"""run_pipeline: web.md §3 (stages, bands), §4.1 (failure copy), §6 (the pipeline core).

MockTransport models, no network, no database.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fpdf import FPDF

from app.grounding import Extraction, ExtractionError
from app.llm import NebiusChatModel, Tier
from app.projects import pipeline
from app.projects.pipeline import (
    BANDS,
    NO_HEADINGS,
    NO_TEXT_LAYER,
    NOT_A_PDF,
    READ_FAILED,
    TOO_LONG,
    UNEXPECTED,
    PipelineError,
    Stage,
    StageResult,
    run_pipeline,
)
from app.script import Screenplay
from app.shots import ShotPlan
from tests.script.conftest import ACTION, PAGE_1, PAGE_2, pdf_bytes

MODELS = {Tier.FAST: "fast-model", Tier.REASONING: "r", Tier.VISION: "v"}
WEB_MD = Path(__file__).resolve().parents[4] / "docs" / "design" / "web.md"


class Models:
    """Token Factory, scripted: extraction chunks and scene plans told apart by the schema name.
    `fail_extract_on` / `fail_plan_on` fail the request whose user message contains the text."""

    def __init__(self, fail_extract_on: str | None = None, fail_plan_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_extract_on = fail_extract_on
        self.fail_plan_on = fail_plan_on

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        schema = body["response_format"]["json_schema"]["name"]
        text = body["messages"][-1]["content"]
        self.calls.append(schema)
        if schema == "ChunkEntities":
            if self.fail_extract_on and self.fail_extract_on in text:
                return httpx2.Response(400, json={"detail": "bad"})
            content: dict[str, Any] = {"entities": self.entities(text)}
        else:
            if self.fail_plan_on and self.fail_plan_on in text:
                return httpx2.Response(400, json={"detail": "bad"})
            bounds = re.search(r"(\d+) elements?, \[0\]", text)
            assert bounds is not None
            content = {"shots": [self.shot(int(bounds.group(1)))]}
        return httpx2.Response(
            200,
            json={
                "model": "fast-model",
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    @staticmethod
    def entities(chunk: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if "KITCHEN" in chunk:
            found.append(
                {"name": "NANDI", "kind": "character", "quotes": ["NANDI (60s, oilskin coat)"]}
            )
        if "GALLERY" in chunk:
            found.append({"name": "THABO", "kind": "character", "quotes": ["holding a torn map"]})
        return found

    @staticmethod
    def shot(count: int) -> dict[str, Any]:
        return {
            "first": 0,
            "last": count - 1,
            "framing": "wide",
            "movement": "static",
            "characters": [],
            "props": [],
            "rationale": "covers the scene",
        }


def make(handler: Models) -> NebiusChatModel:
    async def no_sleep(_: float) -> None:
        return None

    return NebiusChatModel(
        api_key="k",
        base_url="https://tf.test/v1",
        models=MODELS,
        transport=httpx2.MockTransport(handler),
        sleep=no_sleep,
    )


class Advances:
    """Records every on_advance call."""

    def __init__(self) -> None:
        self.seen: list[tuple[Stage, int, StageResult | None]] = []

    async def __call__(self, stage: Stage, progress: int, finished: StageResult | None) -> None:
        self.seen.append((stage, progress, finished))

    def stages(self) -> list[tuple[Stage, int]]:
        return [(stage, progress) for stage, progress, _ in self.seen]


GOOD_PDF = pdf_bytes([PAGE_1, PAGE_2])


def scanned_pdf() -> bytes:
    pdf = FPDF(format="letter")
    pdf.add_page()
    pdf.rect(20, 20, 50, 50)
    return bytes(pdf.output())


async def failure(
    pdf: bytes, handler: Models, advances: Advances | None = None, **kw: int
) -> PipelineError:
    with pytest.raises(PipelineError) as caught:
        await run_pipeline(pdf, make(handler), on_advance=advances or Advances(), **kw)
    return caught.value


# --- the good path ---------------------------------------------------------------------


async def test_a_good_pdf_is_parsed_extracted_and_planned() -> None:
    handler = Models()
    advances = Advances()
    result = await run_pipeline(GOOD_PDF, make(handler), on_advance=advances)

    assert [s.heading for s in result.screenplay.scenes] == [
        "INT. LIGHTHOUSE KITCHEN - NIGHT",
        "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS",
        "INT. LIGHTHOUSE STAIRWELL",
    ]
    assert {e.name for e in result.extraction.entities} >= {"NANDI", "THABO"}
    assert [(s.scene_index, s.number) for s in result.plan.shots] == [(0, 1), (1, 1), (2, 1)]
    assert handler.calls.count("ScenePlan") == 3


async def test_each_stage_is_announced_as_it_begins_with_the_result_before_it() -> None:
    advances = Advances()
    result = await run_pipeline(GOOD_PDF, make(Models()), on_advance=advances)

    assert advances.stages() == [
        (Stage.PARSING, 0),
        (Stage.EXTRACTING, 5),
        (Stage.PLANNING, 40),
    ]
    finished = [f for _, _, f in advances.seen]
    assert finished[0] is None
    assert finished[1] is result.screenplay
    assert finished[2] is result.extraction
    assert isinstance(finished[1], Screenplay)
    assert isinstance(finished[2], Extraction)
    assert isinstance(result.plan, ShotPlan)


def test_the_bands_are_web_md_s() -> None:
    assert dict(BANDS) == {
        Stage.PARSING: (0, 5),
        Stage.EXTRACTING: (5, 40),
        Stage.PLANNING: (40, 60),
        Stage.RENDERING: (60, 100),
    }
    assert [s.value for s in Stage] == ["parsing", "extracting", "planning", "rendering"]


async def test_the_next_stage_waits_for_the_hook() -> None:
    handler = Models()
    order: list[str] = []

    async def hook(stage: Stage, progress: int, finished: StageResult | None) -> None:
        # Yield to the loop several times: a stage started without awaiting the hook would run now.
        for _ in range(5):
            await asyncio.sleep(0)
        order.append(f"{stage}:{len(handler.calls)}")

    await run_pipeline(GOOD_PDF, make(handler), on_advance=hook)
    # No model call had been made when extraction's hook returned; every chunk was done by planning.
    assert order[1] == "extracting:0"
    assert order[2] == f"planning:{handler.calls.count('ChunkEntities')}"
    assert handler.calls.count("ScenePlan") == 3


async def test_an_exception_from_the_hook_propagates_unchanged_and_stops_the_run() -> None:
    handler = Models()

    class WriteFailed(Exception):
        pass

    async def hook(stage: Stage, progress: int, finished: StageResult | None) -> None:
        if stage is Stage.EXTRACTING:
            raise WriteFailed

    with pytest.raises(WriteFailed):
        await run_pipeline(GOOD_PDF, make(handler), on_advance=hook)
    assert handler.calls == []


# --- failures: each gives its §4.1 copy, at its stage ----------------------------------


@pytest.mark.parametrize(
    ("pdf", "copy"),
    [
        (b"this is not a pdf", NOT_A_PDF),
        (scanned_pdf(), NO_TEXT_LAYER),
        (pdf_bytes([[(ACTION, "Just some prose."), (ACTION, "No headings.")]]), NO_HEADINGS),
    ],
    ids=["not_a_pdf", "no_text_layer", "no_headings"],
)
async def test_each_parse_error_code_gives_its_copy(pdf: bytes, copy: str) -> None:
    handler = Models()
    advances = Advances()
    error = await failure(pdf, handler, advances)

    assert error.stage is Stage.PARSING
    assert error.message == str(error) == copy
    assert advances.stages() == [(Stage.PARSING, 0)]
    assert handler.calls == []


async def test_an_over_budget_script_fails_before_any_model_call() -> None:
    handler = Models()
    advances = Advances()
    error = await failure(GOOD_PDF, handler, advances, chunk_chars=1, max_chunks=2)

    assert (error.stage, error.message) == (Stage.EXTRACTING, TOO_LONG)
    assert handler.calls == []
    assert advances.stages() == [(Stage.PARSING, 0), (Stage.EXTRACTING, 5)]


async def test_a_script_exactly_at_the_budget_runs() -> None:
    handler = Models()
    await run_pipeline(GOOD_PDF, make(handler), on_advance=Advances(), chunk_chars=1, max_chunks=3)
    assert handler.calls.count("ChunkEntities") == 3


async def test_a_failed_extraction_chunk_names_its_scene() -> None:
    error = await failure(GOOD_PDF, Models(fail_extract_on="GALLERY"), chunk_chars=1)

    assert error.stage is Stage.EXTRACTING
    assert error.message == READ_FAILED.format(n="2")
    assert isinstance(error.__cause__, ExtractionError)


async def test_a_failed_planning_call_names_its_scene() -> None:
    advances = Advances()
    error = await failure(GOOD_PDF, Models(fail_plan_on="GALLERY"), advances)

    assert error.stage is Stage.PLANNING
    assert error.message == READ_FAILED.format(n="2")
    assert advances.stages()[-1] == (Stage.PLANNING, 40)


async def test_an_extraction_error_without_a_scene_is_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def budget(*_: object, **__: object) -> Extraction:
        raise ExtractionError("The script splits into 99 chunks")

    monkeypatch.setattr(pipeline, "extract", budget)
    error = await failure(GOOD_PDF, Models())
    assert (error.stage, error.message) == (Stage.EXTRACTING, TOO_LONG)


async def test_the_copy_never_carries_the_exception_text() -> None:
    error = await failure(GOOD_PDF, Models(fail_extract_on="GALLERY"), chunk_chars=1)
    assert "HTTP" not in error.message and "chunk" not in error.message
    assert "HTTP 400" in str(error.__cause__)  # the detail stays on the cause, for the log


async def test_anything_else_propagates_unmapped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*_: object, **__: object) -> Extraction:
        raise KeyError("a bug")

    monkeypatch.setattr(pipeline, "extract", broken)
    with pytest.raises(KeyError):
        await run_pipeline(GOOD_PDF, make(Models()), on_advance=Advances())


# --- the copy is web.md §4.1's, verbatim -------------------------------------------------


@pytest.mark.parametrize(
    "copy",
    [NOT_A_PDF, NO_TEXT_LAYER, NO_HEADINGS, TOO_LONG, READ_FAILED, UNEXPECTED],
    ids=["not_a_pdf", "no_text_layer", "no_headings", "too_long", "read_failed", "unexpected"],
)
def test_every_string_is_in_web_md_verbatim(copy: str) -> None:
    doc = " ".join(WEB_MD.read_text(encoding="utf-8").split())
    assert f'"{copy}"' in doc


def test_read_failed_takes_the_scene_number() -> None:
    assert READ_FAILED.format(n="12A").startswith("Reading the script failed at scene 12A.")
