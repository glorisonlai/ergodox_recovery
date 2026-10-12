# MVP design

## Boundaries

The project is a recovery assistant, not a firmware decompiler. `CURRENT.UF2`
is archived as evidence but never parsed for a keymap. The only observation
surface is the focused browser page. Building and flashing firmware are outside
the MVP.

## Data flow

```text
INFO_UF2.TXT ──> device identity ──┐
CURRENT.UF2  ──> verified backup   │
                                  ├──> recovery.json ──> SliceMK JSON
focused, armed browser event ─────┘                  ├──> ZMK keymap
manual behavior confirmation ───────────────────────└──> review report
```

`recovery.json` is the canonical artifact. It has `schema_version: 1`, device
and target metadata, ordered layers, and sparse position-to-binding maps. A
missing binding remains unresolved. It is never treated as a confidently empty
key.

Each binding stores:

- `kind`: key press, layer action, mod-tap, raw advanced ZMK, none,
  transparent, or unknown
- `value`, `hold_value`, and `target_layer` as applicable
- `confidence`: observed, confirmed, inferred, or unknown
- `notes`: human context that cannot be inferred from host events

## Physical order

The model contains 76 visible keys. Complete visual rows contain
`14, 14, 12, 14, 10, 4, 6, 2` keys. This matches the official SliceMK
configurator ordering. A dongle build has a synthetic `&bootloader` position
before those keys, so generated ZMK layers each contain 77 bindings.

## Threat model

The browser is useful because it receives normal focused keyboard input without
Linux input-device permissions. A local web service still needs protection
from malicious remote pages probing localhost, so the service:

- binds only to IPv4 loopback;
- generates a high-entropy token per run and requires it for API calls;
- checks write-request origins;
- denies framing and sends a restrictive Content Security Policy;
- caps request size;
- emits no HTTP access log during capture;
- persists only the validated, normalized session model.

The page disarms after one non-repeated key or shifted-key chord, a ten-second
timeout, blur, or visibility loss. A standalone modifier is recorded when it is
released. The page does not retain the original browser `KeyboardEvent`.

Because modifier chords and shifted symbols may generate multiple host events,
one-event capture cannot recover them reliably. They require a manual binding;
the UI and README make that limitation explicit.

## Export policy

Normal export requires all positions on every layer to be resolved. Draft
export requires an explicit `--allow-unresolved` flag. Existing artifacts are
preserved unless `--force` is supplied; replacement uses atomic file writes.
Unresolved draft positions become `&none` and are prominent in the report.
