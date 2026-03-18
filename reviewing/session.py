import os
import time
from datetime import datetime, timezone
from typing import Dict, List

from fsrs import Scheduler

from hooks_runtime.index import Index, split_note_into_cards

from .card import Card, CardFactory, ClozeCardFactory
from .config import ReviewConfig
from .ui import ReviewUI


class ReviewSession:
    def __init__(
        self,
        repo_root: str,
        ui: ReviewUI,
        config: ReviewConfig,
        scheduler: Scheduler | None = None,
        card_factory: CardFactory | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.reveal_mode = config.reveal_mode
        self.cloze_open = config.cloze_open
        self.cloze_close = config.cloze_close
        self.mask_char = config.mask_char
        self.between_notes_timeout_ms = config.between_notes_timeout_ms
        self.scheduler = scheduler or Scheduler()
        self.card_factory = card_factory or ClozeCardFactory(
            reveal_mode=self.reveal_mode,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
            mask_char=self.mask_char,
        )
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
            rating_view = self.ui.prompt_cloze_reveal(title, card)

            review_duration_ms = max(
                0, (time.monotonic_ns() - question_started_ns) // 1_000_000
            )
            self.ui.show_rating_view(
                f"\n[{idx}/{total}] {card.note_filename} — answer",
                rating_view,
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
            note_path = self._note_abs_path(indexed_path)
            if note_path not in note_blocks_cache:
                note_blocks_cache[note_path] = self._read_note_blocks(note_path)
            note_text = note_blocks_cache[note_path].get(start_line)
            if note_text is None:
                continue
            card_path = os.path.join(self.repo_root, ".srs", f"{note_id}.json")
            card = self.card_factory.from_storage_file(
                note_id=note_id,
                note_path=note_path,
                card_path=card_path,
                note_text=note_text,
                start_line=start_line,
                note_blocks=note_blocks_cache[note_path],
            )
            if card.is_due(now):
                cards.append(card)
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

    def _save_reviewed_card(self, card: Card) -> None:
        card.save_storage_file()
