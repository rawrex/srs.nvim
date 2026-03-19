import os
import time
from datetime import datetime, timezone

from fsrs import Scheduler

from srs_index import Index

from .card import Card
from .config import ReviewConfig
from .parsers import PARSER_REGISTRY
from .storage import parse_storage_json
from .ui import ReviewUI


class ReviewSession:
    def __init__(
        self,
        repo_root: str,
        ui: ReviewUI,
        config: ReviewConfig,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.reveal_mode = config.reveal_mode
        self.cloze_open = config.cloze_open
        self.cloze_close = config.cloze_close
        self.mask_char = config.mask_char
        self.between_notes_timeout_ms = config.between_notes_timeout_ms
        self.scheduler = scheduler or Scheduler()
        self.parser_registry = PARSER_REGISTRY
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
            question_title = f"\n[{idx}/{total}] {card.note_filename}"
            answer_title = f"\n[{idx}/{total}] {card.note_filename} — answer"

            # Step 1: question + reveals.
            question_started_ns = time.monotonic_ns()
            answer_view = self.ui.run_question_step(question_title, card)

            review_duration_ms = max(
                0, (time.monotonic_ns() - question_started_ns) // 1_000_000
            )

            # Step 2: answer view.
            self.ui.show_answer_step(answer_title, answer_view)

            # Step 3: rating.
            self.ui.print_message("")
            rating = self.ui.prompt_rating_step()
            updated_card, review_log = self.scheduler.review_card(
                card.metadata.scheduler_card,
                rating,
                review_duration=int(review_duration_ms),
            )
            card.metadata.scheduler_card = updated_card
            card.metadata.review_logs.append(review_log)
            self._save_reviewed_card(card)
            self.ui.print_message("Saved")
            if idx < total and self.between_notes_timeout_ms > 0:
                time.sleep(self.between_notes_timeout_ms / 1000)

        return 0

    def _load_due_cards(self) -> list[Card]:
        now = datetime.now(timezone.utc)
        cards_with_paths: list[tuple[Card, str]] = []
        note_question_blocks: dict[str, dict[tuple[int, int], str]] = {}
        raw_blocks_cache: dict[tuple[str, str], dict[tuple[int, int], str]] = {}
        index = Index(self.index_path)
        for note_id, indexed_path, parser_id, start_line, end_line in index.read_rows():
            note_path = self._note_abs_path(indexed_path)
            cache_key = (note_path, parser_id)
            if cache_key not in raw_blocks_cache:
                raw_blocks_cache[cache_key] = self._read_note_blocks(
                    note_path,
                    parser_id,
                )
            note_text = raw_blocks_cache[cache_key].get((start_line, end_line))
            if note_text is None:
                continue
            card_path = os.path.join(self.repo_root, ".srs", f"{note_id}.json")
            with open(card_path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            metadata = parse_storage_json(raw_text)
            parser = self.parser_registry.get(parser_id)
            card = parser.build_card(
                note_id=note_id,
                note_path=note_path,
                note_text=note_text,
                start_line=start_line,
                end_line=end_line,
                note_blocks=raw_blocks_cache[cache_key],
                card_path=card_path,
                metadata=metadata,
            )
            note_question_blocks.setdefault(note_path, {})[(start_line, end_line)] = (
                card.question_view().primary_block().text
            )
            cards_with_paths.append((card, note_path))

        due_cards: list[Card] = []
        for card, note_path in cards_with_paths:
            card.note_blocks = note_question_blocks.get(note_path, {})
            if card.is_due(now):
                due_cards.append(card)
        return due_cards

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self.repo_root, indexed_path.lstrip("/"))

    def _read_note_blocks(
        self, path: str, parser_id: str
    ) -> dict[tuple[int, int], str]:
        with open(path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
        parser = self.parser_registry.get(parser_id)
        return {
            (start_line, end_line): block
            for start_line, end_line, block in parser.split_note_into_cards(note_text)
        }

    def _save_reviewed_card(self, card: Card) -> None:
        card.save_storage_file()
