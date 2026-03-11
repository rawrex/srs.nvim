#!/usr/bin/env python3
import sys
import util
from Index import Index
from typing import Dict, List, Set, Tuple

class Handler:
    def __init__(self, repository_root: str) -> None:
        self.repository_root = repository_root

    def is_rev_exists(self, rev: str) -> bool:
        code, _out, _err = util.run_git(["rev-parse", "--verify", rev], cwd=self.repository_root)
        return code == 0

    def diff_name_status(self, old: str, new: str) -> str:
        code, out, _err = util.run_git( ["diff", "--name-status", "-M", "-C", old, new], cwd=self.repository_root)
        if code == 0:
            return out
        return ""

    def diff_name_status_cached(self) -> str:
        args = ["diff", "--cached", "--name-status", "-M", "-C"]
        if not self.is_rev_exists("HEAD"):
            args.append("--root")
        code, out, _err = util.run_git(args, cwd=self.repository_root)
        if code != 0:
            return ""
        return out

    def handle_pre_commit(self, index: Index) -> None:
        diff_text = self.diff_name_status_cached()
        index.apply_diff_and_stage(self.repository_root, diff_text)

    def handle_pre_merge_commit(self, index: Index) -> None:
        diff_text = self.diff_name_status_cached()
        index.apply_diff_and_stage(self.repository_root, diff_text)

    def handle_post_checkout(self, index: Index, args: List[str]) -> None:
        if len(args) < 2:
            return
        old_ref, new_ref = args[0], args[1]
        diff_text = self.diff_name_status(old_ref, new_ref)
        index.apply_diff(diff_text)

    def handle_post_rewrite(self, index: Index) -> None:
        if data := sys.stdin.read().strip().splitlines():
            for line in data:
                parts = line.split()
                if len(parts) < 2:
                    continue
                old_ref, new_ref = parts[0], parts[1]
                diff_text = self.diff_name_status(old_ref, new_ref)
                index.apply_diff(diff_text)


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

