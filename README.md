# ErgoDox Recovery

ErgoDox Recovery is a local, guided tool for reconstructing an editable keymap
from the behavior you can observe on a SliceMK ErgoDox Wireless keyboard. It
does **not** reverse-engineer `CURRENT.UF2`: compiled firmware does not retain a
reliable copy of the original configurator project.

The tool detects a mounted UF2 bootloader drive, makes a verified backup, guides
you through one physical key at a time, and exports:

- `recovery.json`, the versioned source of truth for the recovery session
- `slicemk_ergodox.json`, compatible with the SliceMK configurator schema
- `config/slicemk_ergodox.keymap`, native ZMK devicetree source
- `recovery-report.md`, including confidence and unresolved-key checklists

The default build target is the legacy Raytac MDBT50Q-RX dongle:
`raytac_mdbt50q_rx` with shield `slicemk_ergodox_dongle`.

## Install for development

Python 3.14 and [`uv`](https://docs.astral.sh/uv/) are required.

```sh
git clone <repository-url> ergodox_recovery
cd ergodox_recovery
uv sync --extra dev
uv run ergodox-recovery --help
```

No runtime third-party packages are used.

## Recovery workflow

### 1. Detect and back up the dongle

Put the dongle into UF2 bootloader mode, then run:

```sh
uv run ergodox-recovery detect
uv run ergodox-recovery backup /run/media/glo/MDBT50QBOOT --output ./backups
```

The backup is placed in a new timestamp-and-hash directory. The copied UF2 and
its metadata are verified with SHA-256 and made read-only. Existing backups are
never overwritten.

### 2. Start a session

Create a session while the UF2 drive is mounted to retain device metadata:

```sh
uv run ergodox-recovery new recovery.json \
  --from-mount /run/media/glo/MDBT50QBOOT
```

Or create one for the default dongle target:

```sh
uv run ergodox-recovery new recovery.json
```

### 3. Recover the mapping

Reboot the dongle normally, make sure the keyboard works, then launch:

```sh
uv run ergodox-recovery serve recovery.json
```

The interface opens at `http://127.0.0.1:8765/`. For each layer:

1. Click a physical key in the diagram to select it.
2. Double-click that key; it turns red to show capture is armed.
3. Press only that physical keyboard key.
4. Confirm or manually edit the normalized ZMK binding.
5. Record tap-holds, macros, combos, Bluetooth actions, and layer actions
   manually; a host key event cannot reveal their firmware implementation.

Shifted symbols and chords can arrive as more than one browser event. The MVP
disarms after the first event, so enter these manually and mark their confidence
as confirmed rather than assuming automatic capture reconstructed the chord.

The session is saved after each capture or edit. Use `Ctrl-C` in the terminal to
stop the UI.

### 4. Validate and export

```sh
uv run ergodox-recovery validate recovery.json
uv run ergodox-recovery export recovery.json --output ./recovery-output
```

Export refuses unresolved keys and existing destination files by default. For
an intentional draft, use `--allow-unresolved`. To replace a prior export, use
`--force`. Draft exports map unresolved positions to `&none` and flag every one
in the report.

## Safety and privacy

- The server binds only to `127.0.0.1` and refuses non-loopback binding.
- A random per-run token protects its API, and write requests validate origin.
- The page disarms after one key or shifted-key chord, after a ten-second
  timeout, when it loses focus, or when hidden.
- Capture uses browser events only while the page is focused. The tool never
  reads `/dev/input`, installs a global keyboard hook, or asks for root access.
- Only normalized bindings are persisted. Raw key events, typed text,
  timestamps for individual keys, and clipboard data are never logged.
- The Content Security Policy prevents the UI from contacting remote services.
- The MVP does not build or flash firmware.

Do not type passwords or sensitive text while capture is armed. The persistent
red banner indicates when the one-event listener is active.

## What can and cannot be recovered

A basic output such as `A`, `RETURN`, or `LEFT_ARROW` can usually be observed
and normalized automatically. An observed output alone cannot prove whether it
came from `&kp`, a macro, a combo, a tap-hold, or another active layer. Hidden
layers also cannot be discovered unless you know how to activate them. The
report keeps confidence and notes alongside each position so uncertainty stays
visible instead of being silently converted into guessed firmware.

The generated ZMK keymap contains 76 visible bindings per layer in official
SliceMK configurator order, plus the dongle's required leading `&bootloader`
binding.

## Development

```sh
uv run pytest
uv run ruff check .
```

See [docs/design.md](docs/design.md) for file formats, architecture, and threat
model.
