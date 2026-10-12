"""Render recovery sessions into SliceMK JSON, ZMK source, and a review report."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .model import KEY_POSITIONS
from .session import Binding, Layer, RecoverySession


@dataclass(frozen=True, slots=True)
class ExportResult:
    recovery_json: Path
    slicemk_json: Path
    zmk_keymap: Path
    report: Path


def _layer_macro(layer: Layer, index: int) -> str:
    suffix = re.sub(r"[^A-Z0-9]+", "_", layer.id.upper()).strip("_") or str(index)
    return f"LAYER_{suffix}"


def _layer_lookup(session: RecoverySession) -> dict[str, tuple[Layer, int]]:
    result: dict[str, tuple[Layer, int]] = {}
    for index, layer in enumerate(session.layers):
        result[layer.id] = (layer, index)
        result[layer.name] = (layer, index)
    return result


def render_zmk_binding(
    binding: Binding | None,
    session: RecoverySession,
) -> str:
    if binding is None or binding.kind in {"unknown", "none"}:
        return "&none"
    if binding.kind == "transparent":
        return "&trans"
    if binding.kind == "key_press":
        return f"&kp {binding.value}"
    if binding.kind == "mod_tap":
        return f"&mt {binding.hold_value} {binding.value}"
    if binding.kind == "raw":
        return binding.value
    behavior = {
        "momentary_layer": "mo",
        "to_layer": "to",
        "toggle_layer": "tog",
    }[binding.kind]
    target_layer, index = _layer_lookup(session)[binding.target_layer]
    return f"&{behavior} {_layer_macro(target_layer, index)}"


def render_zmk_keymap(session: RecoverySession) -> str:
    session.validate()
    lines = [
        "#include <behaviors.dtsi>",
        "#include <dt-bindings/zmk/bt.h>",
        "#include <dt-bindings/zmk/keys.h>",
        "#include <dt-bindings/zmk/outputs.h>",
        "#include <dt-bindings/zmk/pointing.h>",
        "",
    ]
    for index, layer in enumerate(session.layers):
        lines.append(f"#define {_layer_macro(layer, index)} {index}")
    lines.extend(["", "/ {", "    keymap {", '        compatible = "zmk,keymap";', ""])
    for index, layer in enumerate(session.layers):
        node_name = re.sub(r"[^a-z0-9_]+", "_", layer.id.replace("-", "_")).strip("_")
        node_name = node_name or f"layer_{index}"
        lines.extend(
            [
                f"        {node_name} {{",
                f"            display-name = {json.dumps(layer.name, ensure_ascii=False)};",
                "            bindings = <",
                "                &bootloader",
            ]
        )
        offset = 0
        for count in (14, 14, 12, 14, 10, 4, 6, 2):
            row = KEY_POSITIONS[offset : offset + count]
            values = [
                render_zmk_binding(layer.bindings.get(position.id), session) for position in row
            ]
            lines.append("                " + "    ".join(values))
            offset += count
        lines.extend(["            >;", "        };", ""])
    lines.extend(["    };", "};", ""])
    return "\n".join(lines)


def _slicemk_key(binding: Binding | None, session: RecoverySession) -> dict[str, object]:
    name = ""
    notes = binding.notes if binding else "Unresolved during recovery"
    if binding is None or binding.kind in {"unknown", "none"}:
        behavior, args = "&none", []
    elif binding.kind == "transparent":
        behavior, args = "&trans", []
    elif binding.kind == "key_press":
        behavior, args = "&kp", [binding.value]
    elif binding.kind == "mod_tap":
        behavior, args = "&mt", [binding.hold_value, binding.value]
    elif binding.kind == "raw":
        tokens = binding.value.split()
        behavior, args = tokens[0], tokens[1:]
    else:
        behavior = {
            "momentary_layer": "&mo",
            "to_layer": "&to",
            "toggle_layer": "&tog",
        }[binding.kind]
        target_layer, _ = _layer_lookup(session)[binding.target_layer]
        args = [target_layer.name]
    return {"Name": name, "Behavior": behavior, "Notes": notes, "Args": args}


def render_slicemk_json(session: RecoverySession) -> dict[str, object]:
    session.validate()
    return {
        "Modified": session.updated_at,
        "Keyboard": "ergodox",
        "Board": session.target_board,
        "Shield": session.target_shield,
        "Peripheral": 40100,
        "Kconfig": None,
        "Advanced": {"Logging": "", "KRO": "", "MouseMove": "", "MouseScroll": "", "BTParams": ""},
        "Layers": [
            {
                "Name": layer.name,
                "Notes": layer.notes,
                "Keys": [
                    _slicemk_key(layer.bindings.get(position.id), session)
                    for position in KEY_POSITIONS
                ],
            }
            for layer in session.layers
        ],
        "Custom": "",
    }


def render_report(session: RecoverySession) -> str:
    session.validate()
    total = len(KEY_POSITIONS) * len(session.layers)
    assigned = sum(len(layer.bindings) for layer in session.layers)
    unresolved: list[tuple[str, str]] = []
    uncertain: list[tuple[str, str, str]] = []
    for layer in session.layers:
        for position in KEY_POSITIONS:
            binding = layer.bindings.get(position.id)
            if binding is None or binding.kind == "unknown":
                unresolved.append((layer.name, position.id))
            elif binding.confidence in {"unknown", "inferred"}:
                uncertain.append((layer.name, position.id, binding.confidence))

    lines = [
        f"# Recovery report: {session.name}",
        "",
        f"- Target: `{session.target_board}` / `{session.target_shield}`",
        f"- Layers: {len(session.layers)}",
        f"- Assigned positions: {assigned}/{total}",
        f"- Unresolved positions: {len(unresolved)}",
        "",
        "The generated keymap uses `&none` for unresolved positions. "
        "Review every such key before building firmware.",
        "",
    ]
    for layer in session.layers:
        lines.extend(
            [
                f"## {layer.name}",
                "",
                "| Position | Binding | Confidence | Notes |",
                "|---|---|---|---|",
            ]
        )
        for position in KEY_POSITIONS:
            binding = layer.bindings.get(position.id)
            rendered = render_zmk_binding(binding, session)
            confidence = binding.confidence if binding else "unknown"
            notes = (binding.notes if binding else "unresolved").replace("|", "\\|")
            lines.append(f"| `{position.id}` | `{rendered}` | {confidence} | {notes} |")
        lines.append("")
    if unresolved:
        lines.extend(["## Unresolved checklist", ""])
        lines.extend(f"- [ ] {layer}: `{position}`" for layer, position in unresolved)
        lines.append("")
    if uncertain:
        lines.extend(["## Needs confirmation", ""])
        lines.extend(
            f"- [ ] {layer}: `{position}` ({confidence})"
            for layer, position, confidence in uncertain
        )
        lines.append("")
    return "\n".join(lines)


def unresolved_positions(session: RecoverySession) -> list[tuple[str, str]]:
    return [
        (layer.name, position.id)
        for layer in session.layers
        for position in KEY_POSITIONS
        if ((binding := layer.bindings.get(position.id)) is None or binding.kind == "unknown")
    ]


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_exports(
    session: RecoverySession,
    output_dir: Path | str,
    *,
    allow_unresolved: bool = False,
    force: bool = False,
) -> ExportResult:
    session.validate()
    unresolved = unresolved_positions(session)
    if unresolved and not allow_unresolved:
        raise ValueError(
            f"refusing to export {len(unresolved)} unresolved positions; "
            "complete the recovery or explicitly allow unresolved keys"
        )
    destination = Path(output_dir).expanduser().resolve()
    config_dir = destination / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    recovery_path = destination / "recovery.json"
    slicemk_path = destination / "slicemk_ergodox.json"
    keymap_path = config_dir / "slicemk_ergodox.keymap"
    report_path = destination / "recovery-report.md"

    paths = (recovery_path, slicemk_path, keymap_path, report_path)
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "refusing to overwrite existing export files: "
            + ", ".join(str(path) for path in existing)
        )
    contents = (
        json.dumps(session.to_dict(), indent=2) + "\n",
        json.dumps(render_slicemk_json(session), indent=2) + "\n",
        render_zmk_keymap(session),
        render_report(session),
    )
    for path, content in zip(paths, contents, strict=True):
        _atomic_write(path, content)
    return ExportResult(recovery_path, slicemk_path, keymap_path, report_path)
