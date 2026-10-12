"""The 76 visible key positions in SliceMK configurator order."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class KeyPosition:
    id: str
    index: int
    row: int
    side: str
    column: int
    visual_column: int
    label: str
    width: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# Number of visible keys on one half for each visual row. These rows correspond
# to the official configurator's ergodox.js layout. Each complete row is left
# half followed by right half; flattening all rows gives SliceMK's 76-key order.
HALF_ROW_KEY_COUNTS: tuple[int, ...] = (7, 7, 6, 7, 5, 2, 3, 1)


def _make_positions() -> tuple[KeyPosition, ...]:
    positions: list[KeyPosition] = []
    index = 0
    for row, count in enumerate(HALF_ROW_KEY_COUNTS):
        for side in ("left", "right"):
            prefix = "L" if side == "left" else "R"
            for column in range(count):
                position_id = f"{prefix}{row}_{column}"
                positions.append(
                    KeyPosition(
                        id=position_id,
                        index=index,
                        row=row,
                        side=side,
                        column=column,
                        # This controls drawing only. It deliberately matches
                        # the JSON/export column: L0_5 is the sixth displayed
                        # key of row L0, rather than a separately named scan
                        # coordinate. The row geometry is handled by CSS.
                        visual_column=column,
                        label=position_id,
                        width=1.5 if column == 0 and row < 4 and side == "left" else 1.0,
                    )
                )
                index += 1
    return tuple(positions)


KEY_POSITIONS: tuple[KeyPosition, ...] = _make_positions()
POSITION_IDS: frozenset[str] = frozenset(position.id for position in KEY_POSITIONS)

if len(KEY_POSITIONS) != 76:  # pragma: no cover - construction invariant
    raise RuntimeError("ErgoDox physical model must contain exactly 76 positions")


def layout_payload() -> dict[str, object]:
    return {
        "keyboard": "slicemk_ergodox",
        "key_count": len(KEY_POSITIONS),
        "half_row_key_counts": list(HALF_ROW_KEY_COUNTS),
        "positions": [position.to_dict() for position in KEY_POSITIONS],
    }
