#!/usr/bin/env python3
import util

from reviewing import ReviewSession, ReviewUI
from reviewing.config import load_review_config


def main() -> int:
    ui: ReviewUI | None = None
    try:
        repo_root = util.get_repo_root()
        if not repo_root:
            print("Not inside a git repository.")
            return 1

        config = load_review_config(repo_root)
        ui = ReviewUI(rating_buttons=config.rating_buttons)
        session = ReviewSession(
            repo_root=repo_root,
            ui=ui,
            reveal_mode=config.reveal_mode,
            cloze_open=config.cloze_open,
            cloze_close=config.cloze_close,
            mask_char=config.mask_char,
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
