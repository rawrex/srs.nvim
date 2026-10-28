import json
import os
import tempfile
import unittest
from datetime import UTC, datetime

from core import util
from core.config import load_review_config
from core.index import Index
from scripts.reschedule_cards import reschedule_entries
from tests.setup_test_helpers import runtime_context

CARD_ID = 1774857617052
OLD_DUE = "2038-06-06T12:53:31.979204+00:00"
REVIEW_LOGS = [
    {"card_id": CARD_ID, "rating": 3, "review_datetime": "2026-03-30T08:25:12.382979+00:00", "review_duration": 3308},
    {"card_id": CARD_ID, "rating": 4, "review_datetime": "2026-03-30T09:35:19.118183+00:00", "review_duration": 3164},
    {"card_id": CARD_ID, "rating": 4, "review_datetime": "2026-04-11T02:58:02.747411+00:00", "review_duration": 13041},
    {"card_id": CARD_ID, "rating": 3, "review_datetime": "2026-10-28T12:53:31.979204+00:00", "review_duration": 2938},
]
BEFORE_OPTIMIZATION = datetime(2026, 10, 7, tzinfo=UTC)


def _write_config(repo_root: str, *, enable_fuzzing: bool = False) -> None:
    payload = {"scheduler": {"desired_retention": 0.8, "enable_fuzzing": enable_fuzzing}}
    with open(os.path.join(repo_root, ".srs", "config.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _write_card(repo_root: str, logs: list[dict[str, object]], *, stability: float | None = 989.4314937336624) -> str:
    payload = {
        "card_id": CARD_ID,
        "difficulty": 1.0,
        "due": OLD_DUE,
        "last_review": OLD_DUE,
        "review_logs": logs,
        "stability": stability,
        "state": 2,
        "step": None,
    }
    path = os.path.join(repo_root, ".srs", f"{CARD_ID}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def _write_index(repo_root: str) -> str:
    path = os.path.join(repo_root, ".srs", "index.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"'{CARD_ID}','/note.md','cloze','21','36','{OLD_DUE}'\n")
    return path


class RescheduleTest(unittest.TestCase):
    def _setup(self) -> tuple[str, str]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_root = temp_dir.name
        os.makedirs(os.path.join(repo_root, ".srs"))
        _write_config(repo_root)
        card_path = _write_card(repo_root, REVIEW_LOGS)
        index_path = _write_index(repo_root)
        util._RUNTIME_CONTEXT = runtime_context(repo_root)
        return card_path, index_path

    def test_reschedule_replays_history_and_rewrites_index(self) -> None:
        card_path, index_path = self._setup()
        index = Index()

        report = reschedule_entries(
            index.get_entries(), load_review_config().build_scheduler(), since=BEFORE_OPTIMIZATION
        )
        index.flush()

        self.assertEqual(1, report.selected)
        self.assertEqual(1, report.rescheduled)
        change = report.changes[0]
        self.assertLess(change.new_due, change.old_due)
        self.assertLess(change.new_stability or 0, change.old_stability or 0)

        with open(card_path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        self.assertEqual(REVIEW_LOGS, stored["review_logs"])
        self.assertEqual(change.new_due.isoformat(), stored["due"])
        self.assertEqual(change.new_stability, stored["stability"])

        with open(index_path, "r", encoding="utf-8") as handle:
            self.assertIn(f"'{change.new_due.isoformat()}'", handle.read())

    def test_dry_run_does_not_write(self) -> None:
        card_path, index_path = self._setup()
        with open(card_path, "r", encoding="utf-8") as handle:
            before_card = handle.read()
        with open(index_path, "r", encoding="utf-8") as handle:
            before_index = handle.read()

        report = reschedule_entries(
            Index().get_entries(), load_review_config().build_scheduler(), since=BEFORE_OPTIMIZATION, dry_run=True
        )

        self.assertEqual(1, report.rescheduled)
        with open(card_path, "r", encoding="utf-8") as handle:
            self.assertEqual(before_card, handle.read())
        with open(index_path, "r", encoding="utf-8") as handle:
            self.assertEqual(before_index, handle.read())

    def test_since_skips_cards_reviewed_before_cutoff(self) -> None:
        card_path, _index_path = self._setup()
        with open(card_path, "r", encoding="utf-8") as handle:
            before_card = handle.read()

        report = reschedule_entries(
            Index().get_entries(), load_review_config().build_scheduler(), since=datetime(2026, 11, 1, tzinfo=UTC)
        )

        self.assertEqual(0, report.selected)
        self.assertEqual(0, report.rescheduled)
        with open(card_path, "r", encoding="utf-8") as handle:
            self.assertEqual(before_card, handle.read())


if __name__ == "__main__":
    unittest.main()
