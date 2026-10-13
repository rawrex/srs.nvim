"""Newline-delimited JSON transport shared by every SRS UI client.

The backend (:mod:`core.rpc`) drives :class:`core.engine.ReviewEngine` and talks
to a UI client over a pair of text streams. Clients are interchangeable as long
as they speak this protocol: the nvim plugin in ``lua/`` and the terminal UI in
``tui/`` are the current ones.

Every message carries a ``type`` discriminator in both directions. The server
only sends orchestration data; formatting (headings, prompts, buffer names) is
the client's job.

Server -> client messages
-------------------------
``intro``
    ``{"type": "intro", "due": int, "notes": [str, ...], "media": str | None}``
    ``due`` is the number of due cards; ``notes`` is the sorted set of unique
    source note paths (repo-relative, leading ``/``) those cards come from.
    More than one card may share a note. ``media`` is the absolute path of the
    directory holding note images (from config), or ``null`` when unset; clients
    that render images use it to resolve ``![[...]]`` references.
``render``
    ``{"type": "render", "state": "question" | "answer",
       "card": {"index": int, "total": int, "note": str},
       "active": {"start": int, "end": int},
       "segments": [{"start": int, "end": int, "text": str}, ...],
       "duration_s": float}``
    ``card.index``/``card.total`` are the card's 1-based position and the
    session's due-card count; ``card.note`` is the repo-relative source path.
    ``duration_s`` (answer step only) is the elapsed question time in seconds.
``rating``
    ``{"type": "rating", "suggested": str | None,
       "choices": [{"name": str, "key": str}, ...]}``
    ``choices`` is ordered (Again, Hard, Good, Easy).
``notice``
    ``{"type": "notice", "level": "info" | "error", "text": str}``

Client -> server events
-----------------------
``start``   ``{"type": "start"}``
``pause``   ``{"type": "pause"}``
``next``    ``{"type": "next"}``
``reveal``  ``{"type": "reveal", "label": str}``
``rate``    ``{"type": "rate", "rating": str | None}``
``quit``    ``{"type": "quit"}``

``segments`` carry the note text as-is (one entry per context block, sorted by
line range). The blocks are *not* decorated: a client decides how to render
callouts and the active marker. ``active`` points at the segment that is the
live card view (client may mark it). Card-level affordances (such as the fixed
key that opens a collapsed block) are handled by the card itself, so clients do
not need a separate field for them.
"""

import json
from typing import IO, Any

# Server -> client message types.
INTRO = "intro"
RENDER = "render"
RATING = "rating"
NOTICE = "notice"

# Client -> server event types.
EVENT_START = "start"
EVENT_PAUSE = "pause"
EVENT_NEXT = "next"
EVENT_REVEAL = "reveal"
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
