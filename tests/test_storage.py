import json
import os
import tempfile
import unittest

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from core.index.storage import REVIEW_LOGS_KEY, Metadata, read_metadata, write_metadata


class StorageTest(unittest.TestCase):
    def test_read_metadata_ignores_non_dict_review_logs(self) -> None:
        scheduler = Scheduler()
        updated_card, review_log = scheduler.review_card(SchedulerCard(), Rating.Good, review_duration=321)
        payload = json.loads(updated_card.to_json())
        payload[REVIEW_LOGS_KEY] = ["bad", 1, review_log.to_dict()]

        metadata = read_metadata(json.dumps(payload))

        self.assertEqual(1, len(metadata.review_logs))
        self.assertEqual(review_log.to_dict(), metadata.review_logs[0].to_dict())

    def test_write_metadata_uses_atomic_replace_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            card_path = os.path.join(temp_dir, "1.json")
            metadata = Metadata(scheduler_card=SchedulerCard(), review_logs=[])

            write_metadata(card_path, metadata)

            self.assertTrue(os.path.exists(card_path))
            self.assertFalse(os.path.exists(card_path + ".tmp"))
            with open(card_path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            self.assertTrue(raw_text.endswith("\n"))

    def test_write_metadata_persists_review_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            card_path = os.path.join(temp_dir, "2.json")
            scheduler = Scheduler()
            updated_card, review_log = scheduler.review_card(SchedulerCard(), Rating.Easy, review_duration=100)
            metadata = Metadata(scheduler_card=updated_card, review_logs=[review_log])

            write_metadata(card_path, metadata)

            with open(card_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertIn(REVIEW_LOGS_KEY, stored)
            self.assertEqual(1, len(stored[REVIEW_LOGS_KEY]))
