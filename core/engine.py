import os
import time
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from fsrs import Rating, Scheduler

from core import util
from core.card import Card, CardRef, ViewBlock
from core.factory import CardFactory
from core.index.index import Index
from core.parsers import ParserRegistry


@runtime_checkable
class ReviewUIProtocol(Protocol):
    """UI boundary for the review engine.

    The engine owns the review flow and timing; a UI is responsible only for
    presenting the current step and returning the user's input.
    """

    def print_message(self, message: str) -> None: ...

    def intro(self, total: int, note_paths: list[str]) -> None: ...

    def question_step(self, card_ref: CardRef, card: Card) -> tuple[ViewBlock, int] | None: ...

    def answer_step(self, card_ref: CardRef, card: Card, view: ViewBlock, duration_s: float) -> None: ...

    def rating_step(self, default_rating: Rating | None) -> Rating: ...


class ReviewEngine:
    """UI-agnostic review flow: load due cards, present steps, persist results."""

    def __init__(self, ui: ReviewUIProtocol, parser_registry: ParserRegistry, scheduler: Scheduler) -> None:
        self.ui = ui
        self.scheduler = scheduler
        self.index = Index(parser_registry=parser_registry)
        self.factory = CardFactory(parser_registry=parser_registry)

    def load_due_cards(self, time_point: datetime) -> list[Card]:
        all = self.index.load_entries()
        due = [entry for entry in all if entry.read_metadata().scheduler_card.due <= time_point]
        return [self.factory.make_card(entry, all=all) for entry in due]

    def run(self) -> int:
        if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
            self.ui.print_message("Missing index")
            return 1

        cards = self.load_due_cards(time_point=datetime.now(timezone.utc))
        if not cards:
            self.ui.print_message("🎉 No due cards 🎉")
            return 0

        total = len(cards)
        note_paths = sorted({card.index_entry.note_path for card in cards})
        self.ui.intro(total, note_paths)

        for idx, card in enumerate(cards, start=1):
            card_ref = CardRef(index=idx, total=total, note_path=card.index_entry.note_path)

            # Step 1. Question
            question_started_ns = time.monotonic_ns()
            question = self.ui.question_step(card_ref, card)
            if question is None:  # skipped: leave the card's schedule untouched
                self.ui.print_message("Skipped")
                continue
            _view, pause_ns = question
            duration_ms = max(0, (time.monotonic_ns() - question_started_ns - pause_ns) // 1_000_000)
            review_duration_s = duration_ms / 1000

            # Step 2. Answer view
            suggested_rating = card.suggested_rating()
            answer_view = card.answer_view()
            self.ui.answer_step(card_ref, card, answer_view, review_duration_s)

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
