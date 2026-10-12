"""Detect mounted UF2 bootloader volumes without touching USB devices directly."""

from __future__ import annotations

import getpass
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DetectedDevice:
    mount_path: Path
    model: str
    board_id: str
    bootloader: str
    date: str
    current_uf2: Path | None
    target_board: str | None
    target_shield: str = "slicemk_ergodox_dongle"

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["mount_path"] = str(self.mount_path)
        result["current_uf2"] = str(self.current_uf2) if self.current_uf2 else None
        return result


def parse_info_uf2(text: str) -> dict[str, str]:
    """Parse INFO_UF2.TXT's heading and colon-separated metadata."""
    result: dict[str, str] = {}
    for index, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if index == 0 and ":" not in line:
            result["Bootloader"] = line
            continue
        key, separator, value = line.partition(":")
        if separator and key.strip():
            result[key.strip()] = value.strip()
    return result


def infer_target_board(model: str, board_id: str = "") -> str | None:
    identity = f"{model} {board_id}".casefold()
    if "mdbt50q-rx" in identity:
        return "raytac_mdbt50q_rx_green" if "green" in identity else "raytac_mdbt50q_rx"
    if "mdbt50q-cx" in identity:
        return "raytac_mdbt50q_cx_blue"
    if "nrf52840" in identity and "dongle" in identity:
        return "nordic_nrf52840_dongle_slicemk"
    if "slicemk" in identity and "usbc" in identity and "mdbt50q" in identity:
        return "slicemk_usbc_mdbt50q_blue"
    return None


def default_search_roots() -> tuple[Path, ...]:
    username = getpass.getuser()
    return (Path("/run/media") / username, Path("/media") / username, Path("/Volumes"))


def _candidate_directories(root: Path, max_depth: int = 2) -> Iterable[Path]:
    if not root.is_dir():
        return
    queue: list[tuple[Path, int]] = [(root, 0)]
    seen: set[tuple[int, int]] = set()
    while queue:
        directory, depth = queue.pop(0)
        try:
            stat = directory.stat()
        except OSError:
            continue
        identity = (stat.st_dev, stat.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        yield directory
        if depth >= max_depth:
            continue
        try:
            with os.scandir(directory) as entries:
                children = [
                    Path(entry.path) for entry in entries if entry.is_dir(follow_symlinks=False)
                ]
        except OSError:
            continue
        queue.extend((child, depth + 1) for child in children)


def device_from_mount(mount_path: Path | str) -> DetectedDevice:
    mount = Path(mount_path).resolve()
    info_path = mount / "INFO_UF2.TXT"
    if not info_path.is_file():
        raise ValueError(f"not a mounted UF2 volume (missing {info_path})")
    try:
        metadata = parse_info_uf2(info_path.read_text(encoding="utf-8", errors="replace"))
    except OSError as error:
        raise ValueError(f"cannot read {info_path}: {error}") from error
    model = metadata.get("Model", "")
    board_id = metadata.get("Board-ID", "")
    current = mount / "CURRENT.UF2"
    return DetectedDevice(
        mount_path=mount,
        model=model,
        board_id=board_id,
        bootloader=metadata.get("Bootloader", ""),
        date=metadata.get("Date", ""),
        current_uf2=current if current.is_file() else None,
        target_board=infer_target_board(model, board_id),
    )


def discover_devices(search_roots: Iterable[Path | str] | None = None) -> list[DetectedDevice]:
    roots_source = default_search_roots() if search_roots is None else search_roots
    roots = tuple(Path(root) for root in roots_source)
    devices: list[DetectedDevice] = []
    seen_mounts: set[Path] = set()
    for root in roots:
        for candidate in _candidate_directories(root):
            if not (candidate / "INFO_UF2.TXT").is_file():
                continue
            try:
                device = device_from_mount(candidate)
            except ValueError:
                continue
            if device.mount_path not in seen_mounts:
                devices.append(device)
                seen_mounts.add(device.mount_path)
    return sorted(devices, key=lambda device: str(device.mount_path))
