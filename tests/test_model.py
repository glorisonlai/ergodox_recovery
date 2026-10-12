from __future__ import annotations

from ergodox_recovery.model import HALF_ROW_KEY_COUNTS, KEY_POSITIONS, POSITION_IDS, layout_payload


def test_ergodox_model_has_exactly_76_unique_contiguous_positions() -> None:
    assert len(KEY_POSITIONS) == 76
    assert len(POSITION_IDS) == 76
    assert [position.index for position in KEY_POSITIONS] == list(range(76))
    assert all(position.id in POSITION_IDS for position in KEY_POSITIONS)


def test_each_visual_row_has_matching_left_and_right_halves() -> None:
    assert sum(HALF_ROW_KEY_COUNTS) * 2 == 76
    for row, count in enumerate(HALF_ROW_KEY_COUNTS):
        left = [
            position
            for position in KEY_POSITIONS
            if position.row == row and position.side == "left"
        ]
        right = [
            position
            for position in KEY_POSITIONS
            if position.row == row and position.side == "right"
        ]
        assert len(left) == len(right) == count
        assert [position.column for position in left] == list(range(count))
        assert [position.column for position in right] == list(range(count))


def test_visual_layout_uses_json_column_order_without_changing_export_indexes() -> None:
    positions = {position.id: position for position in KEY_POSITIONS}

    assert positions["L0_0"].visual_column == 0
    assert positions["L0_5"].visual_column == 5
    assert positions["L0_6"].visual_column == 6
    assert positions["R3_0"].visual_column == 0
    assert positions["R3_6"].visual_column == 6
    assert positions["L5_0"].visual_column == 0
    assert positions["R7_0"].visual_column == 0

    # Canonical export positions remain the unmodified, contiguous SliceMK order.
    assert [position.index for position in KEY_POSITIONS] == list(range(76))


def test_layout_payload_is_complete_and_json_ready() -> None:
    payload = layout_payload()

    assert payload["keyboard"] == "slicemk_ergodox"
    assert payload["key_count"] == 76
    assert len(payload["positions"]) == 76
