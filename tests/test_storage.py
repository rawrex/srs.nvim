import json
import os
import tempfile
import unittest

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from reviewing.storage import (
    REVIEW_LOGS_KEY,
    Metadata,
    parse_storage_json,
    storage_dict_for_scheduler_card,
    write_metadata_file,
    write_storage_file,
)


class StorageTest(unittest.TestCase):
    def test_parse_storage_json_ignores_non_dict_review_logs(self) -> None:
        scheduler = Scheduler()
        updated_card, review_log = scheduler.review_card(
            SchedulerCard(),
            Rating.Good,
            review_duration=321,
        )
        payload = storage_dict_for_scheduler_card(updated_card)
        payload[REVIEW_LOGS_KEY] = ["bad", 1, review_log.to_dict()]

        metadata = parse_storage_json(json.dumps(payload))

        self.assertEqual(1, len(metadata.review_logs))
        self.assertEqual(review_log.to_dict(), metadata.review_logs[0].to_dict())

    def test_write_storage_file_uses_atomic_replace_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            card_path = os.path.join(temp_dir, "1.json")

            write_storage_file(card_path, {"b": 2, "a": 1})

            self.assertTrue(os.path.exists(card_path))
            self.assertFalse(os.path.exists(card_path + ".tmp"))
            with open(card_path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            self.assertTrue(raw_text.endswith("\n"))
            self.assertEqual({"a": 1, "b": 2}, json.loads(raw_text))

    def test_write_metadata_file_persists_review_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            card_path = os.path.join(temp_dir, "2.json")
            scheduler = Scheduler()
            updated_card, review_log = scheduler.review_card(
                SchedulerCard(),
                Rating.Easy,
                review_duration=100,
            )
            metadata = Metadata(
                scheduler_card=updated_card,
                review_logs=[review_log],
            )

            write_metadata_file(card_path, metadata)

            with open(card_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertIn(REVIEW_LOGS_KEY, stored)
            self.assertEqual(1, len(stored[REVIEW_LOGS_KEY]))


if __name__ == "__main__":
    unittest.main()
