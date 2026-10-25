#!/usr/bin/env python3
import os

from core import util
from core.util import EXCLUDE_FROM_TRACKING, GIT_RELATED_FILENAMES, NOREPEAT_MARKER_FILENAME, REPEAT_MARKER_FILENAME


def find_repeat_tracked_paths() -> list[str]:
    repo_root = util._RUNTIME_CONTEXT.repo_root_path
    tracked_paths: set[str] = set()

    def walk(current_dir: str, tracked_parent: bool) -> None:
        entries = sorted(os.scandir(current_dir), key=lambda entry: entry.name)
        has_repeat = any(
            entry.name == REPEAT_MARKER_FILENAME and entry.is_file(follow_symlinks=False) for entry in entries
        )
        has_norepeat = any(
            entry.name == NOREPEAT_MARKER_FILENAME and entry.is_file(follow_symlinks=False) for entry in entries
        )
        tracked_here = has_repeat or (tracked_parent and not has_norepeat)

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in EXCLUDE_FROM_TRACKING:
                    walk(entry.path, tracked_here)
                    continue
            if not tracked_here:
                continue
            if entry.name in {REPEAT_MARKER_FILENAME, NOREPEAT_MARKER_FILENAME}:
                continue
            if entry.name in GIT_RELATED_FILENAMES:
                continue
            if entry.is_file(follow_symlinks=False):
                tracked_paths.add(util.repo_relative_path(repo_root, entry.path))

    walk(repo_root, tracked_parent=False)
    return sorted(tracked_paths)
