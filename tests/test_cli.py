from __future__ import annotations

import json
from pathlib import Path

import pytest

from ergodox_recovery.cli import main
from ergodox_recovery.session import RecoverySession


def test_detect_json_reports_device(uf2_mount: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["detect", "--search-root", str(uf2_mount.parent), "--json"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 1
    assert output[0]["model"] == "Raytac MDBT50Q-RX"
    assert output[0]["target_board"] == "raytac_mdbt50q_rx"


def test_backup_command_creates_verified_copy(
    uf2_mount: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "backups"

    exit_code = main(["backup", str(uf2_mount), "--output", str(destination)])

    assert exit_code == 0
    assert len(list(destination.glob("backup-*/CURRENT.UF2"))) == 1
    output = capsys.readouterr().out
    assert "Backed up" in output
    assert "SHA-256:" in output


def test_new_validate_and_export_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session_path = tmp_path / "session.json"
    output_dir = tmp_path / "output"

    assert main(["new", str(session_path), "--name", "My recovery"]) == 0
    assert main(["validate", str(session_path)]) == 0
    assert main(["export", str(session_path), "--output", str(output_dir)]) == 2
    error = capsys.readouterr().err
    assert "refusing to export 76 unresolved positions" in error

    assert (
        main(
            [
                "export",
                str(session_path),
                "--output",
                str(output_dir),
                "--allow-unresolved",
            ]
        )
        == 0
    )
    assert (output_dir / "slicemk_ergodox.json").is_file()
    assert (output_dir / "config" / "slicemk_ergodox.keymap").is_file()


def test_new_refuses_to_overwrite_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session_path = tmp_path / "session.json"
    original = RecoverySession.new(name="Original")
    original.save(session_path)

    exit_code = main(["new", str(session_path), "--name", "Replacement"])

    assert exit_code == 2
    assert RecoverySession.load(session_path).name == "Original"
    assert "refusing to overwrite" in capsys.readouterr().err


def test_validate_reports_malformed_session_as_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session_path = tmp_path / "invalid.json"
    session_path.write_text("not json", encoding="utf-8")

    assert main(["validate", str(session_path)]) == 2
    assert "cannot load recovery session" in capsys.readouterr().err
