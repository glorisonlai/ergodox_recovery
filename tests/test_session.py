from __future__ import annotations

import json
from pathlib import Path

import pytest

from ergodox_recovery.model import KEY_POSITIONS
from ergodox_recovery.session import Binding, RecoverySession


def test_new_session_has_versioned_base_layer_and_target() -> None:
    session = RecoverySession.new(name="Recovered board")

    assert session.schema_version == 1
    assert session.name == "Recovered board"
    assert session.keyboard == "slicemk_ergodox"
    assert session.target_board == "raytac_mdbt50q_rx"
    assert session.target_shield == "slicemk_ergodox_dongle"
    assert [(layer.id, layer.name) for layer in session.layers] == [("base", "base")]


def test_session_round_trip_preserves_bindings_and_device(tmp_path: Path) -> None:
    session = RecoverySession.new(device={"model": "Raytac MDBT50Q-RX"})
    session.add_layer("Symbols")
    session.set_binding(
        "base",
        KEY_POSITIONS[0].id,
        Binding(kind="key_press", value="A", confidence="observed", notes="captured"),
    )
    session.set_binding(
        "base",
        KEY_POSITIONS[1].id,
        Binding(kind="momentary_layer", target_layer="symbols", confidence="confirmed"),
    )
    destination = tmp_path / "nested" / "recovery.json"

    assert session.save(destination) == destination.resolve()
    restored = RecoverySession.load(destination)

    assert restored.to_dict() == session.to_dict()
    assert json.loads(destination.read_text(encoding="utf-8")) == session.to_dict()


@pytest.mark.parametrize(
    "binding",
    [
        Binding(kind="key_press", value="A; /delete-node/ keymap"),
        Binding(kind="raw", value="kp A"),
        Binding(kind="mod_tap", value="A", hold_value=""),
        Binding(kind="momentary_layer", target_layer="missing"),
        Binding(kind="key_press", value="A", confidence="guessed"),
    ],
)
def test_invalid_or_unsafe_bindings_are_rejected(binding: Binding) -> None:
    session = RecoverySession.new()

    with pytest.raises(ValueError):
        session.set_binding("base", KEY_POSITIONS[0].id, binding)


def test_unknown_position_is_rejected() -> None:
    session = RecoverySession.new()

    with pytest.raises(ValueError, match="unknown key position"):
        session.set_binding("base", "L99_99", Binding(kind="key_press", value="A"))


def test_schema_version_and_unknown_fields_are_rejected() -> None:
    payload = RecoverySession.new().to_dict()
    payload["schema_version"] = 999
    payload["surprise"] = True

    with pytest.raises(ValueError, match="unknown session fields"):
        RecoverySession.from_dict(payload)

    payload.pop("surprise")
    with pytest.raises(ValueError, match="unsupported schema_version"):
        RecoverySession.from_dict(payload)


def test_duplicate_layer_names_are_rejected() -> None:
    session = RecoverySession.new()

    with pytest.raises(ValueError, match="already exists"):
        session.add_layer("base")


def test_layer_names_cannot_contain_newlines() -> None:
    session = RecoverySession.new()

    with pytest.raises(ValueError, match="newlines"):
        session.add_layer('safe";\n/delete-node/ keymap')
