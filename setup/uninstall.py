#!/usr/bin/env python3
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from setup.common import HOOKS, resolve_repo_context


def _is_managed_hook_script(hook_path: str) -> bool:
    try:
        with open(hook_path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return False

    return (
        "#!/bin/sh" in content
        and "set -e" in content
        and "hooks.py" in content
        and '"$@"' in content
    )


def remove_installed_hooks(hooks_dir: str) -> int:
    removed_count = 0
    for hook in HOOKS:
        hook_path = os.path.join(hooks_dir, hook)
        if not os.path.isfile(hook_path):
            continue
        if not _is_managed_hook_script(hook_path):
            continue
        os.remove(hook_path)
        removed_count += 1
    return removed_count


def remove_srs_dir(srs_dir: str) -> bool:
    if not os.path.exists(srs_dir):
        return False
    if not os.path.isdir(srs_dir):
        return False
    shutil.rmtree(srs_dir)
    return True


def main() -> int:
    context = resolve_repo_context()
    if context is None:
        print("Not inside a git repository.")
        return 1

    removed_hooks = remove_installed_hooks(context.hooks_dir)
    removed_srs = remove_srs_dir(context.srs_dir)

    print("Removed hooks:", removed_hooks)
    print("Removed .srs directory:", "yes" if removed_srs else "no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
