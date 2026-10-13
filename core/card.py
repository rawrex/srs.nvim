from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from fsrs import Card as SchedulerCard
from fsrs import Rating

from core.index.model import IndexEntry, Metadata

__all__ = ["SchedulerCard", "REVEAL_ALL_LABEL", "RevealMode", "ViewBlock", "CardRef", "Card"]


REVEAL_ALL_LABEL = ""


class RevealMode(str, Enum):
    WHOLE = "whole"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class ViewBlock:
    start_line: int
    text: str


@dataclass(frozen=True)
class CardRef:
    """Where the current card sits in the review session.

    UIs format their own heading from this; the engine never builds titles.
    """

    index: int  # 1-based position of the card in the due list
    total: int  # number of due cards in the session
    note_path: str  # repo-relative source note path (leading "/")


@dataclass(kw_only=True)
class Card(ABC):
    source_text: str
    index_entry: IndexEntry
    metadata: Metadata
    context: dict[tuple[int, int], str]

    @abstractmethod
    def reveal_for_label(self, label: str) -> ViewBlock | None:
        raise NotImplementedError

    @abstractmethod
    def question_view(self) -> ViewBlock:
        raise NotImplementedError

    @abstractmethod
    def answer_view(self) -> ViewBlock:
        raise NotImplementedError

    @abstractmethod
    def context_view(self) -> ViewBlock:
        raise NotImplementedError

    def suggested_rating(self) -> Rating | None:
        return None

    def reveal_labels(self) -> list[str]:
        """Keys that reveal part of the card during the question step.

        The backend owns the label alphabet; clients bind exactly these keys
        and report the pressed one as the ``label`` of a ``reveal`` event.
        """
        return []
