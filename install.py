#!/usr/bin/env python3
import os
import shlex
import stat
import sys

import util
from srs_index import Index

HOOKS = ["pre-commit", "pre-merge-commit", "post-checkout", "post-rewrite"]
SRS_DIR_NAME = ".srs"
INDEX_FILE_NAME = "index.txt"
REPEAT_MARKER_NAME = ".repeat"


def get_git_dir(repo_root: str) -> str:
    code, out, _ = util.run_git(["rev-parse", "--git-dir"], cwd=repo_root)
    if code == 0:
        git_dir = out.strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.join(repo_root, git_dir)
        return git_dir
    return ""


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
    # Execute permission for owner, group, and others.
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
    marker_dirs: list[str] = []
    for current_dir, dirnames, filenames in os.walk(repo_root, topdown=True):
        dirnames[:] = sorted(
            name for name in dirnames if name not in {".git", SRS_DIR_NAME}
        )
        if REPEAT_MARKER_NAME in filenames:
            marker_dirs.append(current_dir)

    tracked_paths: set[str] = set()
    for marker_dir in marker_dirs:
        for current_dir, dirnames, filenames in os.walk(marker_dir, topdown=True):
            dirnames[:] = sorted(
                name for name in dirnames if name not in {".git", SRS_DIR_NAME}
            )
            for name in sorted(filenames):
                if name == REPEAT_MARKER_NAME:
                    continue
                path = os.path.join(current_dir, name)
                if not os.path.isfile(path):
                    continue
                tracked_paths.add(_to_indexed_path(repo_root, path))
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
    repo_root = util.get_repo_root()
    if not repo_root:
        print("Not inside a git repository.")
        return 1

    git_dir = get_git_dir(repo_root)
    if not git_dir:
        print("Could not determine git directory.")
        return 1

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    hooks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "hooks.py"))

    if not os.path.exists(hooks_path):
        print(f"Missing hook script: {hooks_path}")
        return 1

    if not ensure_srs_index(repo_root):
        print("Could not initialize .srs/index.txt")
        return 1

    index_path = os.path.join(repo_root, SRS_DIR_NAME, INDEX_FILE_NAME)
    initialized_count = initialize_index_from_repeat_markers(repo_root, index_path)

    for hook in HOOKS:
        hook_path = os.path.join(hooks_dir, hook)
        write_hook(hook_path, hooks_path, hook)

    print("Installed hooks:", ", ".join(HOOKS))
    print("Ensured index:", os.path.join(SRS_DIR_NAME, INDEX_FILE_NAME))
    print(f"Initialized cards from {REPEAT_MARKER_NAME} markers:", initialized_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
