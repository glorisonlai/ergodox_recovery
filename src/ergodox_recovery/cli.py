"""Command-line entry point for ErgoDox Recovery."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from .backup import backup_device
from .device import device_from_mount, discover_devices
from .export import write_exports
from .server import create_server
from .session import RecoverySession


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ergodox-recovery",
        description="Local-only guided recovery for SliceMK ErgoDox keymaps.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    detect = subcommands.add_parser("detect", help="find mounted UF2 bootloader volumes")
    detect.add_argument("--search-root", action="append", type=Path)
    detect.add_argument("--json", action="store_true")

    backup = subcommands.add_parser("backup", help="back up CURRENT.UF2 with a SHA-256 manifest")
    backup.add_argument("mount", nargs="?", type=Path)
    backup.add_argument("--output", type=Path, required=True)

    new = subcommands.add_parser("new", help="create a new recovery session")
    new.add_argument("session", type=Path)
    new.add_argument("--name", default="ErgoDox recovery")
    new.add_argument("--board", default="raytac_mdbt50q_rx")
    new.add_argument("--shield", default="slicemk_ergodox_dongle")
    new.add_argument("--from-mount", type=Path)
    new.add_argument("--force", action="store_true")

    serve = subcommands.add_parser("serve", help="open the focused local capture interface")
    serve.add_argument("session", type=Path)
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")

    validate = subcommands.add_parser("validate", help="validate a recovery session")
    validate.add_argument("session", type=Path)

    export = subcommands.add_parser("export", help="generate recovery, SliceMK, and ZMK files")
    export.add_argument("session", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--allow-unresolved", action="store_true")
    export.add_argument("--force", action="store_true")
    return parser


def _detect(args: argparse.Namespace) -> int:
    devices = discover_devices(args.search_root)
    if args.json:
        print(json.dumps([device.to_dict() for device in devices], indent=2))
    elif not devices:
        print("No mounted UF2 bootloader volumes found.")
    else:
        for device in devices:
            backup_status = "CURRENT.UF2 available" if device.current_uf2 else "no CURRENT.UF2"
            print(f"{device.mount_path}: {device.model or 'unknown model'}")
            print(f"  Board-ID: {device.board_id or 'unknown'}")
            print(f"  Target: {device.target_board or 'unknown'} / {device.target_shield}")
            print(f"  Backup: {backup_status}")
    return 0


def _backup(args: argparse.Namespace) -> int:
    if args.mount:
        device = device_from_mount(args.mount)
    else:
        devices = discover_devices()
        if len(devices) != 1:
            raise ValueError(
                f"expected exactly one UF2 volume, found {len(devices)}; provide MOUNT"
            )
        device = devices[0]
    record = backup_device(device, args.output)
    print(f"Backed up {record.size} bytes to {record.firmware_path}")
    print(f"SHA-256: {record.sha256}")
    return 0


def _new(args: argparse.Namespace) -> int:
    destination = args.session.expanduser().resolve()
    if destination.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite existing session: {destination}")
    device = device_from_mount(args.from_mount) if args.from_mount else None
    board = device.target_board if device and device.target_board else args.board
    session = RecoverySession.new(
        args.name,
        board=board,
        shield=args.shield,
        device=device.to_dict() if device else None,
    )
    session.save(destination)
    print(f"Created {destination}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    server = create_server(args.session, port=args.port)
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print(f"Recovery UI: {url}")
    print("Serving on loopback only. Press Ctrl-C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def _validate(args: argparse.Namespace) -> int:
    session = RecoverySession.load(args.session)
    print(
        f"Valid schema v{session.schema_version}: {len(session.layers)} layer(s), "
        f"target {session.target_board} / {session.target_shield}"
    )
    return 0


def _export(args: argparse.Namespace) -> int:
    session = RecoverySession.load(args.session)
    result = write_exports(
        session,
        args.output,
        allow_unresolved=args.allow_unresolved,
        force=args.force,
    )
    print(f"Wrote {result.recovery_json}")
    print(f"Wrote {result.slicemk_json}")
    print(f"Wrote {result.zmk_keymap}")
    print(f"Wrote {result.report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    actions = {
        "detect": _detect,
        "backup": _backup,
        "new": _new,
        "serve": _serve,
        "validate": _validate,
        "export": _export,
    }
    try:
        return actions[args.command](args)
    except (FileExistsError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
