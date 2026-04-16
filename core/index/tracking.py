#!/usr/bin/env python3
import os

from core import util
from core.util import EXCLUDE_FROM_TRACKING, NOREPEAT_MARKER_FILENAME, REPEAT_MARKER_FILENAME


def _to_indexed_path(repo_root: str, abs_path: str) -> str:
    rel_path = os.path.relpath(abs_path, repo_root)
    return util.normalize_path(rel_path.replace(os.sep, "/"))


def is_directory_tracked(directory: str, repeat_dirs: set[str], norepeat_dirs: set[str]) -> bool:
    tracked = "" in repeat_dirs
    if "" in norepeat_dirs:
        tracked = False

    current = ""
    for part in [part for part in directory.split("/") if part]:
        current = f"{current}/{part}" if current else part
        if current in norepeat_dirs:
            tracked = False
        if current in repeat_dirs:
            tracked = True
    return tracked


def tracked_paths_from_repo_paths(repo_paths: list[str]) -> set[str]:
    repeat_dirs: set[str] = set()
    norepeat_dirs: set[str] = set()
    file_paths: list[str] = []

    for repo_path in repo_paths:
        name = os.path.basename(repo_path)
        if name == REPEAT_MARKER_FILENAME:
            repeat_dirs.add(os.path.dirname(repo_path))
            continue
        if name == NOREPEAT_MARKER_FILENAME:
            norepeat_dirs.add(os.path.dirname(repo_path))
            continue
        file_paths.append(repo_path)

    tracked_paths: set[str] = set()
    for repo_path in file_paths:
        if is_directory_tracked(os.path.dirname(repo_path), repeat_dirs, norepeat_dirs):
            tracked_paths.add(util.normalize_path(repo_path))
    return tracked_paths


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
            if entry.is_file(follow_symlinks=False):
                tracked_paths.add(_to_indexed_path(repo_root, entry.path))

    walk(repo_root, tracked_parent=False)
    return sorted(tracked_paths)
