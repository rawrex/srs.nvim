#!/usr/bin/env python3
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from fsrs import Card, Rating, Scheduler
import util


INDEX_ROW_RE = re.compile(r"^'([^']*)','([^']*)'\s*$")
REVIEW_LOGS_KEY = "review_logs"


def load_index_rows(index_path: str) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    with open(index_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            match = INDEX_ROW_RE.match(line)
            if not match:
                continue
            rows.append((match.group(1), match.group(2)))
    return rows


def load_card(card_path: str) -> Tuple[Card, Dict[str, object]]:
    with open(card_path, "r", encoding="utf-8") as handle:
        raw_text = handle.read()
    raw_data = json.loads(raw_text)
    card = Card.from_json(raw_text)
    return card, raw_data


def note_abs_path(repo_root: str, indexed_path: str) -> str:
    return os.path.join(repo_root, indexed_path.lstrip("/"))


def read_note_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def is_due(card: Card, now: datetime) -> bool:
    due = card.due
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= now


def prompt_rating() -> Rating:
    choices = {
        "1": Rating.Again,
        "2": Rating.Hard,
        "3": Rating.Good,
        "4": Rating.Easy,
    }
    while True:
        value = input("Rate [1=Again, 2=Hard, 3=Good, 4=Easy]: ").strip()
        if value in choices:
            return choices[value]
        print("Invalid rating. Use 1, 2, 3, or 4.")


def save_card(
    card_path: str,
    updated_card: Card,
    raw_data: Dict[str, object],
    review_log_json: str,
) -> None:
    card_data = json.loads(updated_card.to_json())
    merged: Dict[str, object] = dict(raw_data)
    merged.update(card_data)

    logs = merged.get(REVIEW_LOGS_KEY)
    if not isinstance(logs, list):
        logs = []
    logs.append(json.loads(review_log_json))
    merged[REVIEW_LOGS_KEY] = logs

    tmp_path = card_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=4, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, card_path)


def main() -> int:
    repo_root = util.get_repo_root()
    if not repo_root:
        print("Not inside a git repository.")
        return 1

    index_path = os.path.join(repo_root, ".srs", "index.txt")
    if not os.path.exists(index_path):
        print("Missing index")
        return 1

    scheduler = Scheduler()
    now = datetime.now(timezone.utc)
    due_items: List[Tuple[str, str, Card, Dict[str, object], str]] = []

    for note_id, indexed_path in load_index_rows(index_path):
        card_path = os.path.join(repo_root, ".srs", f"{note_id}.json")
        card, raw_data = load_card(card_path)
        if is_due(card, now):
            note_path = note_abs_path(repo_root, indexed_path)
            due_items.append((note_id, card_path, card, raw_data, note_path))

    if not due_items:
        print("No due cards.")
        return 0

    for i, (note_id, card_path, card, raw_data, note_path) in enumerate(due_items, start=1):
        os.system("cls" if os.name == "nt" else "clear")

        # Quesion
        question = os.path.basename(note_path)
        print(f"\n[{i}/{len(due_items)}] {question}")
        question_started_ns = time.monotonic_ns()
        input("Enter to show answer")

        # Answer
        review_duration_ms = max(0, (time.monotonic_ns() - question_started_ns) // 1_000_000)
        note_text = read_note_text(note_path)
        print(note_text.rstrip("\n"))

        # Rating
        rating = prompt_rating()

        updated_card, review_log = scheduler.review_card(card, rating, review_duration=int(review_duration_ms))
        save_card(card_path, updated_card, raw_data, review_log.to_json())
        print("Saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
