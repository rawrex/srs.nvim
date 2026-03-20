#!/usr/bin/env python3
import os
import shlex
import stat
import sys

import util
from setup.common import (
    HOOKS,
    INDEX_FILE_NAME,
    NOREPEAT_MARKER_NAME,
    REPEAT_MARKER_NAME,
    SRS_DIR_NAME,
    resolve_repo_context,
)
from srs_index import Index


def write_hook(hook_path: str, script_path: str, hook_name: str) -> None:
    python_executable = shlex.quote(sys.executable)
    quoted_script_path = shlex.quote(script_path)
    quoted_hook_name = shlex.quote(hook_name)
    content = "\n".join(
        [
            "#!/bin/sh",
            "set -e",
            f'exec {python_executable} {quoted_script_path} {quoted_hook_name} "$@"',
            "",
        ]
    )
    with open(hook_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    mode = os.stat(hook_path).st_mode
    os.chmod(hook_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_srs_index(repo_root: str) -> bool:
    srs_dir = os.path.join(repo_root, SRS_DIR_NAME)
    os.makedirs(srs_dir, exist_ok=True)

    index_path = os.path.join(srs_dir, INDEX_FILE_NAME)
    if os.path.isdir(index_path):
        return False
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8"):
            pass
    return True


def _to_indexed_path(repo_root: str, abs_path: str) -> str:
    rel_path = os.path.relpath(abs_path, repo_root)
    return util.normalize_path(rel_path.replace(os.sep, "/"))


def find_repeat_tracked_paths(repo_root: str) -> list[str]:
    tracked_paths: set[str] = set()

    def walk(current_dir: str, tracked_parent: bool) -> None:
        entries = sorted(
            os.scandir(current_dir),
            key=lambda entry: entry.name,
        )

        has_marker = any(
            entry.name == REPEAT_MARKER_NAME and entry.is_file(follow_symlinks=False)
            for entry in entries
        )
        has_norepeat_marker = any(
            entry.name == NOREPEAT_MARKER_NAME and entry.is_file(follow_symlinks=False)
            for entry in entries
        )
        tracked_here = has_marker or (tracked_parent and not has_norepeat_marker)

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name in {".git", SRS_DIR_NAME}:
                    continue
                walk(entry.path, tracked_here)
                continue
            if not tracked_here:
                continue
            if entry.name in {REPEAT_MARKER_NAME, NOREPEAT_MARKER_NAME}:
                continue
            if entry.is_file(follow_symlinks=False):
                tracked_paths.add(_to_indexed_path(repo_root, entry.path))

    walk(repo_root, tracked_parent=False)
    return sorted(tracked_paths)


def initialize_index_from_repeat_markers(repo_root: str, index_path: str) -> int:
    index = Index(index_path)
    lines = index._read()
    original_lines = list(lines)
    existing_paths = set(index._rows_by_path(lines))

    for tracked_path in find_repeat_tracked_paths(repo_root):
        if tracked_path in existing_paths:
            continue
        if not index._is_note_path(tracked_path):
            continue
        index._add_new(tracked_path, lines)
        existing_paths.add(tracked_path)

    if lines != original_lines:
        index._write(lines)

    return len(lines) - len(original_lines)


def main() -> int:
    context = resolve_repo_context()
    if context is None:
        print("Not inside a git repository.")
        return 1

    repo_root = context.repo_root
    hooks_dir = context.hooks_dir
    os.makedirs(hooks_dir, exist_ok=True)

    hooks_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "hooks.py")
    )

    if not os.path.exists(hooks_path):
        print(f"Missing hook script: {hooks_path}")
        return 1

    if not ensure_srs_index(repo_root):
        print("Could not initialize .srs/index.txt")
        return 1

    initialized_count = initialize_index_from_repeat_markers(
        repo_root, context.index_path
    )

    for hook in HOOKS:
        hook_path = os.path.join(hooks_dir, hook)
        write_hook(hook_path, hooks_path, hook)

    print("Installed hooks:", ", ".join(HOOKS))
    print("Ensured index:", os.path.join(SRS_DIR_NAME, INDEX_FILE_NAME))
    print(f"Initialized cards from {REPEAT_MARKER_NAME} markers:", initialized_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
