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


def read_metadata(raw_text: str) -> Metadata:
    raw_data = json.loads(raw_text)
    scheduler_card = SchedulerCard.from_json(raw_text)
    raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
    review_logs: List[ReviewLog] = []
    if isinstance(raw_review_logs, list):
        for item in raw_review_logs:
            if isinstance(item, dict):
                review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
    return Metadata(scheduler_card=scheduler_card, review_logs=review_logs)


def write_metadata(card_path: str, metadata: Metadata) -> None:
    merged = json.loads(metadata.scheduler_card.to_json())
    merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in metadata.review_logs]
    tmp_path = card_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=4, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, card_path)
