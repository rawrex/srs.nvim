#!/usr/bin/env python3
"""Add the due timestamp to existing index rows.

Run this once after upgrading if `.srs/index.txt` rows still end after the
end-line column:

    python migrate_index_due.py [repo]
"""

import argparse
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fsrs import Card as SchedulerCard

from core import util
from core.model import IndexEntry

OLD_ENTRY_RE = re.compile(r"^'(\d+)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")


def migrate_line(raw_line: str, srs_path: str) -> str:
    if not (match := OLD_ENTRY_RE.match(raw_line.rstrip("\n"))):
        return raw_line

    card_id = int(match.group(1))
    with open(os.path.join(srs_path, f"{card_id}.json"), "r", encoding="utf-8") as handle:
        due = SchedulerCard.from_json(handle.read()).due

    return IndexEntry(
        metadata=None,
        card_id=card_id,
        note_path=match.group(2),
        card_type=match.group(3),
        start_line=int(match.group(4)),
        end_line=int(match.group(5)),
        due=due,
    ).format()


def main() -> int:
    parser = argparse.ArgumentParser(description="Add the due timestamp to .srs/index.txt rows.")
    parser.add_argument("repo", nargs="?", default=".", help="Repository root (default: current directory)")
    args = parser.parse_args()

    util.init_runtime_context(os.path.abspath(args.repo))
    if not util._RUNTIME_CONTEXT.repo_root_path:
        print("Not inside a git repository.")
        return 1

    index_path = util._RUNTIME_CONTEXT.index_path
    if not os.path.exists(index_path):
        print("Missing index")
        return 1

    with open(index_path, "r", encoding="utf-8") as handle:
        rows = [migrate_line(line, util._RUNTIME_CONTEXT.srs_path) for line in handle]

    util.write_text_atomic(index_path, "".join(rows))
    print(f"Migrated {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
