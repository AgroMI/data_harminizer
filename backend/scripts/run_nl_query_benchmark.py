from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.benchmark_runner import (
    build_markdown_summary,
    build_text_summary,
    run_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the reproducible NL-query benchmark suite.")
    parser.add_argument("--dataset", type=Path, default=None, help="Optional path to a benchmark dataset JSON file.")
    parser.add_argument("--seed-rows", type=Path, default=None, help="Optional path to a benchmark seed-row JSON file.")
    parser.add_argument("--json-output", type=Path, default=None, help="Optional output path for the JSON report.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional output path for the Markdown summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_benchmark(dataset_path=args.dataset, seed_rows_path=args.seed_rows)

    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    markdown_summary = build_markdown_summary(report)
    if args.markdown_output is not None:
        args.markdown_output.write_text(markdown_summary + "\n", encoding="utf-8")

    print(build_text_summary(report))


if __name__ == "__main__":
    main()
