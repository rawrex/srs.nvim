import os
import time

from fsrs import Scheduler

from core import util
from core.cards_manager import CardsManager
from core.parsers import ParserRegistry
from core.ui import ReviewUI


class ReviewSession:
    def __init__(self, ui: ReviewUI, parser_registry: ParserRegistry, scheduler: Scheduler) -> None:
        self.ui = ui
        self.scheduler = scheduler
        self.cards_manager = CardsManager(parser_registry=parser_registry)

    def run(self) -> int:
        if not os.path.exists(util.get_index_path()):
            self.ui.print_message("Missing index")
            return 1

        cards = self.cards_manager.load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        self.ui.intro(total)

        for idx, due_card in enumerate(cards, start=1):
            card = due_card.card
            context_blocks = due_card.context
            question_title = f"\n[{idx}/{total}] {os.path.basename(card.index_entry.note_abs_path)}"

            # Step 1: question + reveals.
            question_started_ns = time.monotonic_ns()
            self.ui.run_question_step(question_title, card, note_context_blocks=context_blocks)

            review_duration_ms = max(0, (time.monotonic_ns() - question_started_ns) // 1_000_000)
            review_duration_s = review_duration_ms / 1000
            answer_title = f"\n[{idx}/{total}] {os.path.basename(card.index_entry.note_abs_path)} — answer ({review_duration_s:.1f}s)"

            # Step 2: answer view.
            suggested_rating = card.suggested_rating()
            answer_view = card.answer_view()
            self.ui.show_answer_step(answer_title, card, answer_view, note_context_blocks=context_blocks)

            # Step 3: rating.
            self.ui.print_message("")
            rating = self.ui.prompt_rating_step(suggested_rating)
            updated_card, review_log = self.scheduler.review_card(
                card.metadata.scheduler_card, rating, review_duration=int(review_duration_ms)
            )
            card.metadata.scheduler_card = updated_card
            card.metadata.review_logs.append(review_log)

            card.index_entry.write_metadata(card.metadata)
            self.ui.print_message("Saved")

        return 0
