#!/usr/bin/env python3
import os
import subprocess


def run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false"] + args,
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    return result.returncode, result.stdout, result.stderr


def get_repo_root() -> str:
    code, out, _ = run_git(["rev-parse", "--show-toplevel"], cwd=os.getcwd())
    if code == 0:
        return out.strip()
    return ""


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
