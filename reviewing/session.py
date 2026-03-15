import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from fsrs import Card as FsrsCard
from fsrs import ReviewLog, Scheduler

from hooks_runtime.index import Index

from .card import RevealMode, ReviewCard
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
        scheduler: Scheduler | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.reveal_mode = RevealMode(reveal_mode)
        self.cloze_open = cloze_open
        self.cloze_close = cloze_close
        self.mask_char = mask_char
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
                card.fsrs_card,
                rating,
                review_duration=int(review_duration_ms),
            )
            card.fsrs_card = updated_card
            card.review_logs.append(review_log)
            self._save_reviewed_card(card)
            self.ui.print_message("Saved")

        return 0

    def _load_due_cards(self) -> List[ReviewCard]:
        now = datetime.now(timezone.utc)
        cards: List[ReviewCard] = []
        index = Index(self.index_path)
        for note_id, indexed_path in index.read_rows():
            card_path = os.path.join(self.repo_root, ".srs", f"{note_id}.json")
            fsrs_card, review_logs = self._load_fsrs_card(card_path)
            if not self._is_due(fsrs_card, now):
                continue
            note_path = self._note_abs_path(indexed_path)
            cards.append(
                ReviewCard(
                    note_id=note_id,
                    note_path=note_path,
                    card_path=card_path,
                    note_text=self._read_note_text(note_path),
                    fsrs_card=fsrs_card,
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

    def _read_note_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _load_fsrs_card(self, card_path: str) -> Tuple[FsrsCard, List[ReviewLog]]:
        with open(card_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
        raw_data = json.loads(raw_text)
        card = FsrsCard.from_json(raw_text)
        raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
        review_logs: List[ReviewLog] = []
        if isinstance(raw_review_logs, list):
            for item in raw_review_logs:
                if isinstance(item, dict):
                    review_logs.append(ReviewLog.from_dict(item))  # type: ignore[arg-type]
        return card, review_logs

    def _is_due(self, card: FsrsCard, now: datetime) -> bool:
        due = card.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= now

    def _save_reviewed_card(self, card: ReviewCard) -> None:
        merged: Dict[str, object] = json.loads(card.fsrs_card.to_json())
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in card.review_logs]

        tmp_path = card.card_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=4, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, card.card_path)
