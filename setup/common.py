#!/usr/bin/env python3
import os
from dataclasses import dataclass

import util

HOOKS = ["pre-commit", "pre-merge-commit", "post-checkout", "post-rewrite"]
SRS_DIR_NAME = ".srs"
INDEX_FILE_NAME = "index.txt"
REPEAT_MARKER_NAME = ".repeat"
NOREPEAT_MARKER_NAME = ".norepeat"


@dataclass(frozen=True)
class RepoContext:
    repo_root: str
    git_dir: str

    @property
    def hooks_dir(self) -> str:
        return os.path.join(self.git_dir, "hooks")

    @property
    def srs_dir(self) -> str:
        return os.path.join(self.repo_root, SRS_DIR_NAME)

    @property
    def index_path(self) -> str:
        return os.path.join(self.srs_dir, INDEX_FILE_NAME)


def get_git_dir(repo_root: str) -> str:
    code, out, _ = util.run_git(["rev-parse", "--git-dir"], cwd=repo_root)
    if code == 0:
        git_dir = out.strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.join(repo_root, git_dir)
        return git_dir
    return ""


def resolve_repo_context() -> RepoContext | None:
    repo_root = util.get_repo_root()
    if not repo_root:
        return None
    git_dir = get_git_dir(repo_root)
    if not git_dir:
        return None
    return RepoContext(repo_root=repo_root, git_dir=git_dir)
