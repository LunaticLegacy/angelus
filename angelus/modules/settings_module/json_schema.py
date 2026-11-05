"""One dataclass definition drives both directions of a persisted document.

``encode_record`` walks ``dataclasses.fields``; ``decode_record`` validates the
same field list, rejects unknown and missing keys, and rebuilds the instance
from its annotations.  A field added to the writer is therefore a decode error
until the reader knows how to restore it, which is the symmetry this module
exists to guarantee.

Supported annotations: dataclasses, ``str``/``int``/``float``/``bool``,
``Literal``, ``Enum`` subclasses, ``X | None``, ``list[X]``, ``tuple[X, ...]``,
``dict[str, X]``, and ``object`` (a recursively validated JSON value, used only
for third-party passthrough payloads).  ``Any`` is deliberately rejected.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
from types import UnionType
from typing import ForwardRef, Literal, TypeVar, Union, cast, get_args, get_origin, get_type_hints

from .json_store import (
    JsonSchemaError,
    reject_unknown_keys,
    require_int,
    require_list,
    require_mapping,
    require_number,
    require_string,
)

T = TypeVar("T")


def _persisted_fields(cls: type) -> tuple[str, ...]:
    """Return the field names that both directions must agree on.

    Raises:
        JsonSchemaError: If a field cannot be passed to the constructor, in
            which case it could never be restored.
    """
    names: list[str] = []
    for field in fields(cls):
        if not field.init:
            raise JsonSchemaError(
                f"{cls.__name__}.{field.name} has init=False and cannot round-trip"
            )
        names.append(field.name)
    return tuple(names)


def encode_record(value: object, where: str = "record") -> dict[str, object]:
    """Encode a dataclass instance as the object ``decode_record`` accepts.

    Args:
        value: Dataclass instance from the domain layer.
        where: Dotted path used in failure messages.

    Returns:
        JSON-safe object keyed by every persisted field.

    Raises:
        JsonSchemaError: If ``value`` is not a dataclass or a field has no
            JSON representation.
    """
    if not is_dataclass(value) or isinstance(value, type):
        raise JsonSchemaError(f"{where} must be a dataclass instance")
    hints = _type_hints(type(value))
    names = _persisted_fields(type(value))
    for name in names:
        _assert_supported(hints[name], f"{where}.{name}", set())
    return {
        name: encode_value(object.__getattribute__(value, name), f"{where}.{name}")
        for name in names
    }


def encode_value(value: object, where: str) -> object:
    """Encode one field value without losing the type it will decode back to."""
    if is_dataclass(value) and not isinstance(value, type):
        return encode_record(value, where)
    if isinstance(value, Enum):
        return encode_value(value.value, where)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise JsonSchemaError(f"{where} is not a finite JSON number")
        return value
    if isinstance(value, (list, tuple)):
        items = cast("list[object] | tuple[object, ...]", value)
        return [
            encode_value(item, f"{where}[{index}]")
            for index, item in enumerate(items)
        ]
    if isinstance(value, dict):
        encoded: dict[str, object] = {}
        for key, item in cast("dict[object, object]", value).items():
            if not isinstance(key, str):
                raise JsonSchemaError(f"{where} has a non-string key")
            encoded[key] = encode_value(item, f"{where}.{key}")
        return encoded
    raise JsonSchemaError(
        f"{where} has no JSON representation: {type(value).__name__}"
    )


def decode_record(cls: type[T], value: object, where: str | None = None) -> T:
    """Decode one object into ``cls``, requiring every persisted field.

    Args:
        cls: Dataclass whose annotations define the schema.
        value: Decoded JSON value from an untrusted document.
        where: Dotted path used in failure messages.

    Returns:
        Reconstructed dataclass instance.

    Raises:
        JsonSchemaError: If a key is unknown or missing, or a value does not
            match its annotation.
    """
    location = where or cls.__name__
    raw = require_mapping(value, location)
    names = _persisted_fields(cls)
    reject_unknown_keys(raw, names, location)
    missing = [name for name in names if name not in raw]
    if missing:
        raise JsonSchemaError(
            f"{location} is missing fields: {', '.join(missing)}"
        )
    hints = _type_hints(cls)
    return cls(
        **{
            name: decode_value(hints[name], raw[name], f"{location}.{name}")
            for name in names
        }
    )


def decode_value(annotation: object, value: object, where: str) -> object:
    """Decode one JSON value against its declared annotation."""
    if isinstance(annotation, ForwardRef):
        # A residual forward reference can only be a recursive JSON alias
        # (``JsonValue`` inside ``JsonObject``): get_type_hints has already
        # rejected genuinely missing names, so validate the value as JSON.
        return validate_json(value, where)
    if annotation is Path:
        return Path(require_string(value, where))
    origin = get_origin(annotation)
    arguments = get_args(annotation)

    if annotation is object:
        return validate_json(value, where)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            raise JsonSchemaError(
                f"{where} is not a valid {annotation.__name__}: {value!r}"
            ) from exc
    if isinstance(annotation, type) and is_dataclass(annotation):
        return decode_record(annotation, value, where)
    if origin is Literal:
        if value not in arguments:
            raise JsonSchemaError(f"{where} must be one of {arguments}")
        return value
    if origin in (Union, UnionType):
        return _decode_union(arguments, value, where)
    if origin is list:
        if len(arguments) != 1:
            raise JsonSchemaError(f"{where} has an unsupported list annotation")
        return [
            decode_value(arguments[0], item, f"{where}[{index}]")
            for index, item in enumerate(require_list(value, where))
        ]
    if origin is tuple:
        return _decode_tuple(arguments, value, where)
    if origin is dict:
        if arguments != (str, object) and arguments[0] is not str:
            raise JsonSchemaError(f"{where} must map string keys to one type")
        raw = require_mapping(value, where)
        return {
            key: decode_value(arguments[1], item, f"{where}.{key}")
            for key, item in raw.items()
        }
    if annotation is bool:
        if not isinstance(value, bool):
            raise JsonSchemaError(f"{where} must be a boolean")
        return value
    if annotation is int:
        return require_int(value, where)
    if annotation is float:
        return require_number(value, where)
    if annotation is str:
        return require_string(value, where)
    raise JsonSchemaError(f"{where} has unsupported annotation {annotation!r}")


def validate_json(value: object, where: str) -> object:
    """Prove that a value is representable as JSON, and return it unchanged.

    Used only for ``object`` annotations that carry a third-party passthrough
    payload.  Unlike ``Any``, a non-JSON value (datetime, model, callable) is
    rejected instead of being serialized blindly.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise JsonSchemaError(f"{where} is not a finite JSON number")
        return value
    if isinstance(value, list):
        items = cast("list[object]", value)
        for index, item in enumerate(items):
            validate_json(item, f"{where}[{index}]")
        return items
    if isinstance(value, dict):
        fields = cast("dict[object, object]", value)
        for key, item in fields.items():
            if not isinstance(key, str):
                raise JsonSchemaError(f"{where} has a non-string key")
            validate_json(item, f"{where}.{key}")
        return fields
    raise JsonSchemaError(
        f"{where} is not a JSON value: {type(value).__name__}"
    )


