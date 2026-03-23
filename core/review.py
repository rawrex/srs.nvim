#!/usr/bin/env python3
# ruff: noqa: E402
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import util

from core.config import load_review_config
from card.parsers import build_parser_registry
from core.session import ReviewSession
from ui.ui import ReviewUI, SessionEntryUI


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
        session_entry_ui = SessionEntryUI(console=ui.console)
        session = ReviewSession(
            repo_root=repo_root,
            ui=ui,
            config=config,
            parser_registry=parser_registry,
            session_entry_ui=session_entry_ui,
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
