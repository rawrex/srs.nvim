#!/usr/bin/env python3
import os
import time
import hashlib
import subprocess
from typing import Dict, Set, Tuple

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

def generate_note_id(path: str, existing_ids: Set[str]) -> str:
    created_at_ns = str(time.time_ns())
    filename = os.path.basename(path)
    if not filename:
        filename = "item"
    suffix = 0
    while True:
        payload = f"{created_at_ns}:{filename}:{suffix}".encode("utf-8")
        candidate = hashlib.blake2s(payload, digest_size=12).hexdigest()
        if candidate not in existing_ids:
            return candidate
        suffix += 1

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
            old_path = normalize_path(parts[1])
            new_path = normalize_path(parts[2])
            renames[old_path] = new_path
        elif code == "D" and len(parts) >= 2:
            deletes.add(normalize_path(parts[1]))
        elif code == "A" and len(parts) >= 2:
            adds.add(normalize_path(parts[1]))
    return renames, deletes, adds

