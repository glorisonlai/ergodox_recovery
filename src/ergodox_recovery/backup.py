"""Read-only backup of the UF2 boot drive's firmware image and metadata."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .device import DetectedDevice


@dataclass(frozen=True, slots=True)
class BackupRecord:
    backup_directory: Path
    firmware_path: Path
    metadata_path: Path
    sha256: str
    size: int
    created_at: str
    source_mount: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for field in ("backup_directory", "firmware_path", "metadata_path"):
            result[field] = str(result[field])
        return result


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def backup_device(
    device: DetectedDevice,
    destination: Path | str,
    now: datetime | None = None,
) -> BackupRecord:
    """Copy CURRENT.UF2 to a new timestamped, read-only backup directory."""
    source = device.current_uf2
    if source is None or not source.is_file():
        raise ValueError(f"{device.mount_path} does not contain CURRENT.UF2")

    digest, expected_size = _hash_file(source)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    created_at = timestamp.isoformat().replace("+00:00", "Z")
    base = Path(destination).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    stem = f"backup-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}"
    backup_dir = base / stem
    counter = 1
    while True:
        try:
            backup_dir.mkdir(mode=0o700)
            break
        except FileExistsError:
            backup_dir = base / f"{stem}-{counter}"
            counter += 1

    firmware = backup_dir / "CURRENT.UF2"
    metadata_path = backup_dir / "metadata.json"
    try:
        with source.open("rb") as source_handle, firmware.open("xb") as destination_handle:
            shutil.copyfileobj(source_handle, destination_handle, 1024 * 1024)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
        copied_digest, copied_size = _hash_file(firmware)
        if copied_digest != digest or copied_size != expected_size:
            raise OSError("backup verification failed: copied firmware hash or size differs")

        metadata = {
            "schema_version": 1,
            "created_at": created_at,
            "source_mount": str(device.mount_path),
            "source_filename": "CURRENT.UF2",
            "sha256": digest,
            "size": expected_size,
            "device": device.to_dict(),
        }
        with metadata_path.open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        firmware.chmod(0o444)
        metadata_path.chmod(0o444)
    except Exception:
        # Leave a partial directory in place as evidence rather than deleting data.
        raise

    return BackupRecord(
        backup_directory=backup_dir,
        firmware_path=firmware,
        metadata_path=metadata_path,
        sha256=digest,
        size=expected_size,
        created_at=created_at,
        source_mount=str(device.mount_path),
    )
