from __future__ import annotations

from etl.block_detector import detect_blocks_with_positions


def _build_side_by_side_rows() -> list[list[object]]:
    rows: list[list[object]] = [
        [None, None, "left_yield", None, None, None, None, "right_yield", None, None],
        [None, None, "I.", None, "II.", None, None, "I.", None, "II."],
        [None, "plot", "kg/parc", "viz%", "kg/parc", "label", "plot", "t/ha", "viz%", "t/ha"],
    ]

    labels = ("N0", "N40", "N80", "N120")
    for index in range(1, 33):
        label = labels[(index // 2) % len(labels)] if index % 2 == 1 else None
        rows.append(
            [
                label,
                index,
                5.0 + index * 0.1,
                12.0 + index * 0.05,
                6.0 + index * 0.1,
                label,
                index,
                4.0 + index * 0.1,
                11.0 + index * 0.04,
                5.0 + index * 0.1,
            ]
        )

    return rows


def test_detect_blocks_splits_side_by_side_tables_connected_by_label_column() -> None:
    blocks = detect_blocks_with_positions(_build_side_by_side_rows())

    assert len(blocks) == 2

    left_block, right_block = blocks
    assert (left_block["col_start"], left_block["col_end"]) == (1, 5)
    assert (right_block["col_start"], right_block["col_end"]) == (7, 10)
