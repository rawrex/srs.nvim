#!/usr/bin/env python3
import util

from review_card import RevealMode
from review_session import ReviewSession
from review_ui import ReviewUI


REVEAL_MODE_WHOLE = RevealMode.WHOLE
REVEAL_MODE_INCREMENTAL = RevealMode.INCREMENTAL
REVEAL_MODE = RevealMode.INCREMENTAL


def main() -> int:
    ui = ReviewUI()
    try:
        repo_root = util.get_repo_root()
        if not repo_root:
            ui.print_message("Not inside a git repository.")
            return 1

        session = ReviewSession(repo_root=repo_root, ui=ui, reveal_mode=REVEAL_MODE)
        return session.run()
    except KeyboardInterrupt:
        ui.print_message("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
