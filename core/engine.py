import os
import time
from datetime import UTC, datetime
from typing import Any

from fsrs import Rating, Scheduler

from core import util
from core.index import Index
from core.model import IndexEntry
from core.protocol import JsonLineTransport


class ReviewEngine:
    """Review flow driven by the nvim client over newline-delimited JSON."""

    def __init__(self, transport: JsonLineTransport, scheduler: Scheduler) -> None:
        self.transport = transport
        self.scheduler = scheduler
        self.index = Index()

    def load_due_entries(self, time_point: datetime) -> list[IndexEntry]:
        return [entry for entry in self.index.load_entries() if entry.read_metadata().scheduler_card.due <= time_point]

    def run(self) -> int:
        if not os.path.exists(util._RUNTIME_CONTEXT.index_path):
            self._send_notice("Missing index")
            return 1

        entries = self.load_due_entries(time_point=datetime.now(UTC))
        if not entries:
            self._send_notice("🎉 No due cards 🎉")
            return 0

        total = len(entries)
        note_paths = sorted({entry.note_path for entry in entries})
        self._intro(total, note_paths)

        for idx, entry in enumerate(entries, start=1):
            started_ns = time.monotonic_ns()
            pause_ns = self._card_step(idx, total, entry)
            if pause_ns is None:  # Skipped
                self._send_notice("Skipped")
                continue
            duration_ms = max(0, (time.monotonic_ns() - started_ns - pause_ns) // 1_000_000)

            rating = self._rating_step()
            metadata = entry.read_metadata()
            updated_card, review_log = self.scheduler.review_card(
                metadata.scheduler_card, rating, review_duration=int(duration_ms)
            )
            metadata.scheduler_card = updated_card
            metadata.review_logs.append(review_log)
            entry.write_metadata(metadata)
            self._send_notice("Saved")

        return 0

    def _send_notice(self, message: str, level: str = "info") -> None:
        self.transport.send({"type": "notice", "level": level, "text": message})

    def _intro(self, total: int, note_paths: list[str]) -> None:
        self.transport.send({"type": "intro", "due": total, "notes": note_paths})
        while self._await_event().get("type") != "start":
            continue

    def _card_step(self, index: int, total: int, entry: IndexEntry) -> int | None:
        self.transport.send(
            {
                "type": "card",
                "card": {
                    "index": index,
                    "total": total,
                    "id": entry.card_id,
                    "note": entry.note_path,
                    "start_line": entry.start_line,
                    "end_line": entry.end_line,
                    "type": entry.card_type,
                },
            }
        )

        paused = False
        pause_total_ns = 0
        pause_start_ns = 0
        while True:
            event_type = self._await_event().get("type")
            if event_type == "pause":
                if paused:
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                    paused = False
                else:
                    pause_start_ns = time.monotonic_ns()
                    paused = True
            elif event_type == "skip":
                return None
            elif event_type == "answered":
                if paused:
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                return pause_total_ns

    def _rating_step(self) -> Rating:
        while True:
            event = self._await_event()
            if event.get("type") != "rate":
                continue
            rating_name = event.get("rating")
            try:
                return Rating[rating_name]
            except (KeyError, TypeError):
                self._send_notice("Invalid rating", level="error")

    def _await_event(self) -> dict[str, Any]:
        event = self.transport.receive()
        if event is None or event.get("type") == "quit":
            raise KeyboardInterrupt
        return event
