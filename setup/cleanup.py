#!/usr/bin/env python3
import os
import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

common = import_module("setup.common")
build_parser_registry = import_module("card.parsers").build_parser_registry
load_review_config = import_module("core.config").load_review_config
Index = import_module("core.index.index").Index
find_repeat_tracked_paths = import_module(
    "core.index.tracking"
).find_repeat_tracked_paths


def _prompt_yes_no(message: str) -> bool:
    while True:
        answer = input(f"{message} [y/N]: ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        print("Please answer with 'y' or 'n'.")


def _print_path_list(title: str, paths: list[str]) -> None:
    print(title)
    for path in paths:
        print(f"  - {path}")


def main() -> int:
    context = common.resolve_repo_context()
    if context is None:
        print("Not inside a git repository.")
        return 1

    if not os.path.exists(context.index_path):
        print("Missing .srs/index.txt. Run setup/install.py first.")
        return 1

    config = load_review_config(context.repo_root)
    parser_registry = build_parser_registry(config)
    index = Index(context.index_path, parser_registry)

    tracked_paths = set(find_repeat_tracked_paths(context.repo_root))
    report = index.build_cleanup_report(tracked_paths)

    has_missing = bool(report.missing_rows_by_path)
    has_invalid = bool(report.invalid_rows)
    has_orphans = bool(report.orphan_card_ids)
    if not (has_missing or has_invalid or has_orphans):
        print("Index cleanup: nothing to do.")
        return 0

    if has_missing:
        print(
            "Tracked notes missing index coverage:",
            len(report.missing_rows_by_path),
            "path(s)",
        )
        _print_path_list("Missing coverage paths:", sorted(report.missing_rows_by_path))

    if has_invalid:
        print("Invalid index rows found:", len(report.invalid_rows))
        for row in report.invalid_rows:
            print(
                "  -",
                row.path,
                f"[{row.parser_id} {row.start_line}-{row.end_line}]",
                f"id={row.note_id}",
                f"reason={row.reason}",
            )

    if has_orphans:
        print("Orphan card metadata files:", len(report.orphan_card_ids))
        for card_id in report.orphan_card_ids:
            print(f"  - /.srs/{card_id}.json")

    add_missing = has_missing and _prompt_yes_no(
        "Add missing cards for tracked notes automatically?"
    )
    remove_invalid = has_invalid and _prompt_yes_no(
        "Remove invalid index rows and card files?"
    )
    remove_orphans = has_orphans and _prompt_yes_no("Remove orphan .srs/*.json files?")

    result = index.apply_cleanup_report(
        report,
        add_missing=add_missing,
        remove_invalid=remove_invalid,
        remove_orphan_cards=remove_orphans,
    )

    print("Cleanup applied:")
    print("  Added rows:", result.added_rows)
    print("  Removed invalid rows:", result.removed_invalid_rows)
    print("  Removed orphan cards:", result.removed_orphan_cards)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
