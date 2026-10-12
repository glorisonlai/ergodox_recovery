from __future__ import annotations

from pathlib import Path

import pytest

INFO_UF2_TEXT = """\
UF2 Bootloader 0.5.0 lib/nrfx (v2.0.0) lib/tinyusb (0.9.0-22-g7cdeed54)
Model: Raytac MDBT50Q-RX
Board-ID: nRF52840-MDBT50Q_RX-verD
SoftDevice: not found
Date: May 18 2021
"""


@pytest.fixture
def info_uf2_text() -> str:
    return INFO_UF2_TEXT


@pytest.fixture
def uf2_mount(tmp_path: Path) -> Path:
    mount = tmp_path / "MDBT50QBOOT"
    mount.mkdir()
    (mount / "INFO_UF2.TXT").write_text(INFO_UF2_TEXT, encoding="utf-8")
    (mount / "CURRENT.UF2").write_bytes(b"UF2 test image\x00\xff" * 64)
    return mount
