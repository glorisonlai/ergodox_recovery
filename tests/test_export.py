from __future__ import annotations

import json
from pathlib import Path

import pytest

from ergodox_recovery.export import (
    render_report,
    render_slicemk_json,
    render_zmk_binding,
    render_zmk_keymap,
    unresolved_positions,
    write_exports,
)
from ergodox_recovery.model import KEY_POSITIONS
from ergodox_recovery.session import Binding, RecoverySession


@pytest.fixture
def complete_session() -> RecoverySession:
    session = RecoverySession.new(name="Fixture")
    for position in KEY_POSITIONS:
        session.set_binding(
            "base",
            position.id,
            Binding(kind="key_press", value="A", confidence="observed"),
        )
    return session


def test_unresolved_bindings_are_blocked_unless_explicitly_allowed(tmp_path: Path) -> None:
    session = RecoverySession.new()

    assert len(unresolved_positions(session)) == 76
    with pytest.raises(ValueError, match="refusing to export 76 unresolved positions"):
        write_exports(session, tmp_path)
    assert list(tmp_path.iterdir()) == []

    result = write_exports(session, tmp_path, allow_unresolved=True)
    assert all(
        path.is_file()
        for path in (
            result.recovery_json,
            result.slicemk_json,
            result.zmk_keymap,
            result.report,
        )
    )


def test_exports_never_overwrite_without_force(
    complete_session: RecoverySession, tmp_path: Path
) -> None:
    result = write_exports(complete_session, tmp_path)
    sentinel = "user-owned content\n"
    result.report.write_text(sentinel, encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_exports(complete_session, tmp_path)
    assert result.report.read_text(encoding="utf-8") == sentinel

    write_exports(complete_session, tmp_path, force=True)
    assert result.report.read_text(encoding="utf-8") != sentinel


def test_slicemk_export_matches_configurator_schema_types(
    complete_session: RecoverySession,
) -> None:
    exported = render_slicemk_json(complete_session)

    assert list(exported) == [
        "Modified",
        "Keyboard",
        "Board",
        "Shield",
        "Peripheral",
        "Kconfig",
        "Advanced",
        "Layers",
        "Custom",
    ]
    assert isinstance(exported["Modified"], str)
    assert exported["Kconfig"] is None
    assert exported["Peripheral"] == 40100
    assert exported["Advanced"] == {
        "Logging": "",
        "KRO": "",
        "MouseMove": "",
        "MouseScroll": "",
        "BTParams": "",
    }
    layers = exported["Layers"]
    assert isinstance(layers, list)
    assert len(layers) == 1
    assert len(layers[0]["Keys"]) == 76
    assert layers[0]["Keys"][0] == {
        "Name": "",
        "Behavior": "&kp",
        "Notes": "",
        "Args": ["A"],
    }


def test_zmk_export_has_required_bootloader_binding_and_76_physical_keys(
    complete_session: RecoverySession,
) -> None:
    rendered = render_zmk_keymap(complete_session)

    assert rendered.count("&bootloader") == 1
    assert rendered.count("&kp A") == 76
    assert 'compatible = "zmk,keymap";' in rendered
    assert 'display-name = "base";' in rendered


def test_layer_names_are_escaped_and_identifiers_are_sanitized() -> None:
    session = RecoverySession.new()
    layer = session.add_layer('Quotes " and / punctuation')
    session.set_binding(
        "base",
        KEY_POSITIONS[0].id,
        Binding(kind="momentary_layer", target_layer=layer.id, confidence="confirmed"),
    )

    rendered = render_zmk_keymap(session)

    assert 'display-name = "Quotes \\" and / punctuation";' in rendered
    assert "quotes_and_punctuation {" in rendered
    assert "#define LAYER_QUOTES_AND_PUNCTUATION 1" in rendered
    assert "&mo LAYER_QUOTES_AND_PUNCTUATION" in rendered


@pytest.mark.parametrize(
    ("binding", "expected"),
    [
        (None, "&none"),
        (Binding(kind="transparent"), "&trans"),
        (Binding(kind="key_press", value="ESC"), "&kp ESC"),
        (Binding(kind="mod_tap", hold_value="LCTRL", value="A"), "&mt LCTRL A"),
        (Binding(kind="raw", value="&bt BT_CLR"), "&bt BT_CLR"),
    ],
)
def test_zmk_binding_rendering(binding: Binding | None, expected: str) -> None:
    assert render_zmk_binding(binding, RecoverySession.new()) == expected


def test_report_lists_unresolved_and_escapes_table_notes() -> None:
    session = RecoverySession.new()
    session.set_binding(
        "base",
        KEY_POSITIONS[0].id,
        Binding(kind="key_press", value="A", confidence="inferred", notes="left | home"),
    )

    report = render_report(session)

    assert "Assigned positions: 1/76" in report
    assert "Unresolved positions: 75" in report
    assert "left \\| home" in report
    assert "## Needs confirmation" in report


def test_written_json_files_are_parseable(
    complete_session: RecoverySession, tmp_path: Path
) -> None:
    result = write_exports(complete_session, tmp_path)

    recovery = json.loads(result.recovery_json.read_text(encoding="utf-8"))
    slicemk = json.loads(result.slicemk_json.read_text(encoding="utf-8"))
    assert recovery["schema_version"] == 1
    assert len(slicemk["Layers"][0]["Keys"]) == 76
