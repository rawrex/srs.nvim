import math
import os
from datetime import datetime, timezone

from card.card import Card
from card.parsers import ParserRegistry
from core.index.index import Index
from core.index.storage import parse_storage_json

IndexRow = tuple[str, str, str, int, int]
LineRange = tuple[int, int]


class CardsManager:
    def __init__(self, repo_root: str, parser_registry: ParserRegistry) -> None:
        self.repo_root = repo_root
        self.parser_registry = parser_registry
        self.index_path = os.path.join(repo_root, ".srs", "index.txt")

    def has_index(self) -> bool:
        return os.path.exists(self.index_path)

    def load_due_cards(self) -> list[Card]:
        now = datetime.now(timezone.utc)
        index_rows = self._read_index_rows()
        claimed_lines_by_note = self._collect_claimed_lines_by_note(index_rows)
        cards_with_paths, note_question_blocks = self._build_cards_with_note_context(
            index_rows
        )
        self._add_unclaimed_note_context(note_question_blocks, claimed_lines_by_note)
        return self._filter_due_cards(cards_with_paths, note_question_blocks, now)

    def save_reviewed_card(self, card: Card) -> None:
        card.save_storage_file()

    def estimate_due_cards_duration_minutes(self, cards: list[Card]) -> int | None:
        total_duration_ms = 0
        for card in cards:
            if not card.metadata.review_logs:
                return None
            latest_review_log = card.metadata.review_logs[-1]
            review_duration = getattr(latest_review_log, "review_duration", None)
            if not isinstance(review_duration, int):
                return None
            total_duration_ms += review_duration

        return math.ceil(total_duration_ms / 60_000)

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
