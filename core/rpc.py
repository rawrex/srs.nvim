#!/usr/bin/env python3
# ruff: noqa: E402
import json
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
from core.card import Card, ViewBlock
from core.config import ReviewConfig, load_review_config
from core.engine import ReviewEngine
from core.parsers import build_parser_registry
from core.ui import compose_view_text


class JsonLineTransport:
    """Newline-delimited JSON over a pair of text streams (stdout/stdin)."""

    def __init__(self, reader: IO[str], writer: IO[str]) -> None:
        self._reader = reader
        self._writer = writer

    def send(self, message: dict[str, Any]) -> None:
        self._writer.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._writer.flush()

    def receive(self) -> dict[str, Any] | None:
        for line in self._reader:
            if line.strip():
                return json.loads(line)
        return None


class RpcReviewUI:
    """ReviewUIProtocol implementation that renders/awaits events over a transport."""

    def __init__(self, config: ReviewConfig, transport: JsonLineTransport) -> None:
        self.config = config
        self.transport = transport
        self.rating_buttons = config.rating_buttons

    def print_message(self, message: str) -> None:
        self.transport.send({"type": "message", "text": message})

    def intro(self, total: int, note_paths: list[str]) -> None:
        self.transport.send({"type": "intro", "total": total, "notes": note_paths})
        while self._await_event().get("name") != "start":
            continue

    def question_step(self, title: str, card: Card) -> tuple[ViewBlock, int]:
        view: ViewBlock = card.question_view()
        paused: bool = False
        pause_total_ns: int = 0
        pause_start_ns: int = 0
        while True:
            self._send_render("question", title, card, view, paused=paused)
            event: dict[str, Any] = self._await_event()
            name = event.get("name")
            if name == "pause":
                if paused:  # resume
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                    paused = False
                else:  # pause
                    pause_start_ns = time.monotonic_ns()
                    paused = True
            elif name == "next":
                if paused:
                    pause_total_ns += time.monotonic_ns() - pause_start_ns
                return view, pause_total_ns
            elif name == "reveal":
                revealed = card.reveal_for_label(event.get("label", ""))
                if revealed is not None:
                    view = revealed

    def answer_step(self, title: str, card: Card, view: ViewBlock) -> None:
        self._send_render("answer", title, card, view)

    def rating_step(self, default_rating: Rating | None) -> Rating:
        self.transport.send(
            {
                "type": "rating",
                "suggested": default_rating.name if default_rating is not None else None,
                "buttons": {rating.name: button for rating, button in self.rating_buttons.items()},
            }
        )
        while True:
            event = self._await_event()
            if event.get("name") != "rate":
                continue
            rating_name = event.get("rating")
            if rating_name is None:
                if default_rating is not None:
                    return default_rating
                self.transport.send({"type": "error", "text": "Invalid rating"})
                continue
            try:
                return Rating[rating_name]
            except KeyError:
                self.transport.send({"type": "error", "text": "Invalid rating"})

    def _send_render(self, state: str, title: str, card: Card, view: ViewBlock, paused: bool = False) -> None:
        self.transport.send(
            {
                "type": "render",
                "state": state,
                "title": f"{title} (PAUSED)" if paused else title,
                "view": compose_view_text(card, view, self.config.show_context),
                "start_line": view.start_line,
            }
        )

    def _await_event(self) -> dict[str, Any]:
        event = self.transport.receive()
        if event is None or event.get("name") == "quit":
            raise KeyboardInterrupt
        return event


def run(reader: IO[str], writer: IO[str]) -> int:
    transport = JsonLineTransport(reader, writer)
    util.init_runtime_context(os.getcwd())
    if not util._RUNTIME_CONTEXT.repo_root_path:
        transport.send({"type": "error", "text": "Not inside a git repository."})
        return 1

    config = load_review_config()
    engine = ReviewEngine(
        ui=RpcReviewUI(config=config, transport=transport),
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
