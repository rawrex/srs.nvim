#!/usr/bin/env python3
# ruff: noqa: E402
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import util
from core.index.index import Index
from core.optimization import SKIPPED_INSUFFICIENT_DATA, SKIPPED_NO_LOGS, OptimizationReport, run_optimization

OPTIMIZER_INSTALL_HINT = 'Optimizer dependencies are missing. Install them with: pip install "fsrs[optimizer]"'
INSUFFICIENT_DATA_MESSAGE = (
    "Not enough review history to optimize (fsrs needs at least 512 eligible reviews). Parameters unchanged."
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize FSRS scheduler parameters from review history.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show optimizer progress.")
    parser.add_argument("--dry-run", action="store_true", help="Print optimized parameters without writing config.")
    return parser


def _print_report(report: OptimizationReport, dry_run: bool) -> None:
    parameters_text = ", ".join(f"{value:.4f}" for value in report.parameters)
    if report.skipped_reason == SKIPPED_NO_LOGS:
        print("No review logs found. Nothing to optimize.")
        return
    if report.skipped_reason == SKIPPED_INSUFFICIENT_DATA:
        print(INSUFFICIENT_DATA_MESSAGE)
        return

    summary = f"Optimized {report.card_count} card(s) from {report.review_log_count} review log(s)."
    print(summary)
    if dry_run:
        print(f"Dry run — optimized parameters not saved: {parameters_text}")
        return
    print(f"Saved scheduler parameters to {util._RUNTIME_CONTEXT.config_path}")
    print(parameters_text)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    util.init_runtime_context(os.getcwd())
    repo_root = util._RUNTIME_CONTEXT.repo_root_path
    if not repo_root:
        print("Not inside a git repository.")
        return 1

    if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
        print("Missing index")
        return 1

    index = Index()
    entries = index.load_entries()

    try:
        report = run_optimization(entries, verbose=args.verbose, dry_run=args.dry_run)
    except ImportError:
        print(OPTIMIZER_INSTALL_HINT)
        return 1

    _print_report(report, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
