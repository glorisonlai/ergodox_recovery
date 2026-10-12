from __future__ import annotations

import hashlib
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ergodox_recovery.backup import backup_device
from ergodox_recovery.device import device_from_mount


def test_backup_copies_verifies_and_records_firmware(uf2_mount: Path, tmp_path: Path) -> None:
    source = uf2_mount / "CURRENT.UF2"
    original = source.read_bytes()
    timestamp = datetime(2026, 10, 13, 5, 30, tzinfo=UTC)

    record = backup_device(device_from_mount(uf2_mount), tmp_path / "backups", now=timestamp)

    expected_hash = hashlib.sha256(original).hexdigest()
    assert record.sha256 == expected_hash
    assert record.size == len(original)
    assert record.created_at == "2026-10-13T05:30:00Z"
    assert record.firmware_path.read_bytes() == original
    metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
    assert metadata["schema_version"] == 1
    assert metadata["sha256"] == expected_hash
    assert metadata["size"] == len(original)
    assert metadata["source_mount"] == str(uf2_mount.resolve())
    assert metadata["device"]["target_board"] == "raytac_mdbt50q_rx"


def test_backup_is_read_only_and_does_not_modify_source(uf2_mount: Path, tmp_path: Path) -> None:
    source = uf2_mount / "CURRENT.UF2"
    original_mode = stat.S_IMODE(source.stat().st_mode)
    original = source.read_bytes()

    record = backup_device(device_from_mount(uf2_mount), tmp_path / "backups")

    assert source.read_bytes() == original
    assert stat.S_IMODE(source.stat().st_mode) == original_mode
    assert stat.S_IMODE(record.firmware_path.stat().st_mode) == 0o444
    assert stat.S_IMODE(record.metadata_path.stat().st_mode) == 0o444
    assert stat.S_IMODE(record.backup_directory.stat().st_mode) & 0o077 == 0


def test_backup_never_overwrites_existing_backup(uf2_mount: Path, tmp_path: Path) -> None:
    timestamp = datetime(2026, 10, 13, tzinfo=UTC)
    first = backup_device(device_from_mount(uf2_mount), tmp_path, now=timestamp)
    second = backup_device(device_from_mount(uf2_mount), tmp_path, now=timestamp)

    assert first.backup_directory != second.backup_directory
    assert second.backup_directory.name.endswith("-1")
    assert first.firmware_path.read_bytes() == second.firmware_path.read_bytes()


def test_backup_requires_current_uf2(uf2_mount: Path, tmp_path: Path) -> None:
    (uf2_mount / "CURRENT.UF2").unlink()

    with pytest.raises(ValueError, match="CURRENT.UF2"):
        backup_device(device_from_mount(uf2_mount), tmp_path / "backups")
