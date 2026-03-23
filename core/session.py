import os
import time
from datetime import datetime, timezone

from fsrs import Scheduler

from core import util
from core.index.index import Index

from card.card import Card
from core.config import ReviewConfig
from card.parsers import ParserRegistry
from core.index.storage import parse_storage_json
from ui.ui import ReviewUI, SessionEntryUI

IndexRow = tuple[str, str, str, int, int]
LineRange = tuple[int, int]


class ReviewSession:
    def __init__(
        self,
        repo_root: str,
        ui: ReviewUI,
        config: ReviewConfig,
        parser_registry: ParserRegistry,
        session_entry_ui: SessionEntryUI | None = None,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.ui = ui
        self.session_entry_ui = session_entry_ui
        self.between_notes_timeout_ms = config.between_notes_timeout_ms
        self.auto_stage_reviewed_cards = config.auto_stage_reviewed_cards
        self.scheduler = scheduler or config.build_scheduler()
        self.parser_registry = parser_registry
        self.index_path = os.path.join(repo_root, ".srs", "index.txt")
        self._reviewed_card_paths: set[str] = set()

    def run(self) -> int:
        if not os.path.exists(self.index_path):
            self.ui.print_message("Missing index")
            return 1

        cards = self._load_due_cards()
        if not cards:
            self.ui.print_message("No due cards.")
            return 0

        total = len(cards)
        if self.session_entry_ui:
            self.session_entry_ui.show_start_menu(total)
        try:
            for idx, card in enumerate(cards, start=1):
                question_title = f"\n[{idx}/{total}] {card.note_filename}"
                answer_title = f"\n[{idx}/{total}] {card.note_filename} — answer"

                # Step 1: question + reveals.
                question_started_ns = time.monotonic_ns()
                self.ui.run_question_step(question_title, card)

                review_duration_ms = max(
                    0, (time.monotonic_ns() - question_started_ns) // 1_000_000
                )

                # Step 2: answer view.
                suggested_rating = card.suggested_rating()
                answer_view = card.answer_view()
                self.ui.show_answer_step(answer_title, card, answer_view)

                # Step 3: rating.
                self.ui.print_message("")
                rating = self.ui.prompt_rating_step(suggested_rating)
                updated_card, review_log = self.scheduler.review_card(
                    card.metadata.scheduler_card,
                    rating,
                    review_duration=int(review_duration_ms),
                )
                card.metadata.scheduler_card = updated_card
                card.metadata.review_logs.append(review_log)
                self._save_reviewed_card(card)
                self._stage_reviewed_card(card)
                self.ui.print_message("Saved")
                if idx < total and self.between_notes_timeout_ms > 0:
                    time.sleep(self.between_notes_timeout_ms / 1000)
        finally:
            self._commit_reviewed_cards()

        return 0

    def _load_due_cards(self) -> list[Card]:
        now = datetime.now(timezone.utc)
        index_rows = self._read_index_rows()
        claimed_lines_by_note = self._collect_claimed_lines_by_note(index_rows)
        cards_with_paths, note_question_blocks = self._build_cards_with_note_context(
            index_rows
        )
        self._add_unclaimed_note_context(note_question_blocks, claimed_lines_by_note)
        return self._filter_due_cards(cards_with_paths, note_question_blocks, now)

    def _read_index_rows(self) -> list[IndexRow]:
        return list(
            Index(self.index_path, parser_registry=self.parser_registry).read_rows()
        )

    def _collect_claimed_lines_by_note(
        self,
        index_rows: list[IndexRow],
    ) -> dict[str, set[int]]:
        claimed_lines_by_note: dict[str, set[int]] = {}
        for _note_id, indexed_path, _parser_id, start_line, end_line in index_rows:
            note_path = self._note_abs_path(indexed_path)
            claimed_lines_by_note.setdefault(note_path, set()).update(
                range(start_line, end_line + 1)
            )
        return claimed_lines_by_note

    def _build_cards_with_note_context(
        self,
        index_rows: list[IndexRow],
    ) -> tuple[list[tuple[Card, str]], dict[str, dict[LineRange, str]]]:
        cards_with_paths: list[tuple[Card, str]] = []
        note_question_blocks: dict[str, dict[LineRange, str]] = {}
        raw_blocks_cache: dict[tuple[str, str], dict[LineRange, str]] = {}

        for note_id, indexed_path, parser_id, start_line, end_line in index_rows:
            note_path = self._note_abs_path(indexed_path)
            cache_key = (note_path, parser_id)
            blocks_for_parser = raw_blocks_cache.get(cache_key)
            if blocks_for_parser is None:
                blocks_for_parser = self._read_note_blocks(note_path, parser_id)
                raw_blocks_cache[cache_key] = blocks_for_parser

            note_text = blocks_for_parser.get((start_line, end_line))
            if note_text is None:
                continue

            card = self._build_card(
                note_id=note_id,
                note_path=note_path,
                parser_id=parser_id,
                start_line=start_line,
                end_line=end_line,
                note_text=note_text,
                note_blocks=blocks_for_parser,
            )
            note_question_blocks.setdefault(note_path, {})[(start_line, end_line)] = (
                card.context_view().primary_block().text
            )
            cards_with_paths.append((card, note_path))

        return cards_with_paths, note_question_blocks

    def _build_card(
        self,
        note_id: str,
        note_path: str,
        parser_id: str,
        start_line: int,
        end_line: int,
        note_text: str,
        note_blocks: dict[LineRange, str],
    ) -> Card:
        card_path = os.path.join(self.repo_root, ".srs", f"{note_id}.json")
        with open(card_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
        metadata = parse_storage_json(raw_text)
        parser = self.parser_registry.get(parser_id)
        return parser.build_card(
            note_id=note_id,
            note_path=note_path,
            note_text=note_text,
            start_line=start_line,
            end_line=end_line,
            note_blocks=note_blocks,
            card_path=card_path,
            metadata=metadata,
        )

    def _add_unclaimed_note_context(
        self,
        note_question_blocks: dict[str, dict[LineRange, str]],
        claimed_lines_by_note: dict[str, set[int]],
    ) -> None:
        for note_path, claimed_lines in claimed_lines_by_note.items():
            fallback_blocks = self._read_unclaimed_line_blocks(note_path, claimed_lines)
            if not fallback_blocks:
                continue
            note_blocks = note_question_blocks.setdefault(note_path, {})
            for line_range, block in fallback_blocks.items():
                note_blocks.setdefault(line_range, block)

    def _filter_due_cards(
        self,
        cards_with_paths: list[tuple[Card, str]],
        note_question_blocks: dict[str, dict[LineRange, str]],
        now: datetime,
    ) -> list[Card]:
        due_cards: list[Card] = []
        for card, note_path in cards_with_paths:
            card.note_blocks = note_question_blocks.get(note_path, {})
            if card.is_due(now):
                due_cards.append(card)
        return due_cards

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self.repo_root, indexed_path.lstrip("/"))

    def _read_note_blocks(self, path: str, parser_id: str) -> dict[LineRange, str]:
        with open(path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
        parser = self.parser_registry.get(parser_id)
        return {
            (start_line, end_line): block
            for start_line, end_line, block in parser.split_note_into_cards(note_text)
        }

    def _save_reviewed_card(self, card: Card) -> None:
        card.save_storage_file()

    def _stage_reviewed_card(self, card: Card) -> None:
        if not self.auto_stage_reviewed_cards:
            return
        rel_card_path = os.path.relpath(card.card_path, self.repo_root).replace(
            os.sep, "/"
        )
        code, _out, _err = util.run_git(
            ["add", "--", rel_card_path],
            cwd=self.repo_root,
        )
        if code == 0:
            self._reviewed_card_paths.add(rel_card_path)

    def _commit_reviewed_cards(self) -> None:
        if not self.auto_stage_reviewed_cards or not self._reviewed_card_paths:
            return
        reviewed_paths = sorted(self._reviewed_card_paths)
        code, _out, _err = util.run_git(
            ["diff", "--cached", "--quiet", "--"] + reviewed_paths,
            cwd=self.repo_root,
        )
        if code == 0:
            return
        if code != 1:
            return
        code, _out, _err = util.run_git(
            ["commit", "-m", "Spaced repetition session", "--"] + reviewed_paths,
            cwd=self.repo_root,
        )
        if code == 0:
            self._reviewed_card_paths.clear()

    def _read_unclaimed_line_blocks(
        self, note_path: str, claimed_lines: set[int]
    ) -> dict[LineRange, str]:
        with open(note_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return {
            (line_number, line_number): line
            for line_number, line in enumerate(lines, start=1)
            if line_number not in claimed_lines and line.strip()
        }
