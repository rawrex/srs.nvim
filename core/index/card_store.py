import os

from core import util
from core.card import SchedulerCard
from core.index.model import IndexRowTuple
from core.index.storage import Metadata, write_metadata
from core.parsers import ParserRegistry


class IndexCardStore:
    def __init__(self, index_path: str) -> None:
        self.index_path = index_path

    def is_note_path(self, indexed_path: str) -> bool:
        return not (
            indexed_path.startswith("/.srs/")
            or indexed_path == "/.srs"
            or indexed_path.startswith("/.git/")
            or indexed_path == "/.git"
        )

    def index_file_path(self) -> str:
        rel_path = os.path.relpath(self.index_path, self.repo_root())
        return util.normalize_path(rel_path)

    def remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self.card_path(note_id)
        return None

    def collect_parser_rows(
        self, indexed_path: str, parser_registry: ParserRegistry
    ) -> list[tuple[str, int, int]]:
        note_text = self.read_note_text(indexed_path)
        if note_text is None:
            return []

        selected: list[tuple[str, int, int]] = []
        claimed: list[tuple[int, int]] = []
        for parser in parser_registry.ordered():
            cards = parser.split_note_into_cards(note_text)
            for start_line, end_line, _ in cards:
                if any(
                    not (end_line < claimed_start or start_line > claimed_end)
                    for claimed_start, claimed_end in claimed
                ):
                    continue
                selected.append((parser.parser_id, start_line, end_line))
                claimed.append((start_line, end_line))

        return sorted(selected, key=lambda row: (row[1], row[2], row[0]))

    def create_card_row(
        self,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> tuple[IndexRowTuple, str]:
        scheduler_card = SchedulerCard()
        metadata = Metadata(scheduler_card=scheduler_card, review_logs=[])
        card_id = str(scheduler_card.card_id)
        self._write_card_file(card_id, metadata)
        return (card_id, parser_id, start_line, end_line), self.card_path(card_id)

    def card_path(self, note_id: str) -> str:
        return f"/.srs/{note_id}.json"

    def repo_root(self) -> str:
        return os.path.dirname(os.path.dirname(self.index_path))

    def _card_abs_path(self, note_id: str) -> str:
        return os.path.join(os.path.dirname(self.index_path), f"{note_id}.json")

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self.repo_root(), indexed_path.lstrip("/"))

    def read_note_text(self, indexed_path: str) -> str | None:
        note_path = self._note_abs_path(indexed_path)
        if not os.path.exists(note_path):
            return None
        try:
            with open(note_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError):
            return None

    def _write_card_file(self, card_id: str, metadata: Metadata) -> None:
        card_path = self._card_abs_path(card_id)
        write_metadata(card_path, metadata)
