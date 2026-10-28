import io
import json
import os
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from fsrs import Card as SchedulerCard
from fsrs import Scheduler

from core.config import ReviewConfig
from core.protocol import JsonLineTransport
from core.rpc import run
from tests.setup_test_helpers import runtime_context, temporary_session_repo


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


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

    def test_run_drives_engine_with_transport(self) -> None:
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
        self.assertIsInstance(engine_cls.call_args.kwargs["transport"], JsonLineTransport)
        self.assertIsInstance(engine_cls.call_args.kwargs["scheduler"], Scheduler)
        engine.run.assert_called_once_with()

    def test_run_reviews_real_repo_and_persists_review_log(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','2','1970-01-01T00:00:00+00:00'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(1970, 1, 1, tzinfo=UTC)
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
