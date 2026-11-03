"""The stage columns' jsonb: `Screenplay`, `Extraction`, `ShotPlan` to JSON and back, lossless
(web.md §3, §7; T046). The read endpoints (T047) load them.

Driven by the dataclasses' own type hints, so a field added to script.md, grounding.md or shots.md
§6 is stored without touching this file. Every dataclass carries `"_t"`, its class name: that is
how a union like `Element = Action | Dialogue` comes back as the right class. Enums are stored as
their values, tuples as lists. A shape the types don't allow is a `CodecError`, never a guess.
"""

import dataclasses
import types
from enum import Enum
from functools import cache
from typing import Any, TypeAliasType, Union, cast, get_args, get_origin, get_type_hints

from app.grounding import Extraction
from app.script import Screenplay
from app.shots import ShotPlan


class CodecError(ValueError):
    """Stored data that doesn't fit the dataclasses: a bug or a stale row, never a user error."""


type Json = dict[str, Any] | list[Any] | str | int | float | bool | None


def _dump(value: object) -> Json:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {"_t": type(value).__name__}
        for field in dataclasses.fields(value):
            out[field.name] = _dump(getattr(value, field.name))
        return out
    if isinstance(value, Enum):
        return cast(Json, value.value)
    if isinstance(value, tuple | list):
        return [_dump(v) for v in cast(tuple[object, ...], value)]
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in cast(dict[object, object], value).items()}
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise CodecError(f"cannot store a {type(value).__name__}")


@cache
def _hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls)


def _load(hint: Any, data: Any, where: str) -> Any:
    while isinstance(hint, TypeAliasType):  # `type Element = Action | Dialogue`
        hint = hint.__value__
    origin = get_origin(hint)
    if origin in (Union, types.UnionType):
        options = get_args(hint)
        if data is None:
            if type(None) in options:
                return None
            raise CodecError(f"{where}: null where a value is required")
        tagged: list[type] = [
            o for o in options if isinstance(o, type) and dataclasses.is_dataclass(o)
        ]
        if tagged and isinstance(data, dict):
            name = cast(dict[str, Any], data).get("_t")
            match = [o for o in tagged if o.__name__ == name]
            if not match:
                raise CodecError(f"{where}: unknown type {name!r}")
            return _load(match[0], data, where)
        for option in options:
            if option is type(None):
                continue
            try:
                return _load(option, data, where)
            except CodecError:
                continue
        raise CodecError(f"{where}: no type in {hint} fits")
    if dataclasses.is_dataclass(hint) and isinstance(hint, type):
        if not isinstance(data, dict) or cast(dict[str, Any], data).get("_t") != hint.__name__:
            raise CodecError(f"{where}: expected a {hint.__name__}")
        record = cast(dict[str, Any], data)
        hints = _hints(hint)
        values: dict[str, Any] = {}
        for field in dataclasses.fields(hint):
            if field.name not in record:
                # T082: a field added later takes its default, so older rows still load.
                if field.default is not dataclasses.MISSING:
                    values[field.name] = field.default
                    continue
                if field.default_factory is not dataclasses.MISSING:
                    values[field.name] = field.default_factory()
                    continue
                raise CodecError(f"{where}.{field.name}: missing")
            values[field.name] = _load(
                hints[field.name], record[field.name], f"{where}.{field.name}"
            )
        return hint(**values)
    if origin is tuple:
        args = get_args(hint)
        if not isinstance(data, list):
            raise CodecError(f"{where}: expected a list")
        items = cast(list[Any], data)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_load(args[0], v, f"{where}[{i}]") for i, v in enumerate(items))
        if len(args) != len(items):
            raise CodecError(f"{where}: expected {len(args)} items")
        pairs = enumerate(zip(args, items, strict=True))
        return tuple(_load(a, v, f"{where}[{i}]") for i, (a, v) in pairs)
    if origin is dict:
        _, value_type = get_args(hint)
        if not isinstance(data, dict):
            raise CodecError(f"{where}: expected an object")
        return {
            k: _load(value_type, v, f"{where}.{k}") for k, v in cast(dict[str, Any], data).items()
        }
    if isinstance(hint, type) and issubclass(hint, Enum):
        try:
            return hint(data)
        except ValueError as exc:
            raise CodecError(f"{where}: {data!r} is not a {hint.__name__}") from exc
    if hint is float and isinstance(data, int | float) and not isinstance(data, bool):
        return float(data)
    if hint in (str, int, bool) and type(data) is hint:
        return data
    if hint is type(None) and data is None:
        return None
    raise CodecError(f"{where}: {type(data).__name__} is not a {hint}")


def dump_screenplay(value: Screenplay) -> dict[str, Any]:
    return cast(dict[str, Any], _dump(value))


def dump_extraction(value: Extraction) -> dict[str, Any]:
    return cast(dict[str, Any], _dump(value))


def dump_plan(value: ShotPlan) -> dict[str, Any]:
    return cast(dict[str, Any], _dump(value))


def load_screenplay(data: object) -> Screenplay:
    return cast(Screenplay, _load(Screenplay, data, "screenplay"))


def load_extraction(data: object) -> Extraction:
    return cast(Extraction, _load(Extraction, data, "extraction"))


def load_plan(data: object) -> ShotPlan:
    return cast(ShotPlan, _load(ShotPlan, data, "plan"))
