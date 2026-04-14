#!/usr/bin/env python3
import os
import shlex
import stat
import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

util = import_module("core.util")

HOOKS = ["pre-commit", "pre-merge-commit", "post-checkout", "post-rewrite"]

build_parser_registry = import_module("core.parsers").build_parser_registry
load_review_config = import_module("core.config").load_review_config
Index = import_module("core.index.index").Index
find_repeat_tracked_paths = import_module("core.index.tracking").find_repeat_tracked_paths


def write_hook(hook_path: str, script_path: str, hook_name: str) -> None:
    python_executable = shlex.quote(sys.executable)
    quoted_script_path = shlex.quote(script_path)
    quoted_hook_name = shlex.quote(hook_name)
    content = "\n".join(
        ["#!/bin/sh", "set -e", f'exec {python_executable} {quoted_script_path} {quoted_hook_name} "$@"', ""]
    )
    with open(hook_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    mode = os.stat(hook_path).st_mode
    os.chmod(hook_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_srs_index(repo_root: str) -> bool:
    srs_dir = os.path.join(repo_root, util.SRS_DIR_NAME)
    os.makedirs(srs_dir, exist_ok=True)

    index_path = os.path.join(srs_dir, util.INDEX_FILENAME)
    if os.path.isdir(index_path):
        return False
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8"):
            pass
    return True


def initialize_index_from_repeat_markers() -> int:
    config = load_review_config()
    parser_registry = build_parser_registry(config)
    index = Index(parser_registry=parser_registry)
    tracked_paths = set(find_repeat_tracked_paths())
    return index.add_missing_tracked_paths(tracked_paths)


def main() -> int:
    repo_root = util.get_repo_root_path()
    hooks_dir = util.get_hooks_path()
    os.makedirs(hooks_dir, exist_ok=True)

    hooks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hooks", "hooks.py"))

    if not os.path.exists(hooks_path):
        print(f"Missing hook script: {hooks_path}")
        return 1

    if not ensure_srs_index(repo_root):
        print("Could not initialize .srs/index.txt")
        return 1

    initialized_count = initialize_index_from_repeat_markers()

    for hook in HOOKS:
        hook_path = os.path.join(hooks_dir, hook)
        write_hook(hook_path, hooks_path, hook)

    print("Installed hooks:", ", ".join(HOOKS))
    print("Ensured index:", os.path.join(util.SRS_DIR_NAME, util.INDEX_FILENAME))
    print(f"Initialized cards from {util.REPEAT_MARKER_FILENAME} markers:", initialized_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