def _assert_supported(annotation: object, where: str, seen: set[object]) -> None:
    """Reject an annotation the decoder could not restore from its JSON form.

    Encoding runs this before writing, so an untyped field cannot be persisted
    into a document that the reader would refuse.  ``typing.Any`` falls through
    to the final rejection without being named here.  ``seen`` also breaks
    recursive aliases such as ``JsonValue``.
    """
    if annotation in seen:
        return
    seen.add(annotation)
    if isinstance(annotation, ForwardRef):
        # Residual refs are recursive JSON aliases; see decode_value.
        return
    if annotation is object:
        return
    if annotation is Path:
        return
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return
    if isinstance(annotation, type) and is_dataclass(annotation):
        hints = _type_hints(annotation)
        for name in _persisted_fields(annotation):
            _assert_supported(hints[name], f"{where}.{name}", seen)
        return
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        return
    if origin in (Union, UnionType):
        for item in arguments:
            if item is not type(None):
                _assert_supported(item, where, seen)
        return
    if origin is list:
        if len(arguments) != 1:
            raise JsonSchemaError(f"{where} has an unsupported list annotation")
        _assert_supported(arguments[0], where, seen)
        return
    if origin is tuple:
        for item in arguments:
            if item is not Ellipsis:
                _assert_supported(item, where, seen)
        return
    if origin is dict:
        if arguments[0] is not str:
            raise JsonSchemaError(f"{where} must map string keys to one type")
        _assert_supported(arguments[1], where, seen)
        return
    if annotation in (bool, int, float, str):
        return
    raise JsonSchemaError(f"{where} has unsupported annotation {annotation!r}")


def _type_hints(cls: type) -> dict[str, object]:
    """Resolve annotations once per class, surfacing forward-ref mistakes."""
    try:
        return get_type_hints(cls)
    except NameError as exc:
        raise JsonSchemaError(
            f"{cls.__name__} has an unresolvable annotation: {exc}"
        ) from exc


def _decode_union(arguments: tuple[object, ...], value: object, where: str) -> object:
    """Decode ``X | None`` and small unions without guessing silently."""
    non_null = [item for item in arguments if item is not type(None)]
    if value is None:
        if len(non_null) != len(arguments):
            return None
        raise JsonSchemaError(f"{where} must not be null")
    failures: list[str] = []
    for candidate in non_null:
        try:
            return decode_value(candidate, value, where)
        except JsonSchemaError as exc:
            failures.append(str(exc))
    raise JsonSchemaError(
        f"{where} matches no union branch: {'; '.join(failures)}"
    )


def _decode_tuple(
    arguments: tuple[object, ...], value: object, where: str
) -> tuple[object, ...]:
    """Decode both fixed-length and homogeneous tuples."""
    items = require_list(value, where)
    if len(arguments) == 2 and arguments[1] is Ellipsis:
        return tuple(
            decode_value(arguments[0], item, f"{where}[{index}]")
            for index, item in enumerate(items)
        )
    if len(items) != len(arguments):
        raise JsonSchemaError(
            f"{where} must have {len(arguments)} items, got {len(items)}"
        )
    return tuple(
        decode_value(annotation, item, f"{where}[{index}]")
        for index, (annotation, item) in enumerate(zip(arguments, items))
    )
