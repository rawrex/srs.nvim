#!/usr/bin/env python3
import os
import re
import sys
from typing import Dict, List, Set, Tuple
import util

class Index:
    def __init__(self, path: str) -> None:
        self.path = path

    def _stage(self, repo_root: str) -> None:
        rel_index_path = os.path.relpath(self.path, repo_root)
        util.run_git(["add", "--", rel_index_path], cwd=repo_root)

    def _read(self) -> List[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: List[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def apply_diff_and_stage(self, repo_root: str, diff_text: str) -> None:
        if changed := self.apply_diff(diff_text):
            self._stage(repo_root)

    def apply_diff(self, diff_text: str) -> bool:
        renames, deletes, adds = parse_diff(diff_text)
        if not renames and not deletes and not adds:
            return False
        updated, changed = self._update_index_lines(self._read(), renames, deletes, adds)
        if changed:
            self._write(updated)
        return changed

    def _update_index_lines(self, lines: List[str], renames: Dict[str, str], deletes: Set[str], adds: Set[str]) -> Tuple[List[str], bool]:
        change_flag = False
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
                change_flag = True
                continue
            if path in renames:
                change_flag = True
                new_path = renames[path]
                updated.append(f"'{note_id}','{new_path}'\n")
                existing_paths.add(new_path)
            else:  # File changed, no path edits
                updated.append(line)
        for path in sorted(adds):
            if path in existing_paths:
                continue
            note_id = util.generate_note_id(path, existing_ids)
            change_flag = True
            updated.append(f"'{note_id}','{path}'\n")
            existing_paths.add(path)
            existing_ids.add(note_id)
        return updated, change_flag



def is_rev_exists(repo_root: str, rev: str) -> bool:
    code, _out, _err = util.run_git(["rev-parse", "--verify", rev], cwd=repo_root)
    return code == 0


def diff_name_status(repo_root: str, old: str, new: str) -> str:
    code, out, _err = util.run_git(
        ["diff", "--name-status", "-M", "-C", old, new], cwd=repo_root
    )
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


def handle_pre_commit(index: Index, repo_root: str) -> None:
    diff_text = diff_name_status_cached(repo_root)
    index.apply_diff_and_stage(repo_root, diff_text)


def handle_pre_merge_commit(index: Index, repo_root: str) -> None:
    diff_text = diff_name_status_cached(repo_root)
    index.apply_diff_and_stage(repo_root, diff_text)


def handle_post_checkout(index: Index, repo_root: str, args: List[str]) -> None:
    if len(args) < 2:
        return
    old_ref, new_ref = args[0], args[1]
    diff_text = diff_name_status(repo_root, old_ref, new_ref)
    index.apply_diff(diff_text)


def handle_post_rewrite(index: Index, repo_root: str) -> None:
    if data := sys.stdin.read().strip().splitlines():
        for line in data:
            parts = line.split()
            if len(parts) < 2:
                continue
            old_ref, new_ref = parts[0], parts[1]
            diff_text = diff_name_status(repo_root, old_ref, new_ref)
            index.apply_diff(diff_text)


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
    index = Index(index_path)

    if event == "pre-commit":
        handle_pre_commit(index, repo_root)
    elif event == "pre-merge-commit":
        handle_pre_merge_commit(index, repo_root)
    elif event == "post-checkout":
        handle_post_checkout(index, repo_root, sys.argv[2:])
    elif event == "post-rewrite":
        handle_post_rewrite(index, repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
