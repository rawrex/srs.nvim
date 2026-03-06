#!/usr/bin/env python3
import os
import re
import util
import sys
from typing import Dict, List, Set, Tuple

def is_rev_exists(repo_root: str, rev: str) -> bool:
    code, _out, _err = util.run_git(["rev-parse", "--verify", rev], cwd=repo_root)
    return code == 0

def diff_name_status(repo_root: str, old: str, new: str) -> str:
    code, out, _err = util.run_git( ["diff", "--name-status", "-M", "-C", old, new], cwd=repo_root)
    if code == 0:
        return out
    return ""

def diff_name_status_cached(repo_root: str) -> str:
    args = ["diff", "--cached", "--name-status", "-M", "-C"]
    if not is_rev_exists(repo_root, "HEAD"):
        args.append("--root")
    code, out, _err = util.run_git(args, cwd=repo_root)
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

def update_index_lines(index: List[str], renames: Dict[str, str], deletes: Set[str], adds: Set[str]) -> Tuple[List[str], bool]:
    change_flag = False
    updated: List[str] = []
    row_re = re.compile(r"^'([^']*)','([^']*)'\s*$")
    existing_paths: Set[str] = set()
    existing_ids: Set[str] = set()
    for line in index:
        match = row_re.match(line.rstrip("\n"))
        if not match:
            updated.append(line)
            continue
        note_id, path = match.groups()
        existing_paths.add(path)
        existing_ids.add(note_id)
        if path in deletes:
            change_flag = True
            continue
        if path in renames:
            change_flag = True
            new_path = renames[path]
            updated.append(f"'{note_id}','{new_path}'\n")
            existing_paths.add(new_path)
        else: # File changed, no path edits
            updated.append(line)
    for path in sorted(adds):
        if path in existing_paths:
            continue
        note_id = util.note_id_from_path(path)
        if note_id in existing_ids:
            continue
        change_flag = True
        updated.append(f"'{note_id}','{path}'\n")
        existing_paths.add(path)
        existing_ids.add(note_id)
    return updated, change_flag

def read_index(index_path: str) -> List[str]:
    with open(index_path, "r", encoding="utf-8") as handle:
        return handle.readlines()

def write_index(index_path: str, lines: List[str]) -> None:
    tmp_path = index_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    os.replace(tmp_path, index_path)

def apply_diff(index_path: str, diff_text: str) -> bool:
    renames, deletes, adds = parse_diff(diff_text)
    if not renames and not deletes and not adds:
        return False
    index_lines = read_index(index_path)
    updated, changed = update_index_lines(index_lines, renames, deletes, adds)
    if changed:
        write_index(index_path, updated)
    return changed

def stage_index(repo_root: str, index_path: str) -> None:
    rel_index_path = os.path.relpath(index_path, repo_root)
    util.run_git(["add", "--", rel_index_path], cwd=repo_root)

def apply_diff_and_stage(repo_root: str, index_path: str, diff_text: str) -> None:
    if changed := apply_diff(index_path, diff_text):
        stage_index(repo_root, index_path)

def handle_pre_commit(repo_root: str, index_path: str) -> None:
    diff_text = diff_name_status_cached(repo_root)
    apply_diff_and_stage(repo_root, index_path, diff_text)

def handle_pre_merge_commit(repo_root: str, index_path: str) -> None:
    diff_text = diff_name_status_cached(repo_root)
    apply_diff_and_stage(repo_root, index_path, diff_text)

def handle_post_checkout(repo_root: str, index_path: str, args: List[str]) -> None:
    if len(args) < 2:
        return
    old_ref, new_ref = args[0], args[1]
    diff_text = diff_name_status(repo_root, old_ref, new_ref)
    apply_diff(index_path, diff_text)

def handle_post_rewrite(repo_root: str, index_path: str) -> None:
    if data := sys.stdin.read().strip().splitlines():
        for line in data:
            parts = line.split()
            if len(parts) < 2:
                continue
            old_ref, new_ref = parts[0], parts[1]
            diff_text = diff_name_status(repo_root, old_ref, new_ref)
            apply_diff(index_path, diff_text)

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
    if event == "pre-commit":
        handle_pre_commit(repo_root, index_path)
    elif event == "pre-merge-commit":
        handle_pre_merge_commit(repo_root, index_path)
    elif event == "post-checkout":
        handle_post_checkout(repo_root, index_path, sys.argv[2:])
    elif event == "post-rewrite":
        handle_post_rewrite(repo_root, index_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
