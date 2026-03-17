import json
import os
import random
import re
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Tuple

from fsrs import Card as SchedulerCard
from fsrs import ReviewLog


LABEL_CHARS = (
    string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
)
REVIEW_LOGS_KEY = "review_logs"


class RevealMode(str, Enum):
    WHOLE = "whole"
    INCREMENTAL = "incremental"


@dataclass
class IncrementalRevealState:
    word_first_positions: List[int]
    random_positions: List[int]
    revealed_positions: set[int] = field(default_factory=set)
    next_word_first_index: int = 0
    next_random_index: int = 0
    fully_revealed: bool = False


def parse_note_clozes(
    note_text: str,
    cloze_open: str,
    cloze_close: str,
) -> Tuple[List[str], List[str]]:
    text_parts: List[str] = []
    clozes: List[str] = []
    last_end = 0
    cloze_re = re.compile(
        re.escape(cloze_open) + r"(.*?)" + re.escape(cloze_close),
        re.DOTALL,
    )

    for match in cloze_re.finditer(note_text):
        start, end = match.span()
        text_parts.append(note_text[last_end:start])
        clozes.append(match.group(1))
        last_end = end

    text_parts.append(note_text[last_end:])
    return text_parts, clozes


def mask_hidden_text(text: str, mask_char: str) -> str:
    return "".join("\n" if ch == "\n" else mask_char for ch in text)


def build_incremental_reveal_state(hidden: str) -> IncrementalRevealState:
    word_first_positions = [match.start() for match in re.finditer(r"\S+", hidden)]
    first_positions = set(word_first_positions)
    random_positions = [
        idx
        for idx, ch in enumerate(hidden)
        if ch != "\n" and idx not in first_positions
    ]
    random.shuffle(random_positions)
    return IncrementalRevealState(
        word_first_positions=word_first_positions,
        random_positions=random_positions,
    )


def reveal_next_incremental_char(state: IncrementalRevealState) -> None:
    if state.fully_revealed:
        return

    if state.next_word_first_index < len(state.word_first_positions):
        idx = state.word_first_positions[state.next_word_first_index]
        state.next_word_first_index += 1
        state.revealed_positions.add(idx)
    elif state.next_random_index < len(state.random_positions):
        idx = state.random_positions[state.next_random_index]
        state.next_random_index += 1
        state.revealed_positions.add(idx)

    if state.next_word_first_index >= len(
        state.word_first_positions
    ) and state.next_random_index >= len(state.random_positions):
        state.fully_revealed = True


@dataclass
class Card:
    note_id: str
    note_path: str
    card_path: str
    note_text: str
    scheduler_card: SchedulerCard
    review_logs: List[ReviewLog]
    reveal_mode: RevealMode
    cloze_open: str
    cloze_close: str
    mask_char: str
    text_parts: List[str] = field(init=False)
    clozes: List[str] = field(init=False)
    labels: List[str] = field(init=False)
    label_to_index: Dict[str, int] = field(init=False)
    whole_revealed: List[bool] = field(init=False)
    incremental_states: List[IncrementalRevealState] = field(init=False)
    start_line: int = 1
    note_blocks: Dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.reveal_mode = RevealMode(self.reveal_mode)
        self.text_parts, self.clozes = parse_note_clozes(
            self.note_text,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
        )
        self.labels = [LABEL_CHARS[idx] for idx in range(len(self.clozes))]
        self.label_to_index = {label: idx for idx, label in enumerate(self.labels)}
        self.whole_revealed = [False] * len(self.clozes)
        self.incremental_states = [
            build_incremental_reveal_state(hidden) for hidden in self.clozes
        ]

    @property
    def note_filename(self) -> str:
        return self.note_path.rsplit("/", 1)[-1]

    @classmethod
    def from_storage_file(
        cls,
        note_id: str,
        note_path: str,
        card_path: str,
        note_text: str,
        start_line: int,
        note_blocks: Dict[int, str],
        reveal_mode: RevealMode,
        cloze_open: str,
        cloze_close: str,
        mask_char: str,
    ) -> "Card":
        with open(card_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
        scheduler_card, review_logs = parse_storage_json(raw_text)
        return cls(
            note_id=note_id,
            note_path=note_path,
            card_path=card_path,
            note_text=note_text,
            start_line=start_line,
            note_blocks=note_blocks,
            scheduler_card=scheduler_card,
            review_logs=review_logs,
            reveal_mode=reveal_mode,
            cloze_open=cloze_open,
            cloze_close=cloze_close,
            mask_char=mask_char,
        )

    @classmethod
    def new_storage_dict(cls) -> Dict[str, object]:
        return storage_dict_for_scheduler_card(SchedulerCard())

    def is_due(self, now: datetime) -> bool:
        due = self.scheduler_card.due
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= now

    def to_storage_dict(self) -> Dict[str, object]:
        merged = storage_dict_for_scheduler_card(self.scheduler_card)
        merged[REVIEW_LOGS_KEY] = [log.to_dict() for log in self.review_logs]
        return merged

    def save_storage_file(self) -> None:
        write_storage_file(self.card_path, self.to_storage_dict())

    def reveal_for_label(self, label: str) -> bool:
        idx = self.label_to_index.get(label)
        if idx is None:
            return False
        if self.reveal_mode == RevealMode.INCREMENTAL:
            reveal_next_incremental_char(self.incremental_states[idx])
            return True
        if self.whole_revealed[idx]:
            return False
        self.whole_revealed[idx] = True
        return True

    def question_view(self) -> str:
        parts: List[str] = [self.text_parts[0]]
        for idx, hidden in enumerate(self.clozes):
            if self.reveal_mode == RevealMode.INCREMENTAL:
                state = self.incremental_states[idx]
                if state.fully_revealed:
                    parts.append(f"`{hidden}`")
                else:
                    parts.append(
                        f"[{self.labels[idx]}]{self._incremental_hidden_view(hidden, state)}"
                    )
            elif self.whole_revealed[idx]:
                parts.append(f"`{hidden}`")
            else:
                parts.append(
                    f"[{self.labels[idx]}]{mask_hidden_text(hidden, self.mask_char)}"
                )
            parts.append(self.text_parts[idx + 1])
        return "".join(parts)

    def answer_view(self) -> str:
        parts: List[str] = [self.text_parts[0]]
        for idx, hidden in enumerate(self.clozes):
            parts.append(hidden)
            parts.append(self.text_parts[idx + 1])
        return "".join(parts)

    def _incremental_hidden_view(
        self, hidden: str, state: IncrementalRevealState
    ) -> str:
        if state.fully_revealed:
            return hidden
        return "".join(
            ch if ch == "\n" or idx in state.revealed_positions else self.mask_char
            for idx, ch in enumerate(hidden)
        )


def parse_storage_json(raw_text: str) -> Tuple[SchedulerCard, List[ReviewLog]]:
    raw_data = json.loads(raw_text)
    scheduler_card = SchedulerCard.from_json(raw_text)
    raw_review_logs = raw_data.get(REVIEW_LOGS_KEY)
    review_logs: List[ReviewLog] = []
    if isinstance(raw_review_logs, list):
        for item in raw_review_logs:
            if isinstance(item, dict):
                review_logs.append(ReviewLog.from_dict(item))  # pyright: ignore[reportArgumentType]
    return scheduler_card, review_logs


def storage_dict_for_scheduler_card(scheduler_card: SchedulerCard) -> Dict[str, object]:
    return json.loads(scheduler_card.to_json())


def write_storage_file(card_path: str, payload: Dict[str, object]) -> None:
    tmp_path = card_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=4, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, card_path)
