#!/usr/bin/env python3
# ruff: noqa: E402
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console

from core import util
from core.config import load_review_config
from core.parsers import build_parser_registry
from core.session import ReviewSession
from core.ui import ReviewUI


def main() -> int:
    try:
        repo_root = util.get_repo_root_path()
        if not repo_root:
            print("Not inside a git repository.")
            return 1
        config = load_review_config()
        session = ReviewSession(
            ui=ReviewUI(config=config, console=Console()),
            parser_registry=build_parser_registry(config),
            scheduler=config.build_scheduler(),
        )
        return session.run()
    except KeyboardInterrupt:
        print("\nExit.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
