#!/usr/bin/env python3
# ruff: noqa: E402
import os
import sys
import time
from pathlib import Path
from typing import IO, Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fsrs import Rating

from core import util
from core.card import CardRef
from core.config import load_review_config
from core.engine import ReviewEngine
from core.protocol import JsonLineTransport


class TransportUI:
    """ReviewUIProtocol implementation that talks JSON over a transport."""

    def __init__(self, transport: JsonLineTransport) -> None:
        self.transport = transport

    def print_message(self, message: str) -> None:
        self.transport.send({"type": "notice", "level": "info", "text": message})

    def intro(self, total: int, note_paths: list[str]) -> None:
        self.transport.send({"type": "intro", "due": total, "notes": note_paths})
        while self._await_event().get("type") != "start":
            continue

    def card_step(self, card_ref: CardRef) -> int | None:
        self.transport.send(
            {
                "type": "card",
                "card": {
                    "index": card_ref.index,
                    "total": card_ref.total,
                    "id": card_ref.card_id,
                    "note": card_ref.note_path,
                    "start_line": card_ref.start_line,
                    "end_line": card_ref.end_line,
                    "type": card_ref.card_type,
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

    def rating_step(self) -> Rating:
        while True:
            event = self._await_event()
            if event.get("type") != "rate":
                continue
            rating_name = event.get("rating")
            try:
                return Rating[rating_name]
            except (KeyError, TypeError):
                self.transport.send({"type": "notice", "level": "error", "text": "Invalid rating"})

    def _await_event(self) -> dict[str, Any]:
        event = self.transport.receive()
        if event is None or event.get("type") == "quit":
            raise KeyboardInterrupt
        return event


def run(reader: IO[str], writer: IO[str]) -> int:
    transport = JsonLineTransport(reader, writer)
    util.init_runtime_context(os.getcwd())
    if not util._RUNTIME_CONTEXT.repo_root_path:
        transport.send({"type": "notice", "level": "error", "text": "Not inside a git repository."})
        return 1

    config = load_review_config()
    engine = ReviewEngine(ui=TransportUI(transport=transport), scheduler=config.build_scheduler())
    return engine.run()


def main() -> int:
    try:
        return run(sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
