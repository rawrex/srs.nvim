import io
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from fsrs import Card as SchedulerCard
from fsrs import Rating

from core.card import CardRef
from core.config import ReviewConfig
from core.protocol import JsonLineTransport
from core.rpc import TransportUI, run
from tests.setup_test_helpers import runtime_context, temporary_session_repo


def _card_ref(index: int = 1, total: int = 1, note: str = "/note.md") -> CardRef:
    return CardRef(index=index, total=total, card_id=7, note_path=note, card_type="cloze", start_line=2, end_line=4)


def _make_ui(events: list[dict[str, object]]) -> tuple[TransportUI, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
    writer = io.StringIO()
    ui = TransportUI(transport=JsonLineTransport(reader, writer))
    return ui, writer


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


class TransportUiTest(unittest.TestCase):
    def test_intro_waits_for_start(self) -> None:
        ui, writer = _make_ui([{"type": "ignored"}, {"type": "start"}])

        ui.intro(2, ["note"])

        self.assertEqual([{"type": "intro", "due": 2, "notes": ["note"]}], _sent(writer))

    def test_card_step_sends_pointer(self) -> None:
        ui, writer = _make_ui([{"type": "answered"}])

        self.assertEqual(0, ui.card_step(_card_ref(index=2, total=5, note="/notes/x.md")))

        self.assertEqual(
            [
                {
                    "type": "card",
                    "card": {
                        "index": 2,
                        "total": 5,
                        "id": 7,
                        "note": "/notes/x.md",
                        "start_line": 2,
                        "end_line": 4,
                        "type": "cloze",
                    },
                }
            ],
            _sent(writer),
        )

    def test_card_step_returns_none_on_skip(self) -> None:
        ui, _writer = _make_ui([{"type": "skip"}])

        self.assertIsNone(ui.card_step(_card_ref()))

    def test_card_step_tracks_pause_time(self) -> None:
        ui, _writer = _make_ui([{"type": "pause"}, {"type": "answered"}])

        with patch("core.rpc.time.monotonic_ns", side_effect=[100, 300]):
            pause_ns = ui.card_step(_card_ref())

        self.assertEqual(200, pause_ns)

    def test_rating_step_maps_rating_name(self) -> None:
        ui, writer = _make_ui([{"type": "rate", "rating": "Hard"}])

        rating = ui.rating_step()

        self.assertEqual(Rating.Hard, rating)
        self.assertEqual([], _sent(writer))

    def test_rating_step_reports_invalid_rating_and_retries(self) -> None:
        ui, writer = _make_ui([{"type": "rate", "rating": "Nope"}, {"type": "rate", "rating": "Easy"}])

        rating = ui.rating_step()

        self.assertEqual(Rating.Easy, rating)
        self.assertIn({"type": "notice", "level": "error", "text": "Invalid rating"}, _sent(writer))

    def test_await_event_interprets_eof_as_interrupt(self) -> None:
        ui, _writer = _make_ui([])

        with self.assertRaises(KeyboardInterrupt):
            ui.rating_step()


class RpcRunTest(unittest.TestCase):
    def test_run_returns_1_outside_git_repo(self) -> None:
        writer = io.StringIO()
        with (
            patch("core.rpc.util.init_runtime_context"),
            patch("core.rpc.util._RUNTIME_CONTEXT", runtime_context(""), create=True),
        ):
            code = run(io.StringIO(), writer)

        self.assertEqual(1, code)
        self.assertEqual({"type": "notice", "level": "error", "text": "Not inside a git repository."}, _sent(writer)[0])

    def test_run_drives_engine_with_rpc_ui(self) -> None:
        engine = Mock()
        engine.run.return_value = 7
        config = ReviewConfig()
        writer = io.StringIO()
        with (
            patch("core.rpc.util.init_runtime_context"),
            patch("core.rpc.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True),
            patch("core.rpc.load_review_config", return_value=config),
            patch("core.rpc.ReviewEngine", return_value=engine) as engine_cls,
        ):
            code = run(io.StringIO(), writer)

        self.assertEqual(7, code)
        engine_cls.assert_called_once()
        self.assertIsInstance(engine_cls.call_args.kwargs["ui"], TransportUI)
        engine.run.assert_called_once_with()

    def test_run_reviews_real_repo_and_persists_review_log(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','2'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(1970, 1, 1, tzinfo=timezone.utc)
            card_path = os.path.join(repo_root, ".srs", "1.json")
            with open(card_path, "w", encoding="utf-8") as handle:
                json.dump(json.loads(scheduler_card.to_json()), handle)

            events = [{"type": "start"}, {"type": "answered"}, {"type": "rate", "rating": "Good"}]
            reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
            writer = io.StringIO()
            with (
                patch("core.rpc.util.init_runtime_context"),
                patch("core.rpc.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
            ):
                code = run(reader, writer)

            with open(card_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        messages = _sent(writer)
        self.assertEqual(0, code)
        self.assertEqual(1, len(stored["review_logs"]))
        self.assertIn({"type": "notice", "level": "info", "text": "Saved"}, messages)
        card_messages = [message for message in messages if message["type"] == "card"]
        self.assertEqual(1, len(card_messages))
        self.assertEqual("/note.md", card_messages[0]["card"]["note"])
        self.assertEqual("cloze", card_messages[0]["card"]["type"])
        self.assertNotIn("segments", card_messages[0])


if __name__ == "__main__":
    unittest.main()
