from __future__ import annotations

from collections import deque
from typing import Any

MIN_DATA_ROWS = 3
MIN_BLOCK_COLS = 2

HEADER_ROWS = 2
CUT_BAND_WIDTHS = [1, 2]
BRIDGE_CUT_THRESHOLD = 0.02
BRIDGE_CUT_MAX_CELLS = 5
LABEL_BRIDGE_MAX_FILL_RATIO = 0.60
LABEL_BRIDGE_MIN_TEXT_RATIO = 0.80
LABEL_BRIDGE_MAX_UNIQUE_VALUES = 16
SOFT_COL_THRESHOLD = 0.05
SOFT_ROW_THRESHOLD = 0.05
DENSE_COL_THRESHOLD = 0.30
DENSE_ROW_THRESHOLD = 0.30
MIN_GAP_COLS = 1
MIN_GAP_ROWS = 1
MIN_DENSE_COLS = 2
MIN_DENSE_ROWS = 2
MIN_NONEMPTY_CELLS = 20
MAX_ITER = 5
MAX_MERGE_GAP_ROWS = 5


def _is_non_empty_cell(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _is_numeric_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False

    cleaned = value.strip()
    if not cleaned:
        return False

    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _pad_rows(rows: list[list[Any]]) -> list[list[Any]]:
    max_cols = max((len(row) for row in rows), default=0)
    return [row + [None] * (max_cols - len(row)) for row in rows]


def _boxes_overlap(a: dict[str, int], b: dict[str, int]) -> bool:
    row_overlaps = not (a["row_end"] < b["row_start"] or b["row_end"] < a["row_start"])
    col_overlaps = not (a["col_end"] < b["col_start"] or b["col_end"] < a["col_start"])
    return row_overlaps and col_overlaps


def _collect_non_empty_cells(
    grid: list[list[Any]],
    *,
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()

    for row_idx in range(row_start, row_end + 1):
        row = grid[row_idx]
        for col_idx in range(col_start, col_end + 1):
            if _is_non_empty_cell(row[col_idx]):
                cells.add((row_idx, col_idx))

    return cells


def _component_boxes_from_cells(cells: set[tuple[int, int]]) -> list[dict[str, int]]:
    boxes: list[dict[str, int]] = []
    visited: set[tuple[int, int]] = set()

    for seed in sorted(cells):
        if seed in visited:
            continue

        queue: deque[tuple[int, int]] = deque([seed])
        visited.add(seed)

        min_row = max_row = seed[0]
        min_col = max_col = seed[1]

        while queue:
            row_idx, col_idx = queue.popleft()
            min_row = min(min_row, row_idx)
            max_row = max(max_row, row_idx)
            min_col = min(min_col, col_idx)
            max_col = max(max_col, col_idx)

            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (row_idx + dr, col_idx + dc)
                if neighbor in visited:
                    continue
                if neighbor not in cells:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)

        boxes.append(
            {
                "row_start": min_row,
                "row_end": max_row,
                "col_start": min_col,
                "col_end": max_col,
            }
        )

    return boxes


def _component_boxes(grid: list[list[Any]]) -> list[dict[str, int]]:
    if not grid or not grid[0]:
        return []

    cells = _collect_non_empty_cells(
        grid,
        row_start=0,
        row_end=len(grid) - 1,
        col_start=0,
        col_end=len(grid[0]) - 1,
    )
    return _component_boxes_from_cells(cells)


def _box_non_empty_cell_count(grid: list[list[Any]], box: dict[str, int]) -> int:
    count = 0
    for row_idx in range(box["row_start"], box["row_end"] + 1):
        for col_idx in range(box["col_start"], box["col_end"] + 1):
            if _is_non_empty_cell(grid[row_idx][col_idx]):
                count += 1
    return count


def _is_meaningful_box(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    min_data_rows: int,
    min_block_cols: int,
    min_non_empty_cells: int,
) -> bool:
    row_count = box["row_end"] - box["row_start"] + 1
    col_count = box["col_end"] - box["col_start"] + 1
    data_rows = max(row_count - 1, 0)
    non_empty_count = _box_non_empty_cell_count(grid, box)

    if data_rows < min_data_rows:
        return False
    if col_count < min_block_cols:
        return False
    if non_empty_count < min_non_empty_cells:
        return False

    return True


def _unique_boxes(boxes: list[dict[str, int]]) -> list[dict[str, int]]:
    seen: set[tuple[int, int, int, int]] = set()
    unique: list[dict[str, int]] = []

    for box in boxes:
        key = (box["row_start"], box["row_end"], box["col_start"], box["col_end"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(box)

    return unique


def _contiguous_runs(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []

    sorted_indices = sorted(set(indices))
    runs: list[tuple[int, int]] = []
    run_start = sorted_indices[0]
    run_end = sorted_indices[0]

    for value in sorted_indices[1:]:
        if value == run_end + 1:
            run_end = value
            continue

        runs.append((run_start, run_end))
        run_start = value
        run_end = value

    runs.append((run_start, run_end))
    return runs


def _segments_from_runs(start: int, end: int, runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if start > end:
        return []

    if not runs:
        return [(start, end)]

    segments: list[tuple[int, int]] = []
    cursor = start

    for run_start, run_end in sorted(runs):
        if cursor <= run_start - 1:
            segments.append((cursor, run_start - 1))
        cursor = run_end + 1

    if cursor <= end:
        segments.append((cursor, end))

    return segments


def _data_row_bounds(box: dict[str, int]) -> tuple[int, int] | None:
    row_start = box["row_start"] + HEADER_ROWS
    row_end = box["row_end"]
    if row_start > row_end:
        return None
    return row_start, row_end


def _column_counts_on_data_rows(
    grid: list[list[Any]],
    box: dict[str, int],
) -> tuple[dict[int, int], int]:
    bounds = _data_row_bounds(box)
    if bounds is None:
        return {}, 0

    data_row_start, data_row_end = bounds
    total_data_rows = data_row_end - data_row_start + 1
    counts: dict[int, int] = {}

    for col_idx in range(box["col_start"], box["col_end"] + 1):
        non_empty_count = 0
        for row_idx in range(data_row_start, data_row_end + 1):
            if _is_non_empty_cell(grid[row_idx][col_idx]):
                non_empty_count += 1
        counts[col_idx] = non_empty_count

    return counts, total_data_rows


def _row_counts_on_data_rows(
    grid: list[list[Any]],
    box: dict[str, int],
) -> tuple[dict[int, int], int]:
    bounds = _data_row_bounds(box)
    if bounds is None:
        return {}, 0

    data_row_start, data_row_end = bounds
    total_data_rows = data_row_end - data_row_start + 1
    counts: dict[int, int] = {}

    for row_idx in range(data_row_start, data_row_end + 1):
        non_empty_count = 0
        for col_idx in range(box["col_start"], box["col_end"] + 1):
            if _is_non_empty_cell(grid[row_idx][col_idx]):
                non_empty_count += 1
        counts[row_idx] = non_empty_count

    return counts, total_data_rows


def _sum_counts(counts: dict[int, int], start: int, end: int) -> int:
    if start > end:
        return 0
    return sum(counts.get(index, 0) for index in range(start, end + 1))


def _count_dense_from_counts(
    counts: dict[int, int],
    *,
    total: int,
    start: int,
    end: int,
    dense_threshold: float,
) -> int:
    if start > end or total <= 0:
        return 0

    dense = 0
    for index in range(start, end + 1):
        density = counts.get(index, 0) / total
        if density >= dense_threshold:
            dense += 1

    return dense


def _is_label_like_vertical_cut_band(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    cut_start: int,
    cut_end: int,
) -> bool:
    bounds = _data_row_bounds(box)
    if bounds is None:
        return False

    data_row_start, data_row_end = bounds
    width = cut_end - cut_start + 1
    if width <= 0:
        return False

    non_empty_values: list[Any] = []
    text_like_tokens: list[str] = []

    for row_idx in range(data_row_start, data_row_end + 1):
        row = grid[row_idx]
        for col_idx in range(cut_start, cut_end + 1):
            value = row[col_idx]
            if not _is_non_empty_cell(value):
                continue
            non_empty_values.append(value)

            if isinstance(value, str):
                token = value.strip()
                if token and not _is_numeric_like(token):
                    text_like_tokens.append(token)

    if not non_empty_values:
        return False

    total_slots = (data_row_end - data_row_start + 1) * width
    fill_ratio = len(non_empty_values) / total_slots
    if fill_ratio > LABEL_BRIDGE_MAX_FILL_RATIO:
        return False

    text_ratio = len(text_like_tokens) / len(non_empty_values)
    if text_ratio < LABEL_BRIDGE_MIN_TEXT_RATIO:
        return False

    unique_text_values = len(set(text_like_tokens))
    if unique_text_values > LABEL_BRIDGE_MAX_UNIQUE_VALUES:
        return False

    return True


def _best_vertical_bridge_split(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    min_non_empty_cells: int,
) -> list[dict[str, int]] | None:
    col_counts, total_data_rows = _column_counts_on_data_rows(grid, box)
    if total_data_rows <= 0:
        return None

    best_key: tuple[float, float, int, int] | None = None
    best_split: list[dict[str, int]] | None = None

    for width in CUT_BAND_WIDTHS:
        if width <= 0:
            continue

        cut_start_min = box["col_start"] + 1
        cut_start_max = box["col_end"] - width

        for cut_start in range(cut_start_min, cut_start_max + 1):
            cut_end = cut_start + width - 1

            left_start = box["col_start"]
            left_end = cut_start - 1
            right_start = cut_end + 1
            right_end = box["col_end"]

            if left_start > left_end or right_start > right_end:
                continue

            left_dense = _count_dense_from_counts(
                col_counts,
                total=total_data_rows,
                start=left_start,
                end=left_end,
                dense_threshold=DENSE_COL_THRESHOLD,
            )
            right_dense = _count_dense_from_counts(
                col_counts,
                total=total_data_rows,
                start=right_start,
                end=right_end,
                dense_threshold=DENSE_COL_THRESHOLD,
            )

            if left_dense < MIN_DENSE_COLS or right_dense < MIN_DENSE_COLS:
                continue

            left_non_empty = _sum_counts(col_counts, left_start, left_end)
            right_non_empty = _sum_counts(col_counts, right_start, right_end)

            if left_non_empty < min_non_empty_cells or right_non_empty < min_non_empty_cells:
                continue

            cut_cost = _sum_counts(col_counts, cut_start, cut_end)
            normalized_cut_cost = cut_cost / (total_data_rows * width)

            is_sparse_cut = (
                normalized_cut_cost <= BRIDGE_CUT_THRESHOLD or cut_cost <= BRIDGE_CUT_MAX_CELLS
            )
            is_label_bridge_cut = _is_label_like_vertical_cut_band(
                grid,
                box,
                cut_start=cut_start,
                cut_end=cut_end,
            )

            if not (is_sparse_cut or is_label_bridge_cut):
                continue

            key = (float(cut_cost), normalized_cut_cost, width, cut_start)
            if best_key is None or key < best_key:
                best_key = key
                best_split = [
                    {
                        "row_start": box["row_start"],
                        "row_end": box["row_end"],
                        "col_start": left_start,
                        "col_end": left_end,
                    },
                    {
                        "row_start": box["row_start"],
                        "row_end": box["row_end"],
                        "col_start": right_start,
                        "col_end": right_end,
                    },
                ]

    return best_split


def _best_horizontal_bridge_split(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    min_non_empty_cells: int,
) -> list[dict[str, int]] | None:
    row_counts, total_data_rows = _row_counts_on_data_rows(grid, box)
    data_bounds = _data_row_bounds(box)

    if total_data_rows <= 0 or data_bounds is None:
        return None

    data_row_start, data_row_end = data_bounds
    total_cols = box["col_end"] - box["col_start"] + 1

    best_key: tuple[float, float, int, int] | None = None
    best_split: list[dict[str, int]] | None = None

    for width in CUT_BAND_WIDTHS:
        if width <= 0:
            continue

        cut_start_min = data_row_start + 1
        cut_start_max = data_row_end - width

        for cut_start in range(cut_start_min, cut_start_max + 1):
            cut_end = cut_start + width - 1

            top_start = box["row_start"]
            top_end = cut_start - 1
            bottom_start = cut_end + 1
            bottom_end = box["row_end"]

            if top_start > top_end or bottom_start > bottom_end:
                continue

            # Guard against splitting ordinary sparse rows: horizontal bridge cuts must
            # be near-empty bands relative to table width.
            if any(
                (row_counts.get(row_idx, 0) / total_cols) > SOFT_ROW_THRESHOLD
                for row_idx in range(cut_start, cut_end + 1)
            ):
                continue

            top_dense = _count_dense_from_counts(
                row_counts,
                total=total_cols,
                start=data_row_start,
                end=cut_start - 1,
                dense_threshold=DENSE_ROW_THRESHOLD,
            )
            bottom_dense = _count_dense_from_counts(
                row_counts,
                total=total_cols,
                start=cut_end + 1,
                end=data_row_end,
                dense_threshold=DENSE_ROW_THRESHOLD,
            )

            if top_dense < MIN_DENSE_ROWS or bottom_dense < MIN_DENSE_ROWS:
                continue

            top_non_empty = _sum_counts(row_counts, data_row_start, cut_start - 1)
            bottom_non_empty = _sum_counts(row_counts, cut_end + 1, data_row_end)

            if top_non_empty < min_non_empty_cells or bottom_non_empty < min_non_empty_cells:
                continue

            cut_cost = _sum_counts(row_counts, cut_start, cut_end)
            normalized_cut_cost = cut_cost / (total_cols * width)

            if not (
                normalized_cut_cost <= BRIDGE_CUT_THRESHOLD or cut_cost <= BRIDGE_CUT_MAX_CELLS
            ):
                continue

            key = (float(cut_cost), normalized_cut_cost, width, cut_start)
            if best_key is None or key < best_key:
                best_key = key
                best_split = [
                    {
                        "row_start": top_start,
                        "row_end": top_end,
                        "col_start": box["col_start"],
                        "col_end": box["col_end"],
                    },
                    {
                        "row_start": bottom_start,
                        "row_end": bottom_end,
                        "col_start": box["col_start"],
                        "col_end": box["col_end"],
                    },
                ]

    return best_split


def _column_non_empty_ratios_excluding_header(
    grid: list[list[Any]],
    box: dict[str, int],
) -> dict[int, float]:
    counts, total_data_rows = _column_counts_on_data_rows(grid, box)
    if total_data_rows <= 0:
        return {}

    return {
        col_idx: count / total_data_rows
        for col_idx, count in counts.items()
    }


def _row_non_empty_ratios_on_data_rows(
    grid: list[list[Any]],
    box: dict[str, int],
) -> dict[int, float]:
    counts, _ = _row_counts_on_data_rows(grid, box)
    col_count = box["col_end"] - box["col_start"] + 1
    if col_count <= 0:
        return {}

    return {
        row_idx: count / col_count
        for row_idx, count in counts.items()
    }


def _count_dense(values: dict[int, float], start: int, end: int, dense_threshold: float) -> int:
    if start > end:
        return 0
    return sum(1 for idx in range(start, end + 1) if values.get(idx, 0.0) >= dense_threshold)


def _valid_separator_runs(
    values: dict[int, float],
    *,
    start: int,
    end: int,
    soft_threshold: float,
    dense_threshold: float,
    min_gap: int,
    min_dense: int,
) -> list[tuple[int, int]]:
    separator_indices = [
        idx
        for idx in range(start, end + 1)
        if values.get(idx, 1.0) <= soft_threshold
    ]

    runs = _contiguous_runs(separator_indices)
    valid: list[tuple[int, int]] = []

    for run_start, run_end in runs:
        run_len = run_end - run_start + 1
        if run_len < min_gap:
            continue

        left_dense = _count_dense(values, start, run_start - 1, dense_threshold)
        right_dense = _count_dense(values, run_end + 1, end, dense_threshold)

        if left_dense < min_dense or right_dense < min_dense:
            continue

        valid.append((run_start, run_end))

    return valid


def _soft_split_rectangles(
    grid: list[list[Any]],
    box: dict[str, int],
) -> list[dict[str, int]] | None:
    col_values = _column_non_empty_ratios_excluding_header(grid, box)

    row_values = _row_non_empty_ratios_on_data_rows(grid, box)
    data_bounds = _data_row_bounds(box)

    col_runs: list[tuple[int, int]] = []
    if col_values:
        col_runs = _valid_separator_runs(
            col_values,
            start=box["col_start"],
            end=box["col_end"],
            soft_threshold=SOFT_COL_THRESHOLD,
            dense_threshold=DENSE_COL_THRESHOLD,
            min_gap=MIN_GAP_COLS,
            min_dense=MIN_DENSE_COLS,
        )

    row_runs: list[tuple[int, int]] = []
    if row_values and data_bounds is not None:
        data_row_start, data_row_end = data_bounds
        row_runs = _valid_separator_runs(
            row_values,
            start=data_row_start,
            end=data_row_end,
            soft_threshold=SOFT_ROW_THRESHOLD,
            dense_threshold=DENSE_ROW_THRESHOLD,
            min_gap=MIN_GAP_ROWS,
            min_dense=MIN_DENSE_ROWS,
        )

    if not col_runs and not row_runs:
        return None

    row_segments = _segments_from_runs(box["row_start"], box["row_end"], row_runs)
    col_segments = _segments_from_runs(box["col_start"], box["col_end"], col_runs)

    rectangles: list[dict[str, int]] = []
    for row_start, row_end in row_segments:
        for col_start, col_end in col_segments:
            rectangles.append(
                {
                    "row_start": row_start,
                    "row_end": row_end,
                    "col_start": col_start,
                    "col_end": col_end,
                }
            )

    return rectangles


def _rectangles_to_meaningful_boxes(
    grid: list[list[Any]],
    rectangles: list[dict[str, int]],
    *,
    min_data_rows: int,
    min_block_cols: int,
    min_non_empty_cells: int,
) -> list[dict[str, int]]:
    candidate_boxes: list[dict[str, int]] = []

    for rectangle in rectangles:
        local_cells = _collect_non_empty_cells(
            grid,
            row_start=rectangle["row_start"],
            row_end=rectangle["row_end"],
            col_start=rectangle["col_start"],
            col_end=rectangle["col_end"],
        )
        if not local_cells:
            continue

        local_components = _component_boxes_from_cells(local_cells)
        for candidate in local_components:
            if _is_meaningful_box(
                grid,
                candidate,
                min_data_rows=min_data_rows,
                min_block_cols=min_block_cols,
                min_non_empty_cells=min_non_empty_cells,
            ):
                candidate_boxes.append(candidate)

    return sorted(
        _unique_boxes(candidate_boxes),
        key=lambda item: (item["row_start"], item["col_start"]),
    )


def _split_box_once(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    min_data_rows: int,
    min_block_cols: int,
    min_non_empty_cells: int,
) -> list[dict[str, int]]:
    vertical_bridge = _best_vertical_bridge_split(
        grid,
        box,
        min_non_empty_cells=min_non_empty_cells,
    )
    if vertical_bridge:
        bridge_boxes = _rectangles_to_meaningful_boxes(
            grid,
            vertical_bridge,
            min_data_rows=min_data_rows,
            min_block_cols=min_block_cols,
            min_non_empty_cells=min_non_empty_cells,
        )
        if bridge_boxes:
            return bridge_boxes

    horizontal_bridge = _best_horizontal_bridge_split(
        grid,
        box,
        min_non_empty_cells=min_non_empty_cells,
    )
    if horizontal_bridge:
        bridge_boxes = _rectangles_to_meaningful_boxes(
            grid,
            horizontal_bridge,
            min_data_rows=min_data_rows,
            min_block_cols=min_block_cols,
            min_non_empty_cells=min_non_empty_cells,
        )
        if bridge_boxes:
            return bridge_boxes

    soft_rectangles = _soft_split_rectangles(grid, box)
    if soft_rectangles:
        soft_boxes = _rectangles_to_meaningful_boxes(
            grid,
            soft_rectangles,
            min_data_rows=min_data_rows,
            min_block_cols=min_block_cols,
            min_non_empty_cells=min_non_empty_cells,
        )
        if soft_boxes:
            return soft_boxes

    return [box]


def _refine_box_iteratively(
    grid: list[list[Any]],
    box: dict[str, int],
    *,
    min_data_rows: int,
    min_block_cols: int,
    min_non_empty_cells: int,
) -> list[dict[str, int]]:
    current = [box]

    for _ in range(MAX_ITER):
        next_boxes: list[dict[str, int]] = []
        changed = False

        for candidate in current:
            pieces = _split_box_once(
                grid,
                candidate,
                min_data_rows=min_data_rows,
                min_block_cols=min_block_cols,
                min_non_empty_cells=min_non_empty_cells,
            )
            next_boxes.extend(pieces)

            if len(pieces) != 1 or pieces[0] != candidate:
                changed = True

        next_boxes = _unique_boxes(next_boxes)
        if not changed:
            return sorted(next_boxes, key=lambda item: (item["row_start"], item["col_start"]))

        current = next_boxes

    return sorted(_unique_boxes(current), key=lambda item: (item["row_start"], item["col_start"]))


def _merge_overlapping_boxes(boxes: list[dict[str, int]]) -> list[dict[str, int]]:
    merged = list(boxes)

    changed = True
    while changed:
        changed = False
        next_boxes: list[dict[str, int]] = []
        consumed = [False] * len(merged)

        for i in range(len(merged)):
            if consumed[i]:
                continue

            current = dict(merged[i])
            consumed[i] = True

            for j in range(i + 1, len(merged)):
                if consumed[j]:
                    continue

                other = merged[j]
                if not _boxes_overlap(current, other):
                    continue

                current["row_start"] = min(current["row_start"], other["row_start"])
                current["row_end"] = max(current["row_end"], other["row_end"])
                current["col_start"] = min(current["col_start"], other["col_start"])
                current["col_end"] = max(current["col_end"], other["col_end"])
                consumed[j] = True
                changed = True

            next_boxes.append(current)

        merged = _unique_boxes(next_boxes)

    return merged


def _gap_rows_are_empty(
    grid: list[list[Any]],
    row_from: int,
    row_to: int,
    col_start: int,
    col_end: int,
) -> bool:
    for ri in range(row_from, min(row_to + 1, len(grid))):
        row = grid[ri]
        for ci in range(col_start, min(col_end + 1, len(row))):
            if _is_non_empty_cell(row[ci]):
                return False
    return True


def _merge_same_column_span_boxes(
    grid: list[list[Any]],
    boxes: list[dict[str, int]],
    *,
    merge_vertical_blocks: bool = False,
) -> list[dict[str, int]]:
    """Merge boxes with the same column span when separated only by empty rows.

    Handles tables where row-groups (varieties, treatment levels) are separated
    by single blank rows in the source sheet.  Stitching them back into one box
    lets header/data extraction work correctly on the full table.
    By default, an empty row inside the same column span is treated as a hard
    block separator. Legacy vertical stitching can be restored explicitly with
    `merge_vertical_blocks=True`.
    """
    if len(boxes) <= 1:
        return boxes
    if not merge_vertical_blocks:
        return sorted(boxes, key=lambda b: (b["row_start"], b["col_start"]))

    by_cols: dict[tuple[int, int], list[dict[str, int]]] = {}
    for box in boxes:
        key = (box["col_start"], box["col_end"])
        by_cols.setdefault(key, []).append(box)

    result: list[dict[str, int]] = []
    for (col_start, col_end), group in by_cols.items():
        group_sorted = sorted(group, key=lambda b: b["row_start"])
        cur_start = group_sorted[0]["row_start"]
        cur_end = group_sorted[0]["row_end"]

        for next_box in group_sorted[1:]:
            gap_start = cur_end + 1
            gap_end = next_box["row_start"] - 1
            gap_size = gap_end - gap_start + 1

            if (
                0 <= gap_size <= MAX_MERGE_GAP_ROWS
                and _gap_rows_are_empty(grid, gap_start, gap_end, col_start, col_end)
            ):
                cur_end = next_box["row_end"]
            else:
                result.append(
                    {
                        "row_start": cur_start,
                        "row_end": cur_end,
                        "col_start": col_start,
                        "col_end": col_end,
                    }
                )
                cur_start = next_box["row_start"]
                cur_end = next_box["row_end"]

        result.append(
            {
                "row_start": cur_start,
                "row_end": cur_end,
                "col_start": col_start,
                "col_end": col_end,
            }
        )

    return sorted(result, key=lambda b: (b["row_start"], b["col_start"]))


def _extract_cells(grid: list[list[Any]], box: dict[str, int]) -> list[list[Any]]:
    cells: list[list[Any]] = []
    for row_idx in range(box["row_start"], box["row_end"] + 1):
        row = grid[row_idx]
        cells.append(list(row[box["col_start"] : box["col_end"] + 1]))
    return cells


def detect_blocks_with_positions(
    rows: list[list[Any]],
    *,
    min_data_rows: int = MIN_DATA_ROWS,
    min_block_cols: int = MIN_BLOCK_COLS,
    min_non_empty_cells: int = MIN_NONEMPTY_CELLS,
    merge_vertical_blocks: bool = False,
) -> list[dict[str, Any]]:
    """Detect table blocks via BFS components with bridge-aware deterministic split refinement.

    A sparse middle label (for example a few cells like "A trágyaszint"/"N0") can connect two
    otherwise separate side-by-side tables into one connected component. To handle this, each
    component box is iteratively refined by selecting the lowest-cost vertical/horizontal cut band
    over the data region (rows after `HEADER_ROWS`) and splitting when both sides are dense but the
    cut band has very few non-empty cells. Soft separators are then applied, local connected
    components are re-checked, and only overlapping boxes are merged. Vertical stitching across
    empty separator rows is opt-in via `merge_vertical_blocks=True`.
    """
    grid = _pad_rows(rows)
    if not grid or not grid[0]:
        return []

    component_boxes = _component_boxes(grid)

    refined_boxes: list[dict[str, int]] = []
    for box in component_boxes:
        refined_boxes.extend(
            _refine_box_iteratively(
                grid,
                box,
                min_data_rows=min_data_rows,
                min_block_cols=min_block_cols,
                min_non_empty_cells=min_non_empty_cells,
            )
        )

    filtered = [
        box
        for box in _unique_boxes(refined_boxes)
        if _is_meaningful_box(
            grid,
            box,
            min_data_rows=min_data_rows,
            min_block_cols=min_block_cols,
            min_non_empty_cells=min_non_empty_cells,
        )
    ]

    same_col_merged = _merge_same_column_span_boxes(
        grid,
        filtered,
        merge_vertical_blocks=merge_vertical_blocks,
    )

    merged = _merge_overlapping_boxes(same_col_merged)
    merged.sort(key=lambda box: (box["row_start"], box["col_start"]))

    blocks: list[dict[str, Any]] = []
    for box in merged:
        cells = _extract_cells(grid, box)
        blocks.append(
            {
                "row_start": box["row_start"] + 1,
                "row_end": box["row_end"] + 1,
                "col_start": box["col_start"] + 1,
                "col_end": box["col_end"] + 1,
                "row_count": box["row_end"] - box["row_start"] + 1,
                "col_count": box["col_end"] - box["col_start"] + 1,
                "rows": cells,
            }
        )

    return blocks


def detect_blocks(
    rows: list[list[Any]],
    *,
    merge_vertical_blocks: bool = False,
) -> list[list[list[Any]]]:
    return [
        block["rows"]
        for block in detect_blocks_with_positions(
            rows,
            merge_vertical_blocks=merge_vertical_blocks,
        )
    ]
