#!/usr/bin/env python3
import os
import sys
import util
from Index import Index
from Handler import Handler

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
    handler = Handler(repo_root)

    if event == "pre-commit":
        handler.handle_pre_commit(index)
    elif event == "pre-merge-commit":
        handler.handle_pre_merge_commit(index)
    elif event == "post-checkout":
        handler.handle_post_checkout(index, sys.argv[2:])
    elif event == "post-rewrite":
        handler.handle_post_rewrite(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
