#!/usr/bin/env python3
import util
import os
import stat

HOOKS = ["post-commit", "post-merge", "post-checkout", "post-rewrite"]

def get_git_dir(repo_root: str) -> str:
    code, out, _ = util.run_git(["rev-parse", "--git-dir"], cwd=repo_root)
    if code != 0:
        return ""
    git_dir = out.strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(repo_root, git_dir)
    return git_dir

def write_hook(hook_path: str, script_path: str, hook_name: str) -> None:
    content = "\n".join(
        [
            "#!/bin/sh",
            "set -e",
            f'exec python3 "{script_path}" {hook_name} "$@"',
            "",
        ]
    )
    with open(hook_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    mode = os.stat(hook_path).st_mode
    os.chmod(hook_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def main() -> int:
    repo_root = util.get_repo_root()
    if not repo_root:
        print("Not inside a git repository.")
        return 1

    git_dir = get_git_dir(repo_root)
    if not git_dir:
        print("Could not determine git directory.")
        return 1

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "hooks.py"))

    if not os.path.exists(script_path):
        print(f"Missing hook script: {script_path}")
        return 1

    for hook in HOOKS:
        hook_path = os.path.join(hooks_dir, hook)
        write_hook(hook_path, script_path, hook)

    print("Installed hooks:", ", ".join(HOOKS))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
