import io
import json
import unittest
from unittest.mock import patch

from core.protocol import JsonLineTransport
from tui import ReviewRenderer, TuiClient
from tests.setup_test_helpers import FakeConsole


def _render(
    state: str = "question",
    text: str = "question",
    active: tuple[int, int] = (1, 1),
    note: str = "/repo/note.md",
    duration_s: float | None = None,
) -> dict:
    message = {
        "type": "render",
        "state": state,
        "card": {"index": 1, "total": 1, "note": note},
        "active": {"start": active[0], "end": active[1]},
        "segments": [{"start": active[0], "end": active[1], "text": text}],
    }
    if duration_s is not None:
        message["duration_s"] = duration_s
    return message


def _choices() -> list[dict]:
    return [
        {"name": "Again", "key": "n"},
        {"name": "Hard", "key": "e"},
        {"name": "Good", "key": "i"},
        {"name": "Easy", "key": "o"},
    ]


def _make_client(messages: list[dict]) -> tuple[TuiClient, FakeConsole, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    writer = io.StringIO()
    console = FakeConsole()
    renderer = ReviewRenderer(console, show_context=False, media=None)  # type: ignore[arg-type]
    return TuiClient(JsonLineTransport(reader, writer), renderer), console, writer


def _events(writer: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


def _printed_strings(console: FakeConsole) -> list[str]:
    return [value for value, _kwargs in console.printed if isinstance(value, str)]


class TuiClientTest(unittest.TestCase):
    def test_intro_sends_start_on_enter(self) -> None:
        client, _console, writer = _make_client([{"type": "intro", "due": 2, "notes": ["n"]}])

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", return_value="\n"):
            code = client.run()

        self.assertEqual(0, code)
        self.assertEqual([{"type": "start"}], _events(writer))

    def test_question_reveal_then_next(self) -> None:
        client, _console, writer = _make_client([_render(), _render(text="revealed"), _render(state="answer")])

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", side_effect=["a", "\n"]):
            client.run()

        self.assertEqual([{"type": "reveal", "label": "a"}, {"type": "next"}], _events(writer))

    def test_question_escape_skips(self) -> None:
        client, _console, writer = _make_client([_render()])

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", return_value="\x1b"):
            client.run()

        self.assertEqual([{"type": "skip"}], _events(writer))

    def test_question_space_pauses_and_marks_title(self) -> None:
        client, console, writer = _make_client([_render(), _render()])

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", side_effect=[" ", "\n"]):
            client.run()

        self.assertEqual([{"type": "pause"}, {"type": "next"}], _events(writer))
        self.assertIn("[1/1] note.md (PAUSED)", _printed_strings(console))

    def test_rating_default_accepts_enter(self) -> None:
        message = {"type": "rating", "suggested": "Good", "choices": _choices()}
        client, console, writer = _make_client([message])

        with patch("tui.read_single_key", return_value="\n"):
            client.run()

        self.assertEqual([{"type": "rate", "rating": "Good"}], _events(writer))
        self.assertIn(("Set rating: Good", {}), console.printed)

    def test_rating_keeps_enter_invalid_without_suggestion(self) -> None:
        message = {"type": "rating", "suggested": None, "choices": _choices()}
        client, console, writer = _make_client([message])

        with patch("tui.read_single_key", side_effect=["\n", "i"]):
            client.run()

        self.assertEqual([{"type": "rate", "rating": "Good"}], _events(writer))
        self.assertIn(("Invalid rating", {}), console.printed)

    def test_eof_returns_zero(self) -> None:
        client, _console, _writer = _make_client([])

        self.assertEqual(0, client.run())


if __name__ == "__main__":
    unittest.main()
