#!/usr/bin/env python3
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from fsrs import Card, Rating, Scheduler
from rich.console import Console
from rich.markdown import Markdown
import util


INDEX_ROW_RE = re.compile(r"^'([^']*)','([^']*)'\s*$")
CLOZE_RE = re.compile(r"~\{(.*?)\}", re.DOTALL)
REVIEW_LOGS_KEY = "review_logs"
MASK_CHAR = "▇"

RATING_BUTTONS = { "n": Rating.Again, "e": Rating.Hard, "i": Rating.Good, "o": Rating.Easy, }

def mask_hidden_text(text: str) -> str:
    return "".join("\n" if ch == "\n" else (" " if ch.isspace() else MASK_CHAR) for ch in text)


def render_note_views(note_text: str) -> Tuple[str, str, List[str]]:
    question_parts: List[str] = []
    answer_parts: List[str] = []
    revealed_parts: List[str] = []
    last_end = 0

    for match in CLOZE_RE.finditer(note_text):
        start, end = match.span()
        hidden = match.group(1)
        revealed_parts.append(hidden)

        question_parts.append(note_text[last_end:start])
        question_parts.append(mask_hidden_text(hidden))

        answer_parts.append(note_text[last_end:start])
        answer_parts.append(hidden)

        last_end = end

    question_parts.append(note_text[last_end:])
    answer_parts.append(note_text[last_end:])
    return "".join(question_parts), "".join(answer_parts), revealed_parts


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
    while True:
        value = input("Rate [n=Again, e=Hard, i=Good, o=Easy]: ").strip()
        if value in RATING_BUTTONS:
            return RATING_BUTTONS[value]
        print("Invalid rating")


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
    console = Console()
    repo_root = util.get_repo_root()
    if not repo_root:
        console.print("Not inside a git repository.")
        return 1

    index_path = os.path.join(repo_root, ".srs", "index.txt")
    if not os.path.exists(index_path):
        console.print("Missing index")
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
        console.print("No due cards.")
        return 0

    for i, (note_id, card_path, card, raw_data, note_path) in enumerate( due_items, start=1):
        os.system("cls" if os.name == "nt" else "clear")

        # Question
        note_text = read_note_text(note_path)
        question_view, answer_view, revealed_parts = render_note_views(note_text)
        question = os.path.basename(note_path)
        console.print(f"\n[{i}/{len(due_items)}] {question}")
        console.print(Markdown(question_view.rstrip("\n")))
        if not revealed_parts:
            console.print("\n(no cloze segments found)")
        question_started_ns = time.monotonic_ns()
        print()
        input()

        # Answer
        review_duration_ms = max(0, (time.monotonic_ns() - question_started_ns) // 1_000_000)
        os.system("cls" if os.name == "nt" else "clear")
        console.print(f"\n[{i}/{len(due_items)}] {question} — answer")
        console.print(Markdown(answer_view.rstrip("\n")))

        # Rating
        print()
        rating = prompt_rating()

        updated_card, review_log = scheduler.review_card( card, rating, review_duration=int(review_duration_ms))
        save_card(card_path, updated_card, raw_data, review_log.to_json())
        console.print("Saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
