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


def _build_stacked_numeric_rows() -> list[list[object]]:
    rows: list[list[object]] = [
        ["yield"] * 8,
        ["A", "B", "C", "D", "E", "F", "G", "H"],
    ]

    numeric_blocks = [
        [
            [5.55, 8.50, 8.05, 8.35, 8.05, 9.40, 8.25, 8.35],
            [5.80, 7.25, 8.90, 9.75, 8.35, 8.60, 7.85, 9.55],
            [7.65, 8.60, 8.90, 9.35, 10.10, 9.70, 8.85, 9.15],
            [6.45, 6.90, 9.45, 8.70, 8.10, 7.10, 8.20, 6.90],
            [6.36, 7.81, 8.83, 9.04, 8.65, 8.70, 8.29, 8.49],
        ],
        [
            [6.10, 8.95, 7.65, 8.95, 9.55, 9.95, 8.10, 8.60],
            [6.45, 9.05, 8.05, 9.25, 8.80, 9.50, 8.15, 9.35],
            [7.40, 8.30, 8.95, 9.80, 10.90, 10.80, 9.60, 9.45],
            [5.70, 7.00, 8.55, 8.20, 8.55, 8.65, 8.55, 7.60],
            [6.41, 8.33, 8.30, 9.05, 9.45, 9.73, 8.60, 8.75],
        ],
        [
            [4.06, 6.21, 5.88, 6.10, 5.88, 6.87, 6.03, 6.10],
            [4.24, 5.30, 6.51, 7.13, 6.10, 6.29, 5.74, 6.98],
            [5.59, 6.29, 6.51, 6.83, 7.38, 7.09, 6.47, 6.69],
            [4.71, 5.04, 6.91, 6.36, 5.92, 5.19, 5.99, 5.04],
            [4.65, 5.71, 6.45, 6.61, 6.32, 6.36, 6.06, 6.20],
        ],
    ]

    for block in numeric_blocks:
        rows.extend(block)
        rows.append([None] * 8)

    return rows


def test_detect_blocks_splits_side_by_side_tables_connected_by_label_column() -> None:
    blocks = detect_blocks_with_positions(_build_side_by_side_rows())

    assert len(blocks) == 2

    left_block, right_block = blocks
    assert (left_block["col_start"], left_block["col_end"]) == (1, 5)
    assert (right_block["col_start"], right_block["col_end"]) == (7, 10)


def test_detect_blocks_keeps_stacked_numeric_blocks_separate_by_default() -> None:
    blocks = detect_blocks_with_positions(_build_stacked_numeric_rows())

    assert len(blocks) == 3
    assert [(block["row_start"], block["row_end"]) for block in blocks] == [
        (1, 7),
        (9, 13),
        (15, 19),
    ]


def test_detect_blocks_can_restore_legacy_same_span_numeric_merge() -> None:
    blocks = detect_blocks_with_positions(
        _build_stacked_numeric_rows(),
        merge_vertical_blocks=True,
    )

    assert len(blocks) == 1
    assert (blocks[0]["row_start"], blocks[0]["row_end"]) == (1, 19)
