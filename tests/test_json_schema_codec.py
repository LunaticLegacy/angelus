"""Symmetry tests for the dataclass-driven JSON codec."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
import unittest

from angelus.modules.settings_module.json_schema import (
    decode_record,
    encode_record,
)
from angelus.modules.settings_module.json_store import JsonSchemaError
from angelus.modules.settings_module.json_store import read_json
from pathlib import Path
from tempfile import TemporaryDirectory


class Mode(Enum):
    FAST = "fast"
    SAFE = "safe"


@dataclass(frozen=True)
class Inner:
    name: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Outer:
    id: str
    inner: Inner
    mode: Mode
    ratio: float
    enabled: bool
    note: str | None
    items: tuple[int, ...]
    labels: dict[str, str]
    kind: Literal["a", "b"]
    payload: dict[str, object] = field(default_factory=dict)


def sample() -> Outer:
    return Outer(
        id="x",
        inner=Inner("inner", ("one", "two")),
        mode=Mode.SAFE,
        ratio=1.5,
        enabled=True,
        note=None,
        items=(1, 2, 3),
        labels={"k": "v"},
        kind="b",
        payload={"nested": [1, "two", None, {"deep": True}]},
    )


class CodecRoundTripTests(unittest.TestCase):
    def test_encode_and_decode_are_inverse(self) -> None:
        value = sample()
        encoded = encode_record(value)

        self.assertEqual(decode_record(Outer, encoded), value)

    def test_encoded_keys_are_the_dataclass_fields(self) -> None:
        encoded = encode_record(sample())

        self.assertEqual(
            set(encoded),
            {"id", "inner", "mode", "ratio", "enabled", "note", "items", "labels", "kind", "payload"},
        )

    def test_tuple_becomes_a_json_array_and_decodes_back_to_tuple(self) -> None:
        encoded = encode_record(sample())

        self.assertEqual(encoded["items"], [1, 2, 3])
        self.assertEqual(decode_record(Outer, encoded).items, (1, 2, 3))

    def test_enum_is_persisted_by_value(self) -> None:
        encoded = encode_record(sample())

        self.assertEqual(encoded["mode"], "safe")
        self.assertIs(decode_record(Outer, encoded).mode, Mode.SAFE)


class CodecRejectionTests(unittest.TestCase):
    def test_missing_json_uses_default(self) -> None:
        with TemporaryDirectory() as directory:
            self.assertEqual(read_json(Path(directory) / "missing.json", {"empty": True}), {"empty": True})

    def test_malformed_existing_json_raises(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_json(path, {"empty": True})

    def test_unknown_key_is_rejected(self) -> None:
        encoded = encode_record(sample())
        encoded["extra"] = 1

        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

    def test_missing_key_is_rejected(self) -> None:
        encoded = encode_record(sample())
        del encoded["ratio"]

        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

    def test_wrong_scalar_type_is_rejected(self) -> None:
        encoded = encode_record(sample())
        encoded["ratio"] = "1.5"

        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

    def test_boolean_integer_confusion_is_rejected(self) -> None:
        encoded = encode_record(sample())
        encoded["items"] = [True]

        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

    def test_invalid_enum_and_literal_are_rejected(self) -> None:
        encoded = encode_record(sample())
        encoded["mode"] = "turbo"
        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

        encoded = encode_record(sample())
        encoded["kind"] = "c"
        with self.assertRaises(JsonSchemaError):
            decode_record(Outer, encoded)

    def test_non_json_passthrough_value_is_rejected_on_write(self) -> None:
        value = Outer(
            id="x", inner=Inner("i"), mode=Mode.FAST, ratio=1.0, enabled=False,
            note=None, items=(), labels={}, kind="a",
            payload={"when": datetime(2026, 10, 21)},
        )
        with self.assertRaises(JsonSchemaError):
            encode_record(value)

    def test_any_annotation_is_rejected(self) -> None:
        @dataclass(frozen=True)
        class UsesAny:
            value: Any

        with self.assertRaises(JsonSchemaError):
            decode_record(UsesAny, {"value": 1})
        with self.assertRaises(JsonSchemaError):
            encode_record(UsesAny(value=1))

    def test_init_false_field_is_rejected(self) -> None:
        @dataclass(frozen=True)
        class Computed:
            value: str
            derived: str = field(init=False, default="")

        with self.assertRaises(JsonSchemaError):
            decode_record(Computed, {"value": "x"})


if __name__ == "__main__":
    unittest.main()
