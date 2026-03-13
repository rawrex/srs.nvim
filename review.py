#!/usr/bin/env python3
import json
import os
import re
import signal
import string
import sys
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
LABEL_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation

RATING_BUTTONS: Dict[Rating, str] = {
    Rating.Again: "n",
    Rating.Hard: "e",
    Rating.Good: "i",
    Rating.Easy: "o",
}

BUTTON_TO_RATING_BYTE: Dict[str, bytes] = {
    button: bytes([rating.value]) for rating, button in RATING_BUTTONS.items()
}


def mask_hidden_text(text: str) -> str:
    return "".join("\n" if ch == "\n" else MASK_CHAR for ch in text)


def parse_note_clozes(note_text: str) -> Tuple[List[str], List[str]]:
    text_parts: List[str] = []
    clozes: List[str] = []
    last_end = 0

    for match in CLOZE_RE.finditer(note_text):
        start, end = match.span()
        hidden = match.group(1)
        text_parts.append(note_text[last_end:start])
        clozes.append(hidden)

        last_end = end

    text_parts.append(note_text[last_end:])
    return text_parts, clozes


def build_question_view(
    text_parts: List[str],
    clozes: List[str],
    labels: List[str],
    revealed: List[bool],
) -> str:
    parts: List[str] = [text_parts[0]]
    for idx, hidden in enumerate(clozes):
        if revealed[idx]:
            parts.append(f"`{hidden}`")
        else:
            parts.append(f"[{labels[idx]}]{mask_hidden_text(hidden)}")
        parts.append(text_parts[idx + 1])
    return "".join(parts)


def build_answer_view(text_parts: List[str], clozes: List[str]) -> str:
    parts: List[str] = [text_parts[0]]
    for idx, hidden in enumerate(clozes):
        parts.append(hidden)
        parts.append(text_parts[idx + 1])
    return "".join(parts)


def prompt_cloze_reveal(console: Console, title: str, note_text: str) -> str:
    text_parts, clozes = parse_note_clozes(note_text)
    labels = [LABEL_CHARS[idx] for idx in range(len(clozes))]
    label_to_index = {label: idx for idx, label in enumerate(labels)}
    revealed = [False] * len(clozes)

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        console.print(title)
        console.print(
            Markdown(
                build_question_view(text_parts, clozes, labels, revealed).rstrip("\n")
            )
        )

        key = read_single_key().lower()
        if maybe_suspend_for_key(key):
            continue
        if key in {"\r", "\n"}:
            return build_answer_view(text_parts, clozes)

        idx = label_to_index.get(key)
        if idx is not None and not revealed[idx]:
            revealed[idx] = True


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


def read_single_key() -> str:
    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            if key == "\x03":
                raise KeyboardInterrupt
            return key

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x03":
            raise KeyboardInterrupt
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def maybe_suspend_for_key(key: str) -> bool:
    if key != "\x1a":
        return False
    if hasattr(signal, "SIGTSTP"):
        os.kill(os.getpid(), signal.SIGTSTP)
    return True


def prompt_rating() -> Rating:
    prompt = "Rate [n=Again, e=Hard, i=Good, o=Easy]: "
    while True:
        print(prompt, end="", flush=True)
        key = read_single_key().lower()
        if maybe_suspend_for_key(key):
            print()
            continue
        try:
            rating = Rating.from_bytes(BUTTON_TO_RATING_BYTE[key])
        except (KeyError, ValueError):
            print()
            print("Invalid rating")
            continue

        print()
        print(f"Set rating: {rating.name}")
        time.sleep(0.5)
        return rating


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
    try:
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

        for i, (note_id, card_path, card, raw_data, note_path) in enumerate(
            due_items, start=1
        ):
            note_text = read_note_text(note_path)
            note_filename = os.path.basename(note_path)
            title = f"\n[{i}/{len(due_items)}] {note_filename}"
            question_started_ns = time.monotonic_ns()
            answer_view = prompt_cloze_reveal(console, title, note_text)

            # Answer
            review_duration_ms = max(
                0, (time.monotonic_ns() - question_started_ns) // 1_000_000
            )
            os.system("cls" if os.name == "nt" else "clear")
            console.print(f"\n[{i}/{len(due_items)}] {note_filename} — answer")
            console.print(Markdown(answer_view.rstrip("\n")))

            # Rating
            print()
            rating = prompt_rating()

            updated_card, review_log = scheduler.review_card(
                card, rating, review_duration=int(review_duration_ms)
            )
            save_card(card_path, updated_card, raw_data, review_log.to_json())
            console.print("Saved")
        return 0
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
