#!/usr/bin/env python3
"""Explicitly scan notes and create cards.

This is an add-on, not part of the review flow:

    python scan.py [paths ...]

With no paths, the scanner uses the paths selected by ``.repeat`` markers when
present, otherwise the whole repository. Existing spans are left untouched, so
re-running the command is safe.
"""

import argparse
import os

from autoparse.scanner import build_scanner_registry
from autoparse.tracking import find_repeat_tracked_paths
from core import util
from core.config import load_review_config
from core.index import Index
from core.parsers import ParserRegistry
from core.util import GIT_RELATED_FILENAMES

SKIP_DIR_NAMES = {".git", ".srs", "__pycache__", ".venv", "venv", "node_modules"}


def collect_parsed_blocks(note_text: str, registry: ParserRegistry) -> list[tuple[str, int, int]]:
    selected: list[tuple[str, int, int]] = []
    claimed_ranges: list[tuple[int, int]] = []
    for scanner in registry.ordered():
        for line_start, line_end in scanner.interpret_text(note_text):
            if any(
                line_start <= claimed_end and line_end >= claimed_start for claimed_start, claimed_end in claimed_ranges
            ):
                continue
            selected.append((scanner.parser_id, line_start, line_end))
            claimed_ranges.append((line_start, line_end))
    return sorted(selected, key=lambda entry: (entry[1], entry[2], entry[0]))


def iter_note_paths(targets: list[str], repo_root: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(abs_path: str) -> None:
        path = util.repo_relative_path(repo_root, abs_path)
        if path not in seen:
            seen.add(path)
            paths.append(path)

    for target in targets:
        abs_target = target if os.path.isabs(target) else os.path.join(repo_root, target)
        if os.path.isfile(abs_target):
            add(abs_target)
            continue
        if not os.path.isdir(abs_target):
            continue
        for root, dirs, files in os.walk(abs_target):
            dirs[:] = sorted(name for name in dirs if name not in SKIP_DIR_NAMES and not name.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or name in GIT_RELATED_FILENAMES:
                    continue
                add(os.path.join(root, name))

    return paths


def read_note_text(repo_root: str, note_path: str) -> str | None:
    abs_path = os.path.join(repo_root, note_path.lstrip("/"))
    if not os.path.isfile(abs_path):
        return None
    try:
        with open(abs_path, "r", encoding="utf-8") as handle:
            return handle.read()
    except UnicodeDecodeError:
        return None


def scan_note(index: Index, registry: ParserRegistry, note_path: str, note_text: str) -> int:
    existing = {(entry.start_line, entry.end_line) for entry in index.entries_for_note(note_path)}
    added = 0
    for card_type, start_line, end_line in collect_parsed_blocks(note_text, registry):
        if (start_line, end_line) in existing:
            continue
        index.add_card(note_path, card_type, start_line, end_line)
        existing.add((start_line, end_line))
        added += 1
    return added


def _resolve_targets(paths: list[str]) -> list[str]:
    if paths:
        return paths
    marked = [path.lstrip("/") for path in find_repeat_tracked_paths()]
    return marked if marked else ["."]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan notes and create SRS cards automatically.")
    parser.add_argument("paths", nargs="*", help="Files or directories to scan (default: marked paths or repo root).")
    return parser


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

    config = load_review_config()
    registry = build_scanner_registry(config)
    index = Index()

    total = 0
    for note_path in iter_note_paths(_resolve_targets(args.paths), repo_root):
        if note_text := read_note_text(repo_root, note_path):
            if added := scan_note(index, registry, note_path, note_text):
                print(f"{note_path}: {added} card(s)")
                total += added

    print(f"Total: {total} card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
