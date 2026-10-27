#!/usr/bin/env python3
import sys

from core import util
from core.index import Index


class Handler:
    def __init__(self) -> None:
        self.root_path = util._RUNTIME_CONTEXT.repo_root_path

    def is_rev_exists(self, rev: str) -> bool:
        code, _, _ = util.run_git(["rev-parse", "--verify", rev], cwd=self.root_path)
        return code == 0

    def handle_pre_commit(self, index: Index) -> None:
        self._handle_cached_diff(index)

    def _handle_cached_diff(self, index: Index) -> None:
        args = ["diff", "--cached", "--name-status", "-M", "-C"]
        if not self.is_rev_exists("HEAD"):
            args.append("--root")
        index.apply_diff(self._git_diff(args))

    def handle_post_checkout(self, index: Index, args: list[str]) -> None:
        if len(args) < 2:
            return
        old_ref, new_ref = args[0], args[1]
        self._apply_ref_diff(index, old_ref, new_ref)

    def handle_post_rewrite(self, index: Index) -> None:
        data = sys.stdin.read().strip().splitlines()
        if not data:
            return
        for line in data:
            parts = line.split()
            if len(parts) < 2:
                continue
            old_ref, new_ref = parts[0], parts[1]
            self._apply_ref_diff(index, old_ref, new_ref)

    def _apply_ref_diff(self, index: Index, old_ref: str, new_ref: str) -> None:
        index.apply_diff(self._git_diff(["diff", "--name-status", "-M", "-C", old_ref, new_ref]))

    def _git_diff(self, args: list[str]) -> str:
        code, diff_text, _ = util.run_git(args, cwd=self.root_path)
        return diff_text if code == 0 else ""
