import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from core.entry import REVIEW_LOGS_KEY, IndexEntry, Metadata
from tests.setup_test_helpers import runtime_context


def _entry(card_id: int = 1, metadata: Metadata | None = None) -> IndexEntry:
    return IndexEntry(
        metadata=metadata,
        card_id=card_id,
        note_path="/note.md",
        card_type="cloze",
        start_line=1,
        end_line=1,
        due=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _write_card_file(temp_dir: str, card_id: int, payload: dict[str, object]) -> None:
    card_path = os.path.join(temp_dir, f"{card_id}.json")
    with open(card_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class StorageReadTest(unittest.TestCase):
    def test_read_metadata_ignores_non_dict_review_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scheduler = Scheduler()
            updated_card, review_log = scheduler.review_card(SchedulerCard(), Rating.Good, review_duration=321)
            payload = json.loads(updated_card.to_json())
            payload[REVIEW_LOGS_KEY] = ["bad", 1, review_log.to_dict()]
            _write_card_file(temp_dir, 1, payload)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                metadata = _entry().read_metadata()

            self.assertEqual(1, len(metadata.review_logs))
            self.assertEqual(review_log.to_dict(), metadata.review_logs[0].to_dict())

    def test_read_metadata_defaults_to_empty_without_review_logs_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = json.loads(SchedulerCard().to_json())
            _write_card_file(temp_dir, 1, payload)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                metadata = _entry().read_metadata()

            self.assertEqual([], metadata.review_logs)


class StorageWriteTest(unittest.TestCase):
    def test_update_and_write_persists_review_log_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = _entry(card_id=2, metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                entry.update(Scheduler(), 250, Rating.Easy)
                entry.write()

            card_path = os.path.join(temp_dir, "2.json")
            self.assertFalse(os.path.exists(card_path + ".tmp"))
            with open(card_path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            self.assertTrue(raw_text.endswith("\n"))

            stored = json.loads(raw_text)
            self.assertIn(REVIEW_LOGS_KEY, stored)
            self.assertEqual(1, len(stored[REVIEW_LOGS_KEY]))
            self.assertEqual(250, stored[REVIEW_LOGS_KEY][0]["review_duration"])

    def test_write_survives_a_later_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = _entry(card_id=3, metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                entry.update(Scheduler(), 100, Rating.Good)
                entry.write()
                reloaded = _entry(card_id=3).read_metadata()

            self.assertEqual(entry.metadata.scheduler_card.to_json(), reloaded.scheduler_card.to_json())
            self.assertEqual(1, len(reloaded.review_logs))
