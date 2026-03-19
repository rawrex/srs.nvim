import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

from fsrs import Card as SchedulerCard
from fsrs import ReviewLog


REVIEW_LOGS_KEY = "review_logs"


@dataclass
class Metadata:
    scheduler_card: SchedulerCard
    review_logs: List[ReviewLog] = field(default_factory=list)

    def to_storage_dict(self) -> Dict[str, object]:
        merged = storage_dict_for_scheduler_card(self.scheduler_card)
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in self.review_logs]
        return merged


def parse_storage_json(raw_text: str) -> Metadata:
    raw_data = json.loads(raw_text)
    scheduler_card = SchedulerCard.from_json(raw_text)
    raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
    review_logs: List[ReviewLog] = []
    if isinstance(raw_review_logs, list):
        for item in raw_review_logs:
            if isinstance(item, dict):
                review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
    return Metadata(scheduler_card=scheduler_card, review_logs=review_logs)


def storage_dict_for_scheduler_card(scheduler_card: SchedulerCard) -> Dict[str, object]:
    return json.loads(scheduler_card.to_json())


def write_storage_file(card_path: str, payload: Dict[str, object]) -> None:
    tmp_path = card_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=4, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, card_path)


def write_metadata_file(card_path: str, metadata: Metadata) -> None:
    write_storage_file(card_path, metadata.to_storage_dict())
