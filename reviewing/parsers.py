from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Dict, List, Tuple

from fsrs import ReviewLog

from .card import Card, ClozeCard, RevealMode, SchedulerCard
from .storage import storage_dict_for_scheduler_card


DEFAULT_PARSER_ID = "cloze"


class NoteParser(ABC):
    parser_id: ClassVar[str]

    @abstractmethod
    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, str]]:
        raise NotImplementedError

    @abstractmethod
    def new_storage_dict(self, scheduler_card: SchedulerCard) -> Dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        note_blocks: Dict[int, str],
        card_path: str,
        scheduler_card: SchedulerCard,
        review_logs: List[ReviewLog],
    ) -> Card:
        raise NotImplementedError


@dataclass(frozen=True)
class ClozeParser(NoteParser):
    parser_id: ClassVar[str] = DEFAULT_PARSER_ID
    reveal_mode: RevealMode
    cloze_open: str
    cloze_close: str
    mask_char: str

    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, str]]:
        cards: List[Tuple[int, str]] = []
        for line_number, line in enumerate(
            note_text.splitlines(keepends=True), start=1
        ):
            if line.strip():
                cards.append((line_number, line))
        return cards

    def new_storage_dict(self, scheduler_card: SchedulerCard) -> Dict[str, object]:
        return storage_dict_for_scheduler_card(scheduler_card)

    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        note_blocks: Dict[int, str],
        card_path: str,
        scheduler_card: SchedulerCard,
        review_logs: List[ReviewLog],
    ) -> Card:
        return ClozeCard(
            note_id=note_id,
            note_path=note_path,
            card_path=card_path,
            note_text=note_text,
            start_line=start_line,
            note_blocks=note_blocks,
            scheduler_card=scheduler_card,
            review_logs=review_logs,
            reveal_mode=self.reveal_mode,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
            mask_char=self.mask_char,
        )


@dataclass
class ParserRegistry:
    parsers: Dict[str, NoteParser]
    default_parser_id: str

    def register(self, parser: NoteParser) -> None:
        self.parsers[parser.parser_id] = parser

    def get(self, parser_id: str) -> NoteParser:
        return self.parsers[parser_id]

    def default(self) -> NoteParser:
        return self.get(self.default_parser_id)


def default_parser_registry() -> ParserRegistry:
    cloze = ClozeParser(
        reveal_mode=RevealMode.INCREMENTAL,
        cloze_open="~{",
        cloze_close="}",
        mask_char="▇",
    )
    return ParserRegistry(
        parsers={cloze.parser_id: cloze},
        default_parser_id=cloze.parser_id,
    )
