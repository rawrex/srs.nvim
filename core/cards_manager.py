import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from core.card import Card
from core.index.index import Index
from core.index.storage import parse_storage_json
from core.parsers import ParserRegistry

IndexRow = tuple[str, str, str, int, int]
LineRange = tuple[int, int]


@dataclass(frozen=True)
class DueCard:
    card: Card
    note_context_blocks: dict[LineRange, str]


class CardsManager:
    def __init__(self, repo_root: str, parser_registry: ParserRegistry) -> None:
        self.repo_root = repo_root
        self.parser_registry = parser_registry

    def load_due_cards(self) -> list[DueCard]:
        now = datetime.now(timezone.utc)
        index_rows = Index(
            os.path.join(self.repo_root, ".srs", "index.txt"),
            collect_parser_rows=lambda _indexed_path: [],
        ).read_rows()

        claimed_lines_by_note: dict[str, set[int]] = {}
        for _, indexed_path, _, start_line, end_line in index_rows:
            note_path = self._note_abs_path(indexed_path)
            claimed_lines_by_note.setdefault(note_path, set()).update(
                range(start_line, end_line + 1)
            )

        cards_with_paths, note_context_blocks = self._build_cards_with_note_context(
            index_rows
        )
        self._add_unclaimed_note_context(note_context_blocks, claimed_lines_by_note)
        return self._filter_due_cards(cards_with_paths, note_context_blocks, now)

    def estimate_due_cards_duration_minutes(
        self, due_cards: list[DueCard]
    ) -> int | None:
        total_duration_ms = 0
        for due_card in due_cards:
            card = due_card.card
            if not card.metadata.review_logs:
                return None
            latest_review_log = card.metadata.review_logs[-1]
            review_duration = getattr(latest_review_log, "review_duration", None)
            if not isinstance(review_duration, int):
                return None
            total_duration_ms += review_duration

        return math.ceil(total_duration_ms / 60_000)

    def _build_cards_with_note_context(
        self,
        index_rows: list[IndexRow],
    ) -> tuple[list[tuple[Card, str]], dict[str, dict[LineRange, str]]]:
        cards_with_paths: list[tuple[Card, str]] = []
        note_context_blocks: dict[str, dict[LineRange, str]] = {}
        parser_blocks_cache: dict[tuple[str, str], dict[LineRange, str]] = {}

        for note_id, indexed_path, parser_id, start_line, end_line in index_rows:
            note_path = self._note_abs_path(indexed_path)
            cache_key = (note_path, parser_id)
            parser_blocks = parser_blocks_cache.get(cache_key)
            if parser_blocks is None:
                parser_blocks = self._read_parser_blocks(note_path, parser_id)
                parser_blocks_cache[cache_key] = parser_blocks

            note_text = parser_blocks.get((start_line, end_line))
            if note_text is None:
                continue

            card = self._build_card(
                note_id=note_id,
                note_path=note_path,
                parser_id=parser_id,
                start_line=start_line,
                end_line=end_line,
                note_text=note_text,
            )
            note_context_blocks.setdefault(note_path, {})[(start_line, end_line)] = (
                card.context_view().primary_block().text
            )
            cards_with_paths.append((card, note_path))

        return cards_with_paths, note_context_blocks

    def _build_card(
        self,
        note_id: str,
        note_path: str,
        parser_id: str,
        start_line: int,
        end_line: int,
        note_text: str,
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
            card_path=card_path,
            metadata=metadata,
        )

    def _add_unclaimed_note_context(
        self,
        note_context_blocks: dict[str, dict[LineRange, str]],
        claimed_lines_by_note: dict[str, set[int]],
    ) -> None:
        for note_path, claimed_lines in claimed_lines_by_note.items():
            fallback_blocks = self._read_unclaimed_line_blocks(note_path, claimed_lines)
            if not fallback_blocks:
                continue
            context_blocks = note_context_blocks.setdefault(note_path, {})
            for line_range, block in fallback_blocks.items():
                context_blocks.setdefault(line_range, block)

    def _filter_due_cards(
        self,
        cards_with_paths: list[tuple[Card, str]],
        note_context_blocks: dict[str, dict[LineRange, str]],
        now: datetime,
    ) -> list[DueCard]:
        due_cards: list[DueCard] = []
        for card, note_path in cards_with_paths:
            if card.is_due(now):
                due_cards.append(
                    DueCard(
                        card=card,
                        note_context_blocks=note_context_blocks.get(note_path, {}),
                    )
                )
        return due_cards

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self.repo_root, indexed_path.lstrip("/"))

    def _read_parser_blocks(self, path: str, parser_id: str) -> dict[LineRange, str]:
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
