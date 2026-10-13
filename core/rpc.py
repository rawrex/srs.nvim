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
from core.card import Card, CardRef, ViewBlock
from core.config import ReviewConfig, load_review_config
from core.engine import ReviewEngine
from core.parsers import build_parser_registry
from core.protocol import JsonLineTransport


class TransportUI:
    """ReviewUIProtocol implementation that renders/awaits events over a transport."""

    def __init__(self, config: ReviewConfig, transport: JsonLineTransport) -> None:
        self.config = config
        self.transport = transport
        self.rating_buttons = config.rating_buttons

    def print_message(self, message: str) -> None:
        self.transport.send({"type": "notice", "level": "info", "text": message})

    def intro(self, total: int, note_paths: list[str]) -> None:
        self.transport.send({"type": "intro", "due": total, "notes": note_paths, "media": self.config.media})
        while self._await_event().get("type") != "start":
            continue

    def question_step(self, card_ref: CardRef, card: Card) -> tuple[ViewBlock, int] | None:
        view: ViewBlock = card.question_view()
        paused: bool = False
        pause_total_ns: int = 0
        pause_start_ns: int = 0
        while True:
            self._send_render("question", card_ref, card, view)
            event: dict[str, Any] = self._await_event()
            event_type = event.get("type")
            if event_type == "pause":
                if paused:  # resume
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                    paused = False
                else:  # pause
                    pause_start_ns = time.monotonic_ns()
                    paused = True
            elif event_type == "skip":
                return None
            elif event_type == "next":
                if paused:
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                return view, pause_total_ns
            elif event_type == "reveal":
                revealed = card.reveal_for_label(event.get("label", ""))
                if revealed is not None:
                    view = revealed

    def answer_step(self, card_ref: CardRef, card: Card, view: ViewBlock, duration_s: float) -> None:
        self._send_render("answer", card_ref, card, view, duration_s)

    def rating_step(self, default_rating: Rating | None) -> Rating:
        self.transport.send(
            {
                "type": "rating",
                "suggested": default_rating.name if default_rating is not None else None,
                "choices": [
                    {"name": rating.name, "key": self.rating_buttons[rating]}
                    for rating in Rating
                    if rating in self.rating_buttons
                ],
            }
        )
        while True:
            event = self._await_event()
            if event.get("type") != "rate":
                continue
            rating_name = event.get("rating")
            if rating_name is None:
                if default_rating is not None:
                    return default_rating
                self.transport.send({"type": "notice", "level": "error", "text": "Invalid rating"})
                continue
            try:
                return Rating[rating_name]
            except KeyError:
                self.transport.send({"type": "notice", "level": "error", "text": "Invalid rating"})

    def _send_render(
        self, state: str, card_ref: CardRef, card: Card, view: ViewBlock, duration_s: float | None = None
    ) -> None:
        start, end = card.index_entry.start_line, card.index_entry.end_line
        segments = [
            {"start": r0, "end": r1, "text": view.text if (r0, r1) == (start, end) else text}
            for (r0, r1), text in sorted(card.context.items())
        ] or [{"start": start, "end": end, "text": view.text}]
        message: dict[str, Any] = {
            "type": "render",
            "state": state,
            "card": {"index": card_ref.index, "total": card_ref.total, "note": card_ref.note_path},
            "active": {"start": start, "end": end},
            "segments": segments,
        }
        if duration_s is not None:
            message["duration_s"] = duration_s
        self.transport.send(message)

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
    engine = ReviewEngine(
        ui=TransportUI(config=config, transport=transport),
        parser_registry=build_parser_registry(config),
        scheduler=config.build_scheduler(),
    )
    return engine.run()


def main() -> int:
    try:
        return run(sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
