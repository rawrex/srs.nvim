from abc import ABC, abstractmethod
from typing import ClassVar, List, Tuple

from core.card import Card
from core.index.model import IndexEntry, Metadata


class Parser(ABC):
    parser_id: ClassVar[str]
    priority: ClassVar[int] = 0

    @abstractmethod
    def interpret_text(self, note_text: str) -> List[Tuple[int, int, str]]:
        raise NotImplementedError

    @abstractmethod
    def build_card(self, source_text: str, index_entry: IndexEntry, metadata: Metadata) -> Card:
        raise NotImplementedError
