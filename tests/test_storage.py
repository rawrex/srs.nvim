import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from core.index.model import REVIEW_LOGS_KEY, IndexEntry, Metadata
from tests.setup_test_helpers import runtime_context


class StorageTest(unittest.TestCase):
    @staticmethod
    def _entry() -> IndexEntry:
        return IndexEntry(card_id=1, note_path="/note.md", parser_id="cloze", start_line=1, end_line=1)

    def test_read_metadata_ignores_non_dict_review_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scheduler = Scheduler()
            updated_card, review_log = scheduler.review_card(SchedulerCard(), Rating.Good, review_duration=321)
            payload = json.loads(updated_card.to_json())
            payload[REVIEW_LOGS_KEY] = ["bad", 1, review_log.to_dict()]
            entry = self._entry()
            card_path = os.path.join(temp_dir, "1.json")
            with open(card_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                metadata = entry.read_metadata()

            self.assertEqual(1, len(metadata.review_logs))
            self.assertEqual(review_log.to_dict(), metadata.review_logs[0].to_dict())

    def test_write_metadata_uses_atomic_replace_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata = Metadata(scheduler_card=SchedulerCard(), review_logs=[])
            entry = self._entry()
            card_path = os.path.join(temp_dir, "1.json")

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                entry.write_metadata(metadata)

            self.assertTrue(os.path.exists(card_path))
            self.assertFalse(os.path.exists(card_path + ".tmp"))
            with open(card_path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            self.assertTrue(raw_text.endswith("\n"))

    def test_write_metadata_persists_review_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scheduler = Scheduler()
            updated_card, review_log = scheduler.review_card(SchedulerCard(), Rating.Easy, review_duration=100)
            metadata = Metadata(scheduler_card=updated_card, review_logs=[review_log])
            entry = IndexEntry(card_id=2, note_path="/note.md", parser_id="cloze", start_line=1, end_line=1)
            card_path = os.path.join(temp_dir, "2.json")

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(temp_dir, srs_path=temp_dir), create=True):
                entry.write_metadata(metadata)

            with open(card_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertIn(REVIEW_LOGS_KEY, stored)
            self.assertEqual(1, len(stored[REVIEW_LOGS_KEY]))
