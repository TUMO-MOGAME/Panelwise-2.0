"""app/api/v1/schemas.py against web.md §6: the TypeScript block is parsed from the doc and every
interface, nested object, nullability and string union compared with its Pydantic mirror."""

import re
import types
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeAliasType, Union, get_args, get_origin
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from app.api.v1 import schemas
from app.grounding import Extraction, ProposedEntity, ground
from app.llm import Usage
from app.projects.views import entity_views, lines_view, report_view, scene_views, shot_views
from app.script import Screenplay, Span, parse_text
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from tests.script.conftest import two_page_text

WEB_MD = Path(__file__).resolve().parents[4] / "docs" / "design" / "web.md"


# --- a small reader for the doc's TypeScript ---------------------------------------------


@dataclass(frozen=True)
class Shape:
    kind: Literal["object", "list", "dict", "enum", "prim", "tuple"]
    nullable: bool = False
    fields: tuple[tuple[str, Shape], ...] = ()
    item: Shape | None = None
    values: frozenset[str] = frozenset()
    prim: str = ""  # string, number or boolean


def ts_block() -> str:
    doc = WEB_MD.read_text(encoding="utf-8")
    start = doc.index("**Response types**")
    body = doc[doc.index("```ts", start) + len("```ts") :]
    return re.sub(r"//[^\n]*", "", body[: body.index("```")])


