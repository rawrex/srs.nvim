import os
import time
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from fsrs import Rating, Scheduler

from core import util
from core.card import CardRef
from core.index import Index
from core.model import IndexEntry


@runtime_checkable
class ReviewUIProtocol(Protocol):
    """UI boundary for the review engine."""

    def print_message(self, message: str) -> None: ...

    def intro(self, total: int, note_paths: list[str]) -> None: ...

    def card_step(self, card_ref: CardRef) -> int | None:
        """Present the card until the user answers; return paused nanoseconds.

        ``None`` means the card was skipped.
        """
        ...

    def rating_step(self) -> Rating: ...


class ReviewEngine:
    """UI-agnostic review flow: select due entries, time them, persist reviews."""

    def __init__(self, ui: ReviewUIProtocol, scheduler: Scheduler) -> None:
        self.ui = ui
        self.scheduler = scheduler
        self.index = Index()

    def load_due_entries(self, time_point: datetime) -> list[IndexEntry]:
        return [entry for entry in self.index.load_entries() if entry.read_metadata().scheduler_card.due <= time_point]

    def run(self) -> int:
        if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
            self.ui.print_message("Missing index")
            return 1

        entries = self.load_due_entries(time_point=datetime.now(timezone.utc))
        if not entries:
            self.ui.print_message("🎉 No due cards 🎉")
            return 0

        total = len(entries)
        note_paths = sorted({entry.note_path for entry in entries})
        self.ui.intro(total, note_paths)

        for idx, entry in enumerate(entries, start=1):
            card_ref = CardRef(
                index=idx,
                total=total,
                card_id=entry.card_id,
                note_path=entry.note_path,
                card_type=entry.card_type,
                start_line=entry.start_line,
                end_line=entry.end_line,
            )

            started_ns = time.monotonic_ns()
            pause_ns = self.ui.card_step(card_ref)
            if pause_ns is None:  # Skipped
                self.ui.print_message("Skipped")
                continue
            duration_ms = max(0, (time.monotonic_ns() - started_ns - pause_ns) // 1_000_000)

            rating = self.ui.rating_step()
            metadata = entry.read_metadata()
            updated_card, review_log = self.scheduler.review_card(
                metadata.scheduler_card, rating, review_duration=int(duration_ms)
            )
            metadata.scheduler_card = updated_card
            metadata.review_logs.append(review_log)
            entry.write_metadata(metadata)
            self.ui.print_message("Saved")

        return 0
