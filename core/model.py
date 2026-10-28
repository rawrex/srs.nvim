import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from fsrs import Card as SchedulerCard
from fsrs import Rating, ReviewLog, Scheduler

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
    review_logs: list[ReviewLog] = field(default_factory=list)


class IndexEntry:
    card_id: int
    note_path: str
    card_type: str
    start_line: int
    end_line: int
    due: datetime

    def __init__(
        self,
        metadata: Metadata | None,
        card_id: int,
        note_path: str,
        card_type: str,
        start_line: int,
        end_line: int,
        due: datetime,
    ) -> None:
        self.metadata: Metadata | None = metadata
        self.card_id = card_id
        self.note_path = note_path
        self.card_type = card_type
        self.start_line = start_line
        self.end_line = end_line
        self.due = due

    @property
    def card_path(self) -> str:
        return os.path.join(util._RUNTIME_CONTEXT.srs_path, f"{self.card_id}.json")

    def read_metadata(self) -> Metadata:
        if self.metadata == None:
            with open(self.card_path, "r", encoding="utf-8") as handle:
                raw_card = handle.read()
                data = json.loads(raw_card)
                raw_review_logs = data.get(REVIEW_LOGS_KEY)
                scheduler_card = SchedulerCard.from_json(raw_card)
                review_logs: list[ReviewLog] = []
                if isinstance(raw_review_logs, list):
                    review_logs = [ReviewLog.from_dict(item) for item in raw_review_logs if isinstance(item, dict)]
                self.metadata = Metadata(scheduler_card=scheduler_card, review_logs=review_logs)
        return self.metadata

    def update(self, scheduler: Scheduler, duration_ms: int, rating: Rating) -> None:
        data = self.read_metadata()
        updated, review_log = scheduler.review_card(data.scheduler_card, rating, review_duration=duration_ms)
        self.due = updated.due
        data.scheduler_card = updated
        data.review_logs.append(review_log)

    def write(self) -> None:
        data = self.read_metadata()
        merged = json.loads(data.scheduler_card.to_json())
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in data.review_logs]
        payload = json.dumps(merged, ensure_ascii=False, indent=4, sort_keys=True)
        util.write_text_atomic(self.card_path, payload + "\n")

    def format(self) -> str:
        return f"'{self.card_id}','{self.note_path}','{self.card_type}','{self.start_line}','{self.end_line}','{self.due.isoformat()}'\n"

    def is_due(self, time_point: datetime) -> bool:
        return time_point >= self.due
