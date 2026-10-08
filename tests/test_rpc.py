import io
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fsrs import Card as SchedulerCard
from fsrs import Rating

from core.card import ViewBlock
from core.config import ReviewConfig
from core.rpc import JsonLineTransport, RpcReviewUI, run
from tests.setup_test_helpers import runtime_context, temporary_session_repo


class _FakeCard:
    def __init__(self) -> None:
        self.context: dict[tuple[int, int], str] = {}
        self.index_entry = SimpleNamespace(start_line=1, end_line=1)

    def question_view(self) -> ViewBlock:
        return ViewBlock(start_line=1, text="question")

    def answer_view(self) -> ViewBlock:
        return ViewBlock(start_line=1, text="answer")

    def reveal_for_label(self, label: str) -> ViewBlock | None:
        return ViewBlock(start_line=1, text="revealed") if label == "a" else None


def _make_ui(events: list[dict[str, object]]) -> tuple[RpcReviewUI, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
    writer = io.StringIO()
    ui = RpcReviewUI(config=ReviewConfig(show_context=False), transport=JsonLineTransport(reader, writer))
    return ui, writer


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


class RpcReviewUiTest(unittest.TestCase):
    def test_intro_waits_for_start(self) -> None:
        ui, writer = _make_ui([{"name": "ignored"}, {"name": "start"}])

        ui.intro(2, ["note"])

        self.assertEqual([{"type": "intro", "total": 2, "notes": ["note"]}], _sent(writer))

    def test_question_step_reveals_and_finishes_on_next(self) -> None:
        ui, writer = _make_ui([{"name": "reveal", "label": "a"}, {"name": "next"}])

        view, pause_ns = ui.question_step("title", _FakeCard())

        self.assertEqual("revealed", view.text)
        self.assertEqual(0, pause_ns)
        renders = [message for message in _sent(writer) if message["type"] == "render"]
        self.assertEqual(2, len(renders))
        self.assertEqual("question <|---", renders[0]["view"])
        self.assertEqual("revealed <|---", renders[1]["view"])

    def test_question_step_tracks_pause_time(self) -> None:
        ui, _writer = _make_ui([{"name": "pause"}, {"name": "next"}])

        with patch("core.rpc.time.monotonic_ns", side_effect=[100, 300]):
            _view, pause_ns = ui.question_step("title", _FakeCard())

        self.assertEqual(200, pause_ns)

    def test_rating_step_maps_rating_name(self) -> None:
        ui, writer = _make_ui([{"name": "rate", "rating": "Hard"}])

        rating = ui.rating_step(Rating.Good)

        self.assertEqual(Rating.Hard, rating)
        self.assertEqual("Good", _sent(writer)[0]["suggested"])

    def test_rating_step_accepts_default_when_no_rating_sent(self) -> None:
        ui, _writer = _make_ui([{"name": "rate"}])

        self.assertEqual(Rating.Good, ui.rating_step(Rating.Good))

    def test_rating_step_reports_invalid_rating_and_retries(self) -> None:
        ui, writer = _make_ui([{"name": "rate", "rating": "Nope"}, {"name": "rate", "rating": "Easy"}])

        rating = ui.rating_step(None)

        self.assertEqual(Rating.Easy, rating)
        self.assertIn({"type": "error", "text": "Invalid rating"}, _sent(writer))

    def test_await_event_interprets_eof_as_interrupt(self) -> None:
        ui, _writer = _make_ui([])

        with self.assertRaises(KeyboardInterrupt):
            ui.rating_step(None)


class RpcRunTest(unittest.TestCase):
    def test_run_returns_1_outside_git_repo(self) -> None:
        writer = io.StringIO()
        with (
            patch("core.rpc.util.init_runtime_context"),
            patch("core.rpc.util._RUNTIME_CONTEXT", runtime_context(""), create=True),
        ):
            code = run(io.StringIO(), writer)

        self.assertEqual(1, code)
        self.assertEqual({"type": "error", "text": "Not inside a git repository."}, _sent(writer)[0])

    def test_run_drives_engine_with_rpc_ui(self) -> None:
        engine = Mock()
        engine.run.return_value = 7
        config = ReviewConfig()
        writer = io.StringIO()
        with (
            patch("core.rpc.util.init_runtime_context"),
            patch("core.rpc.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True),
            patch("core.rpc.load_review_config", return_value=config),
            patch("core.rpc.build_parser_registry", return_value=Mock()),
            patch("core.rpc.ReviewEngine", return_value=engine) as engine_cls,
        ):
            code = run(io.StringIO(), writer)

        self.assertEqual(7, code)
        engine_cls.assert_called_once()
        self.assertIsInstance(engine_cls.call_args.kwargs["ui"], RpcReviewUI)
        engine.run.assert_called_once_with()

    def test_run_reviews_real_repo_and_persists_review_log(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            with open(os.path.join(repo_root, "note.md"), "w", encoding="utf-8") as handle:
                handle.write("Prelude line\nTerm ~{hidden}\nTail line\n")
            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','2'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(1970, 1, 1, tzinfo=timezone.utc)
            card_path = os.path.join(repo_root, ".srs", "1.json")
            with open(card_path, "w", encoding="utf-8") as handle:
                json.dump(json.loads(scheduler_card.to_json()), handle)

            events = [
                {"name": "start"},
                {"name": "reveal", "label": ""},
                {"name": "next"},
                {"name": "rate", "rating": "Good"},
            ]
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
        self.assertIn({"type": "message", "text": "Saved"}, messages)
        renders = [message for message in messages if message["type"] == "render"]
        self.assertEqual(["question", "question", "answer"], [render["state"] for render in renders])
        self.assertNotIn("hidden", renders[0]["view"])
        self.assertIn("hidden", renders[1]["view"])


if __name__ == "__main__":
    unittest.main()
