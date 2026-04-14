#!/usr/bin/env python3
# ruff: noqa: E402
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import util
from core.config import load_review_config
from core.index.index import Index
from core.parsers import build_parser_registry
from hooks.handler import Handler


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    event = sys.argv[1]

    repo_root = util.get_repo_root_path()
    if not repo_root:
        return 0

    index_path = util.get_index_path()
    if not os.path.exists(index_path):
        return 0

    config = load_review_config()
    parser_registry = build_parser_registry(config)
    index = Index(parser_registry=parser_registry)
    handler = Handler()

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