def split_top(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth, current = 0, ""
    for ch in text:
        if ch in "{<(":
            depth += 1
        elif ch in "}>)":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


class TypeScript:
    def __init__(self, block: str) -> None:
        self.aliases: dict[str, str] = {}
        self.interfaces: dict[str, tuple[str | None, str]] = {}
        for match in re.finditer(r"type (\w+) = ([^;]+);", block):
            self.aliases[match.group(1)] = match.group(2)
        for match in re.finditer(r"interface (\w+)(?: extends (\w+))? \{", block):
            depth, i = 1, match.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(block[i], 0)
                i += 1
            self.interfaces[match.group(1)] = (match.group(2), block[match.end() : i - 1])

    def interface(self, name: str) -> Shape:
        parent, body = self.interfaces[name]
        fields = self.fields(body)
        if parent:
            fields = self.interface(parent).fields + fields
        return Shape("object", fields=fields)

    def fields(self, body: str) -> tuple[tuple[str, Shape], ...]:
        out: list[tuple[str, Shape]] = []
        for line in split_top(body.replace("\n", ";"), ";"):
            name, _, type_ = line.partition(":")
            out.append((name.strip(), self.shape(type_)))
        return tuple(out)

    def shape(self, type_: str) -> Shape:
        alternatives = split_top(type_, "|")
        nullable = "null" in alternatives
        alternatives = [a for a in alternatives if a != "null"]
        if all(a.startswith('"') for a in alternatives):
            return Shape("enum", nullable, values=frozenset(a.strip('"') for a in alternatives))
        (only,) = alternatives
        if only.endswith("[]"):
            return Shape("list", nullable, item=self.shape(only[:-2]))
        if only.startswith("[") and only.endswith("]"):  # a fixed-length tuple: [number, number]
            items = split_top(only[1:-1], ",")
            return Shape(
                "tuple",
                nullable,
                fields=tuple((str(i), self.shape(t)) for i, t in enumerate(items)),
            )
        if only.startswith("{"):
            return Shape("object", nullable, fields=self.fields(only[1:-1]))
        if only in self.interfaces:
            return Shape("object", nullable, fields=self.interface(only).fields)
        if only in self.aliases:
            inner = self.shape(self.aliases[only])
            return Shape(inner.kind, nullable, inner.fields, inner.item, inner.values, inner.prim)
        if only.startswith("Record<"):
            _, value = split_top(only[len("Record<") : -1], ",")
            return Shape("dict", nullable, item=self.shape(value))
        assert only in ("string", "number", "boolean"), f"unknown TypeScript type {only!r}"
        return Shape("prim", nullable, prim=only)


# --- the comparison ------------------------------------------------------------------------


def unwrap(annotation: Any) -> tuple[Any, bool]:
    """(the annotation without None, whether None was allowed)."""
    if isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if get_origin(annotation) in (types.UnionType, Union):
        args = [a for a in get_args(annotation) if a is not type(None)]
        (inner,) = args
        return unwrap(inner)[0], True
    return annotation, False


def compare(annotation: Any, shape: Shape, where: str) -> None:
    inner, nullable = unwrap(annotation)
    assert nullable == shape.nullable, f"{where}: nullable {nullable}, doc says {shape.nullable}"
    if shape.kind == "object":
        assert isinstance(inner, type) and issubclass(inner, BaseModel), where
        doc_names = [name for name, _ in shape.fields]
        assert list(inner.model_fields) == doc_names, f"{where}: {list(inner.model_fields)}"
        for name, field_shape in shape.fields:
            compare(inner.model_fields[name].annotation, field_shape, f"{where}.{name}")
    elif shape.kind == "tuple":
        assert get_origin(inner) is tuple, f"{where}: {inner} for a TypeScript tuple"
        items = get_args(inner)
        assert len(items) == len(shape.fields), (
            f"{where}: {len(items)} items, doc {len(shape.fields)}"
        )
        for item, (i, item_shape) in zip(items, shape.fields, strict=True):
            compare(item, item_shape, f"{where}[{i}]")
    elif shape.kind == "list":
        assert get_origin(inner) is list, where
        assert shape.item is not None
        compare(get_args(inner)[0], shape.item, f"{where}[]")
    elif shape.kind == "enum":
        if isinstance(inner, type) and issubclass(inner, Enum):
            values = {str(m.value) for m in inner}
        else:
            assert get_origin(inner) is Literal, where
            values = set(get_args(inner))
        assert values == set(shape.values), f"{where}: {values} vs {set(shape.values)}"
    elif shape.kind == "dict":
        assert get_origin(inner) is dict, where
        key, value = get_args(inner)
        assert key is str, where
        assert shape.item is not None
        compare(value, shape.item, f"{where}{{}}")
    else:
        # A doc `string` is a JSON string: str, or a UUID or datetime that serialises as one.
        allowed = {"string": (str, UUID, datetime), "number": (int, float), "boolean": (bool,)}
        assert inner in allowed[shape.prim], f"{where}: {inner} for a TypeScript {shape.prim}"


TS = TypeScript(ts_block())
NAMES = sorted(TS.interfaces)


def test_the_doc_s_typescript_was_read() -> None:
    assert set(NAMES) >= {
        "Job",
        "ProjectSummary",
        "SpanRef",
        "QuoteView",
        "EntityView",
        "SceneView",
        "ReportView",
        "Project",
        "LinesView",
        "ShotView",
        "CheckView",
        "AuditView",
        "FrameView",
        "LetteringView",
        "ComicPanelView",
        "ComicPageView",
        "ComicView",
    }


@pytest.mark.parametrize("name", NAMES)
def test_every_interface_has_a_model_with_identical_fields(name: str) -> None:
    model = getattr(schemas, name)
    compare(model, TS.interface(name), name)


def test_the_comparison_catches_a_renamed_field() -> None:
    class Wrong(BaseModel):
        page: int
        start: int
        line_end: int

    with pytest.raises(AssertionError):
        compare(Wrong, TS.interface("SpanRef"), "SpanRef")


def test_the_comparison_catches_a_primitive_type_difference() -> None:
    class Wrong(BaseModel):
        page: str
        line_start: int
        line_end: int

    with pytest.raises(AssertionError):
        compare(Wrong, TS.interface("SpanRef"), "SpanRef")


def test_the_comparison_reads_a_tuple_item_by_item() -> None:
    rect = dict(TS.interface("LetteringView").fields)["rect"]
    assert (rect.kind, len(rect.fields)) == ("tuple", 4)

    class Short(BaseModel):
        rect: tuple[int, int, int]

    with pytest.raises(AssertionError, match="3 items, doc 4"):
        compare(Short.model_fields["rect"].annotation, rect, "rect")


def test_the_comparison_reads_a_record_s_value_union() -> None:
    positions = dict(TS.interface("AuditView").fields)["positions"]
    assert positions.kind == "dict"
    assert positions.item is not None
    assert positions.item.values == {"left", "centre", "right"}


def test_the_comparison_catches_a_nullability_difference() -> None:
    class Wrong(BaseModel):
        page: int
        line_start: int
        line_end: int | None

    with pytest.raises(AssertionError):
        compare(Wrong, TS.interface("SpanRef"), "SpanRef")


# --- JSON on the wire ----------------------------------------------------------------------


def test_built_views_serialise_with_the_doc_s_field_names() -> None:
    text, breaks = two_page_text()
    screenplay: Screenplay = parse_text(text, breaks)
    proposals = [
        ProposedEntity.model_validate(
            {"kind": "prop", "name": "torn map", "quotes": ["a torn map"]}
        )
    ]
    entities, report = ground(proposals, screenplay)
    extraction = Extraction(entities, report, ("m",), Usage(1, 1, 0))
    kitchen = screenplay.scenes[0]
    covered = kitchen.elements[2:4]
    plan = ShotPlan(
        (
            Shot(
                0,
                1,
                Framing.MEDIUM,
                Movement.STATIC,
                (2, 3),
                ("NANDI",),
                (),
                "NIGHT",
                "r",
                Span(1, covered[0].span.line_start, covered[-1].span.line_end),
                "\n".join(e.text for e in covered),
            ),
        ),
        PlanReport(1, 1, 0, 0, 0),
        ("m",),
        Usage(1, 1, 0),
    )
    built = {
        "LinesView": lines_view(screenplay),
        "SceneView": scene_views(screenplay, plan)[0],
        "EntityView": next(e for e in entity_views(extraction) if e.quotes),
        "ReportView": report_view(extraction, plan),
        "ShotView": shot_views(screenplay, extraction, plan)[0],
    }
    for name, view in built.items():
        dumped = view.model_dump(mode="json")
        assert set(dumped) == {n for n, _ in TS.interface(name).fields}, name
    shot = built["ShotView"].model_dump(mode="json")
    assert shot["framing"] == "medium" and shot["movement"] == "static"
    assert set(shot["segments"][0]) == {"line_start", "line_end", "cue", "extension", "on_screen"}
    assert set(shot["span"]) == {"page", "line_start", "line_end"}


def test_job_and_summary_serialise_ids_and_times_as_strings() -> None:
    job = schemas.Job(
        id=uuid.uuid4(),
        state="running",
        stage=schemas.Stage.EXTRACTING,
        progress=5,
        error=None,
        updated_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
    )
    summary = schemas.ProjectSummary(
        id=uuid.uuid4(),
        title="The Red Kite",
        created_at=datetime(2026, 9, 30, 11, tzinfo=UTC),
        pages=5,
        scenes=5,
        shots=None,
        frames=None,
        job=job,
    )
    dumped = summary.model_dump(mode="json")
    assert list(dumped) == [n for n, _ in TS.interface("ProjectSummary").fields]
    assert list(dumped["job"]) == [n for n, _ in TS.interface("Job").fields]
    assert dumped["job"]["stage"] == "extracting"
    assert isinstance(dumped["id"], str) and dumped["created_at"].startswith("2026-09-30T11:00")


# --- the one rule a FrameView enforces itself ---------------------------------------------


def frame(state: str, image_url: str | None, failure: str | None = None) -> schemas.FrameView:
    return schemas.FrameView.model_validate(
        {
            "shot_id": "1.1",
            "state": state,
            "attempt": 1,
            "max_renders": 3,
            "image_url": image_url,
            "withheld_check": None,
            "failure": failure,
            "audits": [],
        }
    )


@pytest.mark.parametrize("state", ["passed", "warned"])
def test_an_accepted_frame_may_carry_its_image(state: str) -> None:
    assert frame(state, "https://storage.test/signed").image_url is not None


@pytest.mark.parametrize("state", ["rendering", "auditing", "withheld", "failed"])
def test_no_image_url_outside_passed_and_warned(state: str) -> None:
    with pytest.raises(ValidationError, match="only for passed or warned"):
        frame(state, "https://storage.test/signed")
    assert frame(state, None).image_url is None


@pytest.mark.parametrize("failure", ["render", "restart"])
def test_only_a_failed_frame_says_why_it_failed(failure: str) -> None:
    assert frame("failed", None, failure).failure == failure
    with pytest.raises(ValidationError, match="only for failed frames"):
        frame("withheld", None, failure)
