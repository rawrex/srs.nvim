import os
import time
from datetime import datetime, timezone

from fsrs import Scheduler

from core import util
from core.card import Card
from core.factory import CardFactory
from core.index.index import Index
from core.parsers import ParserRegistry
from core.ui import ReviewUI


class ReviewSession:
    def __init__(self, ui: ReviewUI, parser_registry: ParserRegistry, scheduler: Scheduler) -> None:
        self.ui = ui
        self.scheduler = scheduler
        self.index = Index(parser_registry=parser_registry)
        self.factory = CardFactory(parser_registry=parser_registry)

    def load_due_cards(self) -> list[Card]:
        now = datetime.now(timezone.utc)
        index_entries = self.index.load_entries()
        for index, entry in enumerate(index_entries):
            metadata = entry.read_metadata()
            if metadata.scheduler_card.due > now:
                index_entries.pop(index)
        cards: list[Card] = []
        for entry in index_entries:
            card = self.factory.make_card(index_entry=entry)
            card.context = self.factory.make_context(card, index_entries)
            cards.append(card)
        return cards

    def run(self) -> int:
        if not os.path.exists(util.get_index_path()):
            self.ui.print_message("Missing index")
            return 1

        cards = self.load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        self.ui.intro(total)

        for idx, card in enumerate(cards, start=1):
            note_name = os.path.basename(card.index_entry.note_abs_path)
            question_title = f"\n[{idx}/{total}] {note_name}"

            # Step 1. Question
            question_started_ns = time.monotonic_ns()
            self.ui.question_step(question_title, card, note_context_blocks=card.context)
            duration_ms = max(0, (time.monotonic_ns() - question_started_ns) // 1_000_000)
            review_duration_s = duration_ms / 1000
            answer_title = f"\n[{idx}/{total}] {note_name} — answer ({review_duration_s:.1f}s)"

            # Step 2. Answer view
            suggested_rating = card.suggested_rating()
            answer_view = card.answer_view()
            self.ui.answer_step(answer_title, card, answer_view, note_context_blocks=card.context)

            # Step 3. Rating
            self.ui.print_message("")
            rating = self.ui.rating_step(suggested_rating)
            updated_card, review_log = self.scheduler.review_card(
                card.metadata.scheduler_card, rating, review_duration=int(duration_ms)
            )
            card.metadata.scheduler_card = updated_card
            card.metadata.review_logs.append(review_log)

            card.index_entry.write_metadata(card.metadata)
            self.ui.print_message("Saved")

        return 0
