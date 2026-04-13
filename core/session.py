import os
import time

from fsrs import Scheduler

from core.cards_manager import CardsManager
from core.index.storage import write_metadata
from core.parsers import ParserRegistry
from core.ui import ReviewUI, SessionEntryUI


class ReviewSession:
    def __init__(
        self,
        ui: ReviewUI,
        repo_root: str,
        parser_registry: ParserRegistry,
        session_entry_ui: SessionEntryUI | None,
        scheduler: Scheduler,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.session_entry_ui = session_entry_ui
        self.scheduler = scheduler
        self.cards_manager = CardsManager(repo_root=repo_root, parser_registry=parser_registry)

    def run(self) -> int:
        if not os.path.exists(os.path.join(self.repo_root, ".srs", "index.txt")):
            self.ui.print_message("Missing index")
            return 1

        cards = self.cards_manager.load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        if self.session_entry_ui:
            self.session_entry_ui.show_start_menu(total)
        for idx, due_card in enumerate(cards, start=1):
            card = due_card.card
            note_context_blocks = due_card.note_context_blocks
            question_title = f"\n[{idx}/{total}] {card.note_filename}"

            # Step 1: question + reveals.
            question_started_ns = time.monotonic_ns()
            self.ui.run_question_step(question_title, card, note_context_blocks=note_context_blocks)

            review_duration_ms = max(0, (time.monotonic_ns() - question_started_ns) // 1_000_000)
            review_duration_s = review_duration_ms / 1000
            answer_title = f"\n[{idx}/{total}] {card.note_filename} — answer ({review_duration_s:.1f}s)"

            # Step 2: answer view.
            suggested_rating = card.suggested_rating()
            answer_view = card.answer_view()
            self.ui.show_answer_step(answer_title, card, answer_view, note_context_blocks=note_context_blocks)

            # Step 3: rating.
            self.ui.print_message("")
            rating = self.ui.prompt_rating_step(suggested_rating)
            updated_card, review_log = self.scheduler.review_card(
                card.metadata.scheduler_card, rating, review_duration=int(review_duration_ms)
            )
            card.metadata.scheduler_card = updated_card
            card.metadata.review_logs.append(review_log)

            # TODO shoeld be moved into the Card
            write_metadata(os.path.join(self.repo_root, ".srs", f"{card.index_entry.card_id}.json"), card.metadata)
            self.ui.print_message("Saved")

        return 0
