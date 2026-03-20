from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Tuple

from card.card import Card
from core.index.storage import Metadata


class NoteParser(ABC):
    parser_id: ClassVar[str]
    priority: ClassVar[int] = 0

    @abstractmethod
    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, int, str]]:
        raise NotImplementedError

    @abstractmethod
    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        end_line: int,
        note_blocks: Dict[Tuple[int, int], str],
        card_path: str,
        metadata: Metadata,
    ) -> Card:
        raise NotImplementedError
