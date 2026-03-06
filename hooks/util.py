#!/usr/bin/env python3
import os
import subprocess

def run_git(args: list, cwd: str):
    result = subprocess.run( ["git"] + args, cwd=cwd, text=True, capture_output=True)
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

def note_id_from_path(path: str) -> str:
    base = os.path.basename(path)
    name, _ = os.path.splitext(base)
    return name
