import os
import time

from fsrs import Scheduler

from core import util
from core.card import Card
from core.cards_manager import CardsManager
from core.config import ReviewConfig
from core.parsers import ParserRegistry
from ui.ui import ReviewUI, SessionEntryUI


class ReviewSession:
    def __init__(
        self,
        repo_root: str,
        ui: ReviewUI,
        config: ReviewConfig,
        parser_registry: ParserRegistry,
        session_entry_ui: SessionEntryUI | None,
        scheduler: Scheduler,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.session_entry_ui = session_entry_ui
        self.between_notes_timeout_ms = config.between_notes_timeout_ms
        self.auto_stage_reviewed_cards = config.auto_stage_reviewed_cards
        self.scheduler = scheduler
        self.cards_manager = CardsManager(
            repo_root=repo_root,
            parser_registry=parser_registry,
        )
        self._reviewed_card_paths: set[str] = set()

    def run(self) -> int:
        if not self.cards_manager.has_index():
            self.ui.print_message("Missing index")
            return 1

        cards = self.cards_manager.load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        if self.session_entry_ui:
            estimated_minutes = self.cards_manager.estimate_due_cards_duration_minutes(
                cards
            )
            self.session_entry_ui.show_start_menu(total, estimated_minutes)
        try:
            for idx, due_card in enumerate(cards, start=1):
                card = due_card.card
                note_context_blocks = due_card.note_context_blocks
                question_title = f"\n[{idx}/{total}] {card.note_filename}"

                # Step 1: question + reveals.
                question_started_ns = time.monotonic_ns()
                self.ui.run_question_step(
                    question_title,
                    card,
                    note_context_blocks=note_context_blocks,
                )

                review_duration_ms = max(
                    0, (time.monotonic_ns() - question_started_ns) // 1_000_000
                )
                review_duration_s = review_duration_ms / 1000
                answer_title = (
                    f"\n[{idx}/{total}] {card.note_filename} "
                    f"— answer ({review_duration_s:.1f}s)"
                )

                # Step 2: answer view.
                suggested_rating = card.suggested_rating()
                answer_view = card.answer_view()
                self.ui.show_answer_step(
                    answer_title,
                    card,
                    answer_view,
                    note_context_blocks=note_context_blocks,
                )

                # Step 3: rating.
                self.ui.print_message("")
                rating = self.ui.prompt_rating_step(suggested_rating)
                updated_card, review_log = self.scheduler.review_card(
                    card.metadata.scheduler_card,
                    rating,
                    review_duration=int(review_duration_ms),
                )
                card.metadata.scheduler_card = updated_card
                card.metadata.review_logs.append(review_log)
                self.cards_manager.save_reviewed_card(card)
                self._stage_reviewed_card(card)
                self.ui.print_message("Saved")
                if idx < total and self.between_notes_timeout_ms > 0:
                    time.sleep(self.between_notes_timeout_ms / 1000)
        finally:
            self._commit_reviewed_cards()

        return 0

    def _stage_reviewed_card(self, card: Card) -> None:
        if not self.auto_stage_reviewed_cards:
            return
        rel_card_path = os.path.relpath(card.card_path, self.repo_root).replace(
            os.sep, "/"
        )
        code, _out, _err = util.run_git(
            ["add", "--", rel_card_path],
            cwd=self.repo_root,
        )
        if code == 0:
            self._reviewed_card_paths.add(rel_card_path)

    def _commit_reviewed_cards(self) -> None:
        if not self.auto_stage_reviewed_cards or not self._reviewed_card_paths:
            return
        reviewed_paths = sorted(self._reviewed_card_paths)
        code, _out, _err = util.run_git(
            ["diff", "--cached", "--quiet", "--"] + reviewed_paths,
            cwd=self.repo_root,
        )
        if code == 0:
            return
        if code != 1:
            return
        code, _out, _err = util.run_git(
            ["commit", "-m", "Spaced repetition session", "--"] + reviewed_paths,
            cwd=self.repo_root,
        )
        if code == 0:
            self._reviewed_card_paths.clear()
