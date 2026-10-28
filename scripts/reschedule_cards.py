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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fsrs import Card, Scheduler

from core import util
from core.config import load_review_config
from core.entry import IndexEntry
from core.index import Index

SAMPLE_LIMIT = 10


@dataclass(frozen=True)
class RescheduleChange:
    card_id: int
    note_path: str
    old_due: datetime
    new_due: datetime
    old_stability: float | None
    new_stability: float | None


@dataclass(frozen=True)
class RescheduleReport:
    scanned: int
    selected: int
    rescheduled: int
    changes: list[RescheduleChange]


def reschedule_entries(
    entries: list[IndexEntry], scheduler: Scheduler, since: datetime | None = None, dry_run: bool = False
) -> RescheduleReport:
    """Replay each card's review history through ``scheduler`` and rewrite its derived state.

    ``since`` limits the work to cards with at least one review on or after that instant.
    Review logs are treated as immutable facts; only stability, difficulty, state, and due change.
    """
    selected = 0
    changes: list[RescheduleChange] = []

    for entry in entries:
        metadata = entry.read_metadata()
        logs = metadata.review_logs
        if not logs:
            continue
        if since is not None and not any(log.review_datetime >= since for log in logs):
            continue
        selected += 1

        card = Card(card_id=entry.card_id)
        for log in sorted(logs, key=lambda item: item.review_datetime):
            card, _ = scheduler.review_card(
                card, log.rating, review_datetime=log.review_datetime, review_duration=log.review_duration
            )

        changes.append(
            RescheduleChange(
                card_id=entry.card_id,
                note_path=entry.note_path,
                old_due=entry.due,
                new_due=card.due,
                old_stability=metadata.scheduler_card.stability,
                new_stability=card.stability,
            )
        )
        metadata.scheduler_card = card
        entry.due = card.due
        if not dry_run:
            entry.write()

    return RescheduleReport(scanned=len(entries), selected=selected, rescheduled=len(changes), changes=changes)


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
