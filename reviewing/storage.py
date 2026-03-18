import json
import os
from typing import Dict, List, Tuple

from fsrs import Card as SchedulerCard
from fsrs import ReviewLog


REVIEW_LOGS_KEY = "review_logs"


def parse_storage_json(raw_text: str) -> Tuple[SchedulerCard, List[ReviewLog]]:
    raw_data = json.loads(raw_text)
    scheduler_card = SchedulerCard.from_json(raw_text)
    raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
    review_logs: List[ReviewLog] = []
    if isinstance(raw_review_logs, list):
        for item in raw_review_logs:
            if isinstance(item, dict):
                review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
    return scheduler_card, review_logs


def storage_dict_for_scheduler_card(scheduler_card: SchedulerCard) -> Dict[str, object]:
    return json.loads(scheduler_card.to_json())


def write_storage_file(card_path: str, payload: Dict[str, object]) -> None:
    tmp_path = card_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=4, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, card_path)
