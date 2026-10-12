"""Newline-delimited JSON transport shared by every SRS UI client.

The backend (:mod:`core.rpc`) drives :class:`core.engine.ReviewEngine` and talks
to a UI client over a pair of text streams. Clients are interchangeable as long
as they speak this protocol: the nvim plugin in ``lua/`` and the terminal UI in
``tui/`` are the current ones.

Server -> client messages
-------------------------
``message``
    ``{"type": "message", "text": str}``
``intro``
    ``{"type": "intro", "total": int, "notes": [str, ...]}``
``render``
    ``{"type": "render", "state": str, "title": str, "note": str,
       "progress": {"current": int, "total": int} | None,
       "active": {"start": int, "end": int},
       "segments": [{"start": int, "end": int, "text": str}, ...]}``
``rating``
    ``{"type": "rating", "suggested": str | None, "buttons": {str: str}}``
``error``
    ``{"type": "error", "text": str}``

Client -> server events
-----------------------
``start``   ``{"name": "start"}``
``pause``   ``{"name": "pause"}``
``next``    ``{"name": "next"}``
``reveal``  ``{"name": "reveal", "label": str}``
``rate``    ``{"name": "rate", "rating": str | None}``
``quit``    ``{"name": "quit"}``

``segments`` carry the note text as-is (one entry per context block, sorted by
line range). The blocks are *not* decorated: a client decides how to render
callouts and the active marker. ``active`` points at the segment that is the
live card view (client may mark it); ``title`` is the orchestration title built
by the engine. Card-level affordances (such as the fixed key that opens a
collapsed block) are handled by the card itself, so clients do not need a
separate field for them.
"""

import json
from typing import IO, Any

MESSAGE = "message"
INTRO = "intro"
RENDER = "render"
RATING = "rating"
ERROR = "error"

EVENT_START = "start"
EVENT_PAUSE = "pause"
EVENT_NEXT = "next"
EVENT_REVEAL = "reveal"
EVENT_RATE = "rate"
EVENT_QUIT = "quit"


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
