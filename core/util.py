#!/usr/bin/env python3
import os
import subprocess
from dataclasses import dataclass

SRS_DIR_NAME = ".srs"
INDEX_FILENAME = "index.txt"
CONFIG_FILENAME = "config.json"
REPEAT_MARKER_FILENAME = ".repeat"
NOREPEAT_MARKER_FILENAME = ".norepeat"

EXCLUDE_FROM_TRACKING = [SRS_DIR_NAME, ".git"]


@dataclass(frozen=True)
class RuntimeContext:
    cwd: str
    repo_root_path: str
    git_dir: str
    srs_path: str
    index_path: str
    config_path: str
    hooks_path: str


_RUNTIME_CONTEXT: RuntimeContext


def run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    result = subprocess.run(["git", "-c", "core.quotepath=false"] + args, cwd=cwd, text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr


def _resolve_repo_root_path(cwd: str) -> str:
    code, out, _ = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if code == 0:
        return out.strip()
    return ""


def _resolve_git_dir(repo_root_path: str) -> str:
    code, out, _ = run_git(["rev-parse", "--git-dir"], cwd=repo_root_path)
    if code == 0:
        git_dir = out.strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.join(repo_root_path, git_dir)
        return git_dir
    return ""


def init_runtime_context(cwd: str) -> RuntimeContext:
    global _RUNTIME_CONTEXT
    repo_root_path = _resolve_repo_root_path(cwd)
    git_dir = _resolve_git_dir(repo_root_path)
    srs_path = os.path.join(repo_root_path, SRS_DIR_NAME)
    index_path = os.path.join(srs_path, INDEX_FILENAME)
    config_path = os.path.join(srs_path, CONFIG_FILENAME)
    hooks_path = os.path.join(git_dir, "hooks")
    _RUNTIME_CONTEXT = RuntimeContext(
        cwd=cwd,
        repo_root_path=repo_root_path,
        git_dir=git_dir,
        srs_path=srs_path,
        index_path=index_path,
        config_path=config_path,
        hooks_path=hooks_path,
    )
    return _RUNTIME_CONTEXT


def normalize_path(path: str) -> str:
    if not path:
        return path
    if path.startswith("/"):
        return path
    return "/" + path


def parse_diff(text: str) -> tuple[dict[str, str], set[str], set[str]]:
    renames: dict[str, str] = {}
    deletes: set[str] = set()
    adds: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        code = status[:1]
        if code == "R" and len(parts) >= 3:
            old_path = normalize_path(parts[1])
            new_path = normalize_path(parts[2])
            renames[old_path] = new_path
        elif code == "C" and len(parts) >= 3:
            adds.add(normalize_path(parts[2]))
        elif code == "D" and len(parts) >= 2:
            deletes.add(normalize_path(parts[1]))
        elif code == "A" and len(parts) >= 2:
            adds.add(normalize_path(parts[1]))
    return renames, deletes, adds
