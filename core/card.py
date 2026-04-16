from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from fsrs import Card as SchedulerCard
from fsrs import Rating

from core.index.model import IndexEntry, Metadata

__all__ = ["SchedulerCard", "REVEAL_ALL_LABEL", "RevealMode", "ViewBlock", "Card"]


REVEAL_ALL_LABEL = ""


class RevealMode(str, Enum):
    WHOLE = "whole"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class ViewBlock:
    start_line: int
    text: str


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
