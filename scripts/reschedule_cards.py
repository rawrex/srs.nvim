#!/usr/bin/env python3
"""Recompute card scheduling from review history with the current scheduler config.

This is intended for repairing cards whose state was produced by bad scheduler
parameters. Every review log is replayed from scratch through the scheduler
configured in ``.srs/config.json``; review logs themselves are left untouched.

Usage:
    python scripts/reschedule_cards.py [repo] [--since YYYY-MM-DD] [--dry-run]

``--since`` limits the reschedule to cards with at least one review on or after
that date. Without it, every card with review history is rescheduled.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import util
from core.config import load_review_config
from core.index import Index
from core.reschedule import reschedule_entries

SAMPLE_LIMIT = 10


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recompute card schedules from their review history.")
    parser.add_argument("repo", nargs="?", default=".", help="Repository root (default: current directory)")
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD", help="Only reschedule cards reviewed on or after this UTC date"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the changes without writing anything")
    return parser


def _parse_since(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid date: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _format_stability(value: float | None) -> str:
    return "none" if value is None else f"{value:.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        since = _parse_since(args.since)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))

    util.init_runtime_context(os.path.abspath(args.repo))
    if not util._RUNTIME_CONTEXT.repo_root_path:
        print("Not inside a git repository.")
        return 1

    if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
        print("Missing index")
        return 1

    scheduler = load_review_config().build_scheduler()
    index = Index()
    try:
        report = reschedule_entries(index.get_entries(), scheduler, since=since, dry_run=args.dry_run)
    finally:
        if not args.dry_run:
            index.flush()

    prefix = "Dry run: " if args.dry_run else ""
    print(f"{prefix}scanned {report.scanned} card(s), selected {report.selected}, rescheduled {report.rescheduled}.")
    for change in report.changes[:SAMPLE_LIMIT]:
        print(
            f"  {change.card_id} {change.note_path}: "
            f"due {change.old_due.date()} -> {change.new_due.date()}, "
            f"stability {_format_stability(change.old_stability)} -> {_format_stability(change.new_stability)}"
        )
    if len(report.changes) > SAMPLE_LIMIT:
        print(f"  ... and {len(report.changes) - SAMPLE_LIMIT} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
