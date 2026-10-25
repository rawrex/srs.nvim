from abc import ABC, abstractmethod
from typing import ClassVar


class Parser(ABC):
    """A card-type pack: it only knows how to find card spans in a note.

    Presentation is the UI's job; the review core never builds cards.
    """

    parser_id: ClassVar[str]
    priority: ClassVar[int] = 0

    @abstractmethod
    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        raise NotImplementedError
