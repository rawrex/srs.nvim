"""Newline-delimited JSON transport between the backend and the nvim client.

The backend only sends pointers: which note, which span, which card type. The
client opens the real note and derives the presentation from its contents.

Server -> client messages
-------------------------
``intro``
    ``{"type": "intro", "due": int, "notes": [str, ...],
       "cloze": {"open": str, "close": str}}``
``card``
    ``{"type": "card", "card": {"index": int, "total": int, "id": int,
       "note": str, "start_line": int, "end_line": int, "type": str}}``
    ``note`` is the repo-relative path (leading ``/``); ``start_line`` and
    ``end_line`` are 1-based and inclusive.
``notice``
    ``{"type": "notice", "level": "info" | "error", "text": str}``

Client -> server events
-----------------------
``start``     ``{"type": "start"}``
``answered``  ``{"type": "answered"}``  # user revealed; stop the timer
``pause``     ``{"type": "pause"}``
``skip``      ``{"type": "skip"}``
``rate``      ``{"type": "rate", "rating": str}``
``quit``      ``{"type": "quit"}``
"""

import json
from typing import IO, Any

# Server -> client message types.
INTRO = "intro"
CARD = "card"
NOTICE = "notice"

# Client -> server event types.
EVENT_START = "start"
EVENT_ANSWERED = "answered"
EVENT_PAUSE = "pause"
EVENT_SKIP = "skip"
EVENT_RATE = "rate"
EVENT_QUIT = "quit"

# ``notice`` severity levels.
LEVEL_INFO = "info"
LEVEL_ERROR = "error"


class JsonLineTransport:
    """Newline-delimited JSON over a pair of text streams (stdout/stdin)."""

    def __init__(self, reader: IO[str], writer: IO[str]) -> None:
        self._reader = reader
        self._writer = writer

    def send(self, message: dict[str, Any]) -> None:
        self._writer.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._writer.flush()

    def receive(self) -> dict[str, Any] | None:
        while True:
            line = self._reader.readline()
            if line == "":
                return None
            if line.strip():
                return json.loads(line)
