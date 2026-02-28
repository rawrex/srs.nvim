#!/usr/bin/env python3
import os
import re
import util
import sys
from typing import Dict, List, Set, Tuple


def rev_exists(repo_root: str, rev: str) -> bool:
    code, _out, _err = util.run_git(["rev-parse", "--verify", rev], cwd=repo_root)
    return code == 0


def diff_name_status(repo_root: str, old: str, new: str) -> str:
    code, out, _err = util.run_git(
        ["diff", "--name-status", "-M", "-C", old, new], cwd=repo_root
    )
    if code != 0:
        return ""
    return out


def parse_diff(text: str) -> Tuple[Dict[str, str], Set[str], Set[str]]:
    renames: Dict[str, str] = {}
    deletes: Set[str] = set()
    adds: Set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        code = status[:1]
        if code == "R" and len(parts) >= 3:
            old_path = util.normalize_path(parts[1])
            new_path = util.normalize_path(parts[2])
            renames[old_path] = new_path
        elif code == "D" and len(parts) >= 2:
            deletes.add(util.normalize_path(parts[1]))
        elif code == "A" and len(parts) >= 2:
            adds.add(util.normalize_path(parts[1]))
    return renames, deletes, adds


def update_index_lines(
    lines: List[str], renames: Dict[str, str], deletes: Set[str], adds: Set[str]
) -> Tuple[List[str], bool]:
    changed = False
    updated: List[str] = []
    row_re = re.compile(r"^'([^']*)','([^']*)'\s*$")
    existing_paths: Set[str] = set()
    existing_ids: Set[str] = set()
    for line in lines:
        match = row_re.match(line.rstrip("\n"))
        if not match:
            updated.append(line)
            continue
        note_id, path = match.groups()
        existing_paths.add(path)
        existing_ids.add(note_id)
        if path in deletes:
            changed = True
            continue
        if path in renames:
            new_path = renames[path]
            updated.append(f"'{note_id}','{new_path}'\n")
            changed = True
            existing_paths.add(new_path)
        else:
            updated.append(line)
    for path in sorted(adds):
        if path in existing_paths:
            continue
        note_id = util.note_id_from_path(path)
        if note_id in existing_ids:
            continue
        updated.append(f"'{note_id}','{path}'\n")
        changed = True
        existing_paths.add(path)
        existing_ids.add(note_id)
    return updated, changed


def load_index_lines(index_path: str) -> List[str]:
    with open(index_path, "r", encoding="utf-8") as handle:
        return handle.readlines()


def write_index_lines(index_path: str, lines: List[str]) -> None:
    tmp_path = index_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    os.replace(tmp_path, index_path)


def apply_diff(repo_root: str, index_path: str, diff_text: str) -> bool:
    renames, deletes, adds = parse_diff(diff_text)
    if not renames and not deletes and not adds:
        return False
    lines = load_index_lines(index_path)
    updated, changed = update_index_lines(lines, renames, deletes, adds)
    if changed:
        write_index_lines(index_path, updated)
    return changed


def handle_post_commit(repo_root: str, index_path: str) -> None:
    if not rev_exists(repo_root, "HEAD~1"):
        return
    diff_text = diff_name_status(repo_root, "HEAD~1", "HEAD")
    apply_diff(repo_root, index_path, diff_text)


def handle_post_merge(repo_root: str, index_path: str) -> None:
    if not rev_exists(repo_root, "ORIG_HEAD"):
        return
    diff_text = diff_name_status(repo_root, "ORIG_HEAD", "HEAD")
    apply_diff(repo_root, index_path, diff_text)


def handle_post_checkout(repo_root: str, index_path: str, args: List[str]) -> None:
    if len(args) < 2:
        return
    old_ref, new_ref = args[0], args[1]
    diff_text = diff_name_status(repo_root, old_ref, new_ref)
    apply_diff(repo_root, index_path, diff_text)


def handle_post_rewrite(repo_root: str, index_path: str) -> None:
    data = sys.stdin.read().strip().splitlines()
    if not data:
        return
    for line in data:
        parts = line.split()
        if len(parts) < 2:
            continue
        old_ref, new_ref = parts[0], parts[1]
        diff_text = diff_name_status(repo_root, old_ref, new_ref)
        apply_diff(repo_root, index_path, diff_text)


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    event = sys.argv[1]
    repo_root = util.get_repo_root()
    if not repo_root:
        return 0
    index_path = os.path.join(repo_root, ".srs", "index.txt")
    if not os.path.exists(index_path):
        return 0
    if event == "post-commit":
        handle_post_commit(repo_root, index_path)
    elif event == "post-merge":
        handle_post_merge(repo_root, index_path)
    elif event == "post-checkout":
        handle_post_checkout(repo_root, index_path, sys.argv[2:])
    elif event == "post-rewrite":
        handle_post_rewrite(repo_root, index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
