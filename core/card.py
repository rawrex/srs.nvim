from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import CodeType
from typing import List

from fsrs import Card as SchedulerCard
from fsrs import Rating

from core.index.model import IndexEntry, Metadata

__all__ = ["SchedulerCard", "REVEAL_ALL_LABEL", "RevealMode", "ViewBlock", "CardView", "Card"]


REVEAL_ALL_LABEL = ""


class RevealMode(str, Enum):
    WHOLE = "whole"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class ViewBlock:
    start_line: int
    text: str
    is_primary: bool


@dataclass(frozen=True)
class CardView:
    blocks: List[ViewBlock]

    def primary_block(self) -> ViewBlock:
        for block in self.blocks:
            if block.is_primary:
                return block
        if self.blocks:
            return self.blocks[0]
        return ViewBlock(start_line=1, text="", is_primary=True)


@dataclass()
class Card(ABC):
    source_text: str
    index_entry: IndexEntry
    metadata: Metadata
    context: dict[tuple[int, int], str]

    def is_due(self, now: datetime) -> bool:
        due = self.metadata.scheduler_card.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= now

    @abstractmethod
    def reveal_for_label(self, label: str) -> CardView | None:
        raise NotImplementedError

    @abstractmethod
    def question_view(self) -> CardView:
        raise NotImplementedError

    @abstractmethod
    def answer_view(self) -> CardView:
        raise NotImplementedError

    @abstractmethod
    def context_view(self) -> CardView:
        raise NotImplementedError

    def suggested_rating(self) -> Rating | None:
        return None
