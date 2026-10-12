from __future__ import annotations

from pathlib import Path

import pytest

from ergodox_recovery.device import (
    device_from_mount,
    discover_devices,
    infer_target_board,
    parse_info_uf2,
)


def test_parse_info_uf2_extracts_heading_and_metadata(info_uf2_text: str) -> None:
    metadata = parse_info_uf2(info_uf2_text)

    assert metadata == {
        "Bootloader": ("UF2 Bootloader 0.5.0 lib/nrfx (v2.0.0) lib/tinyusb (0.9.0-22-g7cdeed54)"),
        "Model": "Raytac MDBT50Q-RX",
        "Board-ID": "nRF52840-MDBT50Q_RX-verD",
        "SoftDevice": "not found",
        "Date": "May 18 2021",
    }


@pytest.mark.parametrize(
    ("model", "board_id", "expected"),
    [
        ("Raytac MDBT50Q-RX", "nRF52840-MDBT50Q_RX-verD", "raytac_mdbt50q_rx"),
        ("Raytac MDBT50Q-RX Green", "", "raytac_mdbt50q_rx_green"),
        ("Raytac MDBT50Q-CX", "", "raytac_mdbt50q_cx_blue"),
        ("nRF52840 Dongle", "", "nordic_nrf52840_dongle_slicemk"),
        ("unknown", "unknown", None),
    ],
)
def test_infer_target_board(model: str, board_id: str, expected: str | None) -> None:
    assert infer_target_board(model, board_id) == expected


def test_device_from_mount_maps_real_dongle_metadata(uf2_mount: Path) -> None:
    device = device_from_mount(uf2_mount)

    assert device.mount_path == uf2_mount.resolve()
    assert device.model == "Raytac MDBT50Q-RX"
    assert device.board_id == "nRF52840-MDBT50Q_RX-verD"
    assert device.target_board == "raytac_mdbt50q_rx"
    assert device.target_shield == "slicemk_ergodox_dongle"
    assert device.current_uf2 == uf2_mount / "CURRENT.UF2"


def test_device_from_mount_rejects_non_uf2_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        device_from_mount(tmp_path)


def test_device_without_current_firmware_is_still_detected(uf2_mount: Path) -> None:
    (uf2_mount / "CURRENT.UF2").unlink()

    assert device_from_mount(uf2_mount).current_uf2 is None


def test_discover_devices_ignores_decoys_and_sorts_results(
    tmp_path: Path, uf2_mount: Path, info_uf2_text: str
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    second = root / "ZBOOT"
    second.mkdir()
    (second / "INFO_UF2.TXT").write_text(info_uf2_text, encoding="utf-8")
    decoy = root / "not-a-device"
    decoy.mkdir()
    (decoy / "CURRENT.UF2").write_bytes(b"not enough")

    devices = discover_devices([uf2_mount, root])

    assert [device.mount_path for device in devices] == sorted(
        [uf2_mount.resolve(), second.resolve()], key=str
    )


def test_discover_devices_deduplicates_overlapping_roots(uf2_mount: Path) -> None:
    devices = discover_devices([uf2_mount.parent, uf2_mount])

    assert len(devices) == 1
