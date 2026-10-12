"""Versioned recovery session model with strict, human-readable JSON."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .model import POSITION_IDS

SCHEMA_VERSION = 1
SUPPORTED_BINDING_KINDS = frozenset(
    {
        "key_press",
        "none",
        "transparent",
        "momentary_layer",
        "to_layer",
        "toggle_layer",
        "mod_tap",
        "raw",
        "unknown",
    }
)
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_()+|.-]+$")
_SAFE_RAW = re.compile(r"^&[A-Za-z0-9_]+(?: [A-Za-z0-9_()+|.&-]+)*$")
_LAYER_ID = re.compile(r"^[a-z][a-z0-9-]*$")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_string(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field_name} must be a{' non-empty' if not allow_empty else ''} string")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{field_name} must not contain control characters or newlines")
    return value


@dataclass(slots=True)
class Binding:
    kind: str = "unknown"
    value: str = ""
    hold_value: str = ""
    target_layer: str = ""
    confidence: str = "unknown"
    notes: str = ""

    def validate(self) -> None:
        if self.kind not in SUPPORTED_BINDING_KINDS:
            raise ValueError(f"unsupported binding kind: {self.kind!r}")
        if self.confidence not in {"observed", "confirmed", "inferred", "unknown"}:
            raise ValueError(f"invalid binding confidence: {self.confidence!r}")
        _require_string(self.notes, "binding notes", allow_empty=True)
        if self.kind == "key_press":
            _require_string(self.value, "key_press value")
        elif self.kind == "mod_tap":
            _require_string(self.value, "mod_tap tap value")
            _require_string(self.hold_value, "mod_tap hold value")
        elif self.kind in {"momentary_layer", "to_layer", "toggle_layer"}:
            _require_string(self.target_layer, f"{self.kind} target_layer")
        elif self.kind == "raw":
            raw = _require_string(self.value, "raw binding")
            if not _SAFE_RAW.fullmatch(raw):
                raise ValueError("raw binding must be one safe, single-line ZMK binding")

        for field_name, token in (("value", self.value), ("hold_value", self.hold_value)):
            if self.kind != "raw" and token and not _SAFE_TOKEN.fullmatch(token):
                raise ValueError(f"binding {field_name} contains unsupported characters")

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Binding:
        if not isinstance(data, dict):
            raise ValueError("binding must be an object")
        allowed = {"kind", "value", "hold_value", "target_layer", "confidence", "notes"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown binding fields: {', '.join(sorted(unknown))}")
        binding = cls(**{key: data[key] for key in allowed if key in data})
        binding.validate()
        return binding


@dataclass(slots=True)
class Layer:
    id: str
    name: str
    notes: str = ""
    bindings: dict[str, Binding] = field(default_factory=dict)

    def validate(self) -> None:
        _require_string(self.id, "layer id")
        if not _LAYER_ID.fullmatch(self.id):
            raise ValueError("layer id must use lowercase letters, numbers, and hyphens")
        _require_string(self.name, "layer name")
        _require_string(self.notes, "layer notes", allow_empty=True)
        unknown_positions = set(self.bindings) - POSITION_IDS
        if unknown_positions:
            raise ValueError(f"unknown key positions: {', '.join(sorted(unknown_positions))}")
        for binding in self.bindings.values():
            binding.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "notes": self.notes,
            "bindings": {
                position_id: binding.to_dict()
                for position_id, binding in sorted(self.bindings.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layer:
        if not isinstance(data, dict):
            raise ValueError("layer must be an object")
        allowed = {"id", "name", "notes", "bindings"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown layer fields: {', '.join(sorted(unknown))}")
        raw_bindings = data.get("bindings", {})
        if not isinstance(raw_bindings, dict):
            raise ValueError("layer bindings must be an object")
        layer = cls(
            id=_require_string(data.get("id"), "layer id"),
            name=_require_string(data.get("name"), "layer name"),
            notes=_require_string(data.get("notes", ""), "layer notes", allow_empty=True),
            bindings={key: Binding.from_dict(value) for key, value in raw_bindings.items()},
        )
        layer.validate()
        return layer


@dataclass(slots=True)
class RecoverySession:
    schema_version: int
    session_id: str
    name: str
    created_at: str
    updated_at: str
    keyboard: str = "slicemk_ergodox"
    target_board: str = "raytac_mdbt50q_rx"
    target_shield: str = "slicemk_ergodox_dongle"
    device: dict[str, object] | None = None
    layers: list[Layer] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        name: str = "ErgoDox recovery",
        *,
        board: str = "raytac_mdbt50q_rx",
        shield: str = "slicemk_ergodox_dongle",
        device: dict[str, object] | None = None,
    ) -> RecoverySession:
        timestamp = utc_now()
        session = cls(
            schema_version=SCHEMA_VERSION,
            session_id=str(uuid.uuid4()),
            name=name,
            created_at=timestamp,
            updated_at=timestamp,
            target_board=board,
            target_shield=shield,
            device=device,
        )
        session.add_layer("base")
        return session

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; expected {SCHEMA_VERSION}"
            )
        _require_string(self.session_id, "session id")
        _require_string(self.name, "session name")
        _require_string(self.created_at, "created_at")
        _require_string(self.updated_at, "updated_at")
        if self.keyboard != "slicemk_ergodox":
            raise ValueError("keyboard must be 'slicemk_ergodox'")
        if self.device is not None and not isinstance(self.device, dict):
            raise ValueError("device must be an object or null")
        _require_string(self.target_board, "target_board")
        _require_string(self.target_shield, "target_shield")
        if not self.layers:
            raise ValueError("session must contain at least one layer")
        layer_ids = [layer.id for layer in self.layers]
        layer_names = [layer.name for layer in self.layers]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("layer ids must be unique")
        if len(layer_names) != len(set(layer_names)):
            raise ValueError("layer names must be unique")
        valid_targets = set(layer_ids) | set(layer_names)
        for layer in self.layers:
            layer.validate()
            for binding in layer.bindings.values():
                if (
                    binding.kind in {"momentary_layer", "to_layer", "toggle_layer"}
                    and binding.target_layer not in valid_targets
                ):
                    raise ValueError(f"binding references unknown layer {binding.target_layer!r}")

    def add_layer(self, name: str) -> Layer:
        clean_name = _require_string(name, "layer name").strip()
        if any(layer.name == clean_name for layer in self.layers):
            raise ValueError(f"layer name already exists: {clean_name}")
        base = re.sub(r"[^a-z0-9]+", "-", clean_name.casefold()).strip("-") or "layer"
        layer_id = base
        suffix = 2
        existing_ids = {layer.id for layer in self.layers}
        while layer_id in existing_ids:
            layer_id = f"{base}-{suffix}"
            suffix += 1
        layer = Layer(id=layer_id, name=clean_name)
        self.layers.append(layer)
        self.updated_at = utc_now()
        return layer

    def get_layer(self, layer_id: str) -> Layer:
        for layer in self.layers:
            if layer.id == layer_id or layer.name == layer_id:
                return layer
        raise KeyError(f"unknown layer: {layer_id}")

    def set_binding(
        self,
        layer_id: str,
        position_id: str,
        binding: Binding | dict[str, Any],
    ) -> None:
        if position_id not in POSITION_IDS:
            raise ValueError(f"unknown key position: {position_id}")
        normalized = binding if isinstance(binding, Binding) else Binding.from_dict(binding)
        normalized.validate()
        if normalized.kind in {"momentary_layer", "to_layer", "toggle_layer"}:
            valid_targets = {candidate.id for candidate in self.layers} | {
                candidate.name for candidate in self.layers
            }
            if normalized.target_layer not in valid_targets:
                raise ValueError(f"binding references unknown layer {normalized.target_layer!r}")
        self.get_layer(layer_id).bindings[position_id] = normalized
        self.updated_at = utc_now()
        self.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "keyboard": self.keyboard,
            "target": {"board": self.target_board, "shield": self.target_shield},
            "device": self.device,
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoverySession:
        if not isinstance(data, dict):
            raise ValueError("session must be an object")
        allowed = {
            "schema_version",
            "session_id",
            "name",
            "created_at",
            "updated_at",
            "keyboard",
            "target",
            "device",
            "layers",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown session fields: {', '.join(sorted(unknown))}")
        target = data.get("target")
        if not isinstance(target, dict):
            raise ValueError("target must be an object")
        if set(target) - {"board", "shield"}:
            raise ValueError("target contains unknown fields")
        raw_layers = data.get("layers")
        if not isinstance(raw_layers, list):
            raise ValueError("layers must be an array")
        schema_version = data.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("schema_version must be an integer")
        session = cls(
            schema_version=schema_version,
            session_id=_require_string(data.get("session_id"), "session id"),
            name=_require_string(data.get("name"), "session name"),
            created_at=_require_string(data.get("created_at"), "created_at"),
            updated_at=_require_string(data.get("updated_at"), "updated_at"),
            keyboard=_require_string(data.get("keyboard"), "keyboard"),
            target_board=_require_string(target.get("board"), "target board"),
            target_shield=_require_string(target.get("shield"), "target shield"),
            device=data.get("device"),
            layers=[Layer.from_dict(layer) for layer in raw_layers],
        )
        session.validate()
        return session

    @classmethod
    def load(cls, path: Path | str) -> RecoverySession:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot load recovery session: {error}") from error
        return cls.from_dict(data)

    def save(self, path: Path | str) -> Path:
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = utc_now()
        encoded = json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination
