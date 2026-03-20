#!/usr/bin/env python3
import os
import sys

import util
from hooks_runtime.handler import Handler
from reviewing.config import load_review_config
from reviewing.parsers import build_parser_registry
from srs_index import Index, IndexUpdateAbortError


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

    config = load_review_config(repo_root)
    parser_registry = build_parser_registry(config)
    index = Index(index_path, parser_registry=parser_registry)
    handler = Handler(repo_root)

    try:
        if event == "pre-commit":
            handler.handle_pre_commit(index)
        elif event == "pre-merge-commit":
            handler.handle_pre_merge_commit(index)
        elif event == "post-checkout":
            handler.handle_post_checkout(index, sys.argv[2:])
        elif event == "post-rewrite":
            handler.handle_post_rewrite(index)
    except IndexUpdateAbortError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
