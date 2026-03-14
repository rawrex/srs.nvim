import random
import re
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple

from fsrs import Card as FsrsCard
from fsrs import ReviewLog


CLOZE_RE = re.compile(r"~\{(.*?)\}", re.DOTALL)
MASK_CHAR = "▇"
LABEL_CHARS = (
    string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
)


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


def parse_note_clozes(note_text: str) -> Tuple[List[str], List[str]]:
    text_parts: List[str] = []
    clozes: List[str] = []
    last_end = 0

    for match in CLOZE_RE.finditer(note_text):
        start, end = match.span()
        text_parts.append(note_text[last_end:start])
        clozes.append(match.group(1))
        last_end = end

    text_parts.append(note_text[last_end:])
    return text_parts, clozes


def mask_hidden_text(text: str) -> str:
    return "".join("\n" if ch == "\n" else MASK_CHAR for ch in text)


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
class ReviewCard:
    note_id: str
    note_path: str
    card_path: str
    note_text: str
    fsrs_card: FsrsCard
    review_logs: List[ReviewLog]
    reveal_mode: RevealMode
    text_parts: List[str] = field(init=False)
    clozes: List[str] = field(init=False)
    labels: List[str] = field(init=False)
    label_to_index: Dict[str, int] = field(init=False)
    whole_revealed: List[bool] = field(init=False)
    incremental_states: List[IncrementalRevealState] = field(init=False)

    def __post_init__(self) -> None:
        self.reveal_mode = RevealMode(self.reveal_mode)
        self.text_parts, self.clozes = parse_note_clozes(self.note_text)
        self.labels = [LABEL_CHARS[idx] for idx in range(len(self.clozes))]
        self.label_to_index = {label: idx for idx, label in enumerate(self.labels)}
        self.whole_revealed = [False] * len(self.clozes)
        self.incremental_states = [
            build_incremental_reveal_state(hidden) for hidden in self.clozes
        ]

    @property
    def note_filename(self) -> str:
        return self.note_path.rsplit("/", 1)[-1]

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
                parts.append(f"[{self.labels[idx]}]{mask_hidden_text(hidden)}")
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
            ch if ch == "\n" or idx in state.revealed_positions else MASK_CHAR
            for idx, ch in enumerate(hidden)
        )
