#!/usr/bin/env python3
from core import util

from core.config import load_review_config
from card.parsers import build_parser_registry
from core.session import ReviewSession
from ui.ui import ReviewUI


def main() -> int:
    ui: ReviewUI | None = None
    try:
        repo_root = util.get_repo_root()
        if not repo_root:
            print("Not inside a git repository.")
            return 1

        config = load_review_config(repo_root)
        parser_registry = build_parser_registry(config)
        ui = ReviewUI(config=config)
        session = ReviewSession(
            repo_root=repo_root,
            ui=ui,
            config=config,
            parser_registry=parser_registry,
        )
        return session.run()
    except KeyboardInterrupt:
        if ui:
            ui.print_message("\nInterrupted.")
        else:
            print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
