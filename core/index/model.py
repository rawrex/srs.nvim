import json
import os
from dataclasses import dataclass, field
from typing import List

from fsrs import Card as SchedulerCard
from fsrs import ReviewLog

from core import util

REVIEW_LOGS_KEY = "review_logs"


@dataclass(frozen=True)
class DiffChangeSet:
    renames: dict[str, str]
    deletes: set[str]
    adds: set[str]

    @classmethod
    def from_diff_text(cls, diff_text: str) -> "DiffChangeSet":
        renames, deletes, adds = util.parse_diff(diff_text)
        return cls(renames=renames, deletes=deletes, adds=adds)

    def has_changes(self) -> bool:
        return bool(self.renames or self.deletes or self.adds)


@dataclass(frozen=True)
class IndexUpdateResult:
    lines: list[str]
    changed: bool
    touched_paths: set[str]


@dataclass
class Metadata:
    scheduler_card: SchedulerCard
    review_logs: List[ReviewLog] = field(default_factory=list)


class IndexEntry:
    card_id: int
    note_path: str
    parser_id: str
    start_line: int
    end_line: int

    def __init__(self, card_id: int, note_path: str, parser_id: str, start_line: int, end_line: int) -> None:
        self.card_id = card_id
        self.note_path = note_path
        self.parser_id = parser_id
        self.start_line = start_line
        self.end_line = end_line

    @property
    def card_path(self) -> str:
        return os.path.join(util._RUNTIME_CONTEXT.srs_path, f"{self.card_id}.json")

    @property
    def note_abs_path(self) -> str:
        return os.path.join(util._RUNTIME_CONTEXT.repo_root_path, self.note_path.lstrip("/"))

    def read_metadata(self) -> Metadata:
        with open(self.card_path, "r", encoding="utf-8") as handle:
            raw_card_text = handle.read()
            data = json.loads(raw_card_text)
            raw_review_logs = data.get(REVIEW_LOGS_KEY)
            scheduler_card = SchedulerCard.from_json(raw_card_text)
            review_logs: List[ReviewLog] = []
            if isinstance(raw_review_logs, list):
                for item in raw_review_logs:
                    if isinstance(item, dict):
                        review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
            return Metadata(scheduler_card=scheduler_card, review_logs=review_logs)

    def write_metadata(self, metadata: Metadata) -> None:
        merged = json.loads(metadata.scheduler_card.to_json())
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in metadata.review_logs]
        tmp_path = self.card_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=4, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, self.card_path)
