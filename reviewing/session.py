import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from fsrs import ReviewLog, Scheduler

from hooks_runtime.index import Index, split_note_into_cards

from .card import Card, RevealMode, SchedulerCard
from .ui import ReviewUI


REVIEW_LOGS_KEY = "review_logs"


class ReviewSession:
    def __init__(
        self,
        repo_root: str,
        ui: ReviewUI,
        reveal_mode: RevealMode,
        cloze_open: str,
        cloze_close: str,
        mask_char: str,
        between_notes_timeout_ms: int,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.reveal_mode = RevealMode(reveal_mode)
        self.cloze_open = cloze_open
        self.cloze_close = cloze_close
        self.mask_char = mask_char
        self.between_notes_timeout_ms = between_notes_timeout_ms
        self.scheduler = scheduler or Scheduler()
        self.index_path = os.path.join(repo_root, ".srs", "index.txt")

    def run(self) -> int:
        if not os.path.exists(self.index_path):
            self.ui.print_message("Missing index")
            return 1

        cards = self._load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        for idx, card in enumerate(cards, start=1):
            title = f"\n[{idx}/{total}] {card.note_filename}"
            question_started_ns = time.monotonic_ns()
            self.ui.prompt_cloze_reveal(title, card)

            review_duration_ms = max(
                0, (time.monotonic_ns() - question_started_ns) // 1_000_000
            )
            self.ui.show_answer(
                f"\n[{idx}/{total}] {card.note_filename} — answer",
                card.answer_view(),
            )

            print()
            rating = self.ui.prompt_rating()
            updated_card, review_log = self.scheduler.review_card(
                card.scheduler_card,
                rating,
                review_duration=int(review_duration_ms),
            )
            card.scheduler_card = updated_card
            card.review_logs.append(review_log)
            self._save_reviewed_card(card)
            self.ui.print_message("Saved")
            if idx < total and self.between_notes_timeout_ms > 0:
                time.sleep(self.between_notes_timeout_ms / 1000)

        return 0

    def _load_due_cards(self) -> List[Card]:
        now = datetime.now(timezone.utc)
        cards: List[Card] = []
        note_blocks_cache: Dict[str, Dict[int, str]] = {}
        index = Index(self.index_path)
        for note_id, indexed_path, start_line in index.read_rows():
            card_path = os.path.join(self.repo_root, ".srs", f"{note_id}.json")
            scheduler_card, review_logs = self._load_scheduler_card(card_path)
            if not self._is_due(scheduler_card, now):
                continue
            note_path = self._note_abs_path(indexed_path)
            if note_path not in note_blocks_cache:
                note_blocks_cache[note_path] = self._read_note_blocks(note_path)
            note_text = note_blocks_cache[note_path].get(start_line)
            if note_text is None:
                continue
            cards.append(
                Card(
                    note_id=note_id,
                    note_path=note_path,
                    card_path=card_path,
                    note_text=note_text,
                    scheduler_card=scheduler_card,
                    review_logs=review_logs,
                    reveal_mode=self.reveal_mode,
                    cloze_open=self.cloze_open,
                    cloze_close=self.cloze_close,
                    mask_char=self.mask_char,
                )
            )
        return cards

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self.repo_root, indexed_path.lstrip("/"))

    def _read_note_blocks(self, path: str) -> Dict[int, str]:
        with open(path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
        return {
            line_number: block
            for line_number, block in split_note_into_cards(note_text)
        }

    def _load_scheduler_card(
        self, card_path: str
    ) -> Tuple[SchedulerCard, List[ReviewLog]]:
        with open(card_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
        raw_data = json.loads(raw_text)
        scheduler_card = SchedulerCard.from_json(raw_text)
        raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
        review_logs: List[ReviewLog] = []
        if isinstance(raw_review_logs, list):
            for item in raw_review_logs:
                if isinstance(item, dict):
                    review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
        return scheduler_card, review_logs

    def _is_due(self, card: SchedulerCard, now: datetime) -> bool:
        due = card.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= now

    def _save_reviewed_card(self, card: Card) -> None:
        merged: Dict[str, object] = json.loads(card.scheduler_card.to_json())
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in card.review_logs]

        tmp_path = card.card_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=4, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, card.card_path)
