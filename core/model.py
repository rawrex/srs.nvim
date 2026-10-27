import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import List

from fsrs import Card as SchedulerCard
from fsrs import ReviewLog

from core import util

REVIEW_LOGS_KEY = "review_logs"


@dataclass(frozen=True)
class DiffChangeSet:
    renames: dict[str, str]
    deletes: set[str]

    @classmethod
    def from_diff_text(cls, diff_text: str) -> "DiffChangeSet":
        renames, deletes = util.parse_diff(diff_text)
        return cls(renames=renames, deletes=deletes)


@dataclass
class Metadata:
    scheduler_card: SchedulerCard
    review_logs: List[ReviewLog] = field(default_factory=list)


class IndexEntry:
    card_id: int
    note_path: str
    card_type: str
    start_line: int
    end_line: int

    def __init__(self, card_id: int, note_path: str, card_type: str, start_line: int, end_line: int) -> None:
        self.card_id = card_id
        self.note_path = note_path
        self.card_type = card_type
        self.start_line = start_line
        self.end_line = end_line
        self._metadata: Metadata | None = None

    @property
    def card_path(self) -> str:
        return os.path.join(util._RUNTIME_CONTEXT.srs_path, f"{self.card_id}.json")

    def read_metadata(self) -> Metadata:
        if self._metadata == None:
            with open(self.card_path, "r", encoding="utf-8") as handle:
                raw_card = handle.read()
                data = json.loads(raw_card)
                raw_review_logs = data.get(REVIEW_LOGS_KEY)
                scheduler_card = SchedulerCard.from_json(raw_card)
                review_logs = [ReviewLog.from_dict(item) for item in raw_review_logs]
                self._metadata = Metadata(scheduler_card=scheduler_card, review_logs=review_logs)
        return self._metadata

    def write_metadata(self, metadata: Metadata) -> None:
        merged = json.loads(metadata.scheduler_card.to_json())
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in metadata.review_logs]
        payload = json.dumps(merged, ensure_ascii=False, indent=4, sort_keys=True)
        util.write_text_atomic(self.card_path, payload + "\n")
        self._metadata = metadata

    def is_due(self, time_point: datetime) -> bool:
        return time_point >= self.read_metadata().scheduler_card.due
