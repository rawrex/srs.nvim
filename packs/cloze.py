import random
import re
import string
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Dict, List, Tuple

from fsrs import Rating

from core.api import Parser
from core.autograde import suggest_rating
from core.card import REVEAL_ALL_LABEL, Card, CardView, RevealMode, ViewBlock
from core.config import ReviewConfig
from core.index.model import IndexEntry, Metadata

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


CLOZE_PARSER_ID = "cloze"
LABEL_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation


@dataclass
class IncrementalRevealState:
    word_first_positions: List[int]
    random_positions: List[int]
    revealed_positions: set[int] = field(default_factory=set)
    next_word_first_index: int = 0
    next_random_index: int = 0
    fully_revealed: bool = False


def parse_note_clozes(note_text: str, cloze_open: str, cloze_close: str) -> Tuple[List[str], List[str]]:
    text_parts: List[str] = []
    clozes: List[str] = []
    last_end = 0
    cloze_re = re.compile(re.escape(cloze_open) + r"(.*?)" + re.escape(cloze_close), re.DOTALL)

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
    random_positions = [idx for idx, ch in enumerate(hidden) if ch != "\n" and idx not in first_positions]
    random.shuffle(random_positions)
    return IncrementalRevealState(word_first_positions=word_first_positions, random_positions=random_positions)


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

    if state.next_word_first_index >= len(state.word_first_positions) and state.next_random_index >= len(
        state.random_positions
    ):
        state.fully_revealed = True


@dataclass
class ClozeCard(Card):
    reveal_mode: RevealMode = RevealMode.INCREMENTAL
    cloze_open: str = "~{"
    cloze_close: str = "}"
    mask_char: str = "▇"
    text_parts: List[str] = field(init=False)
    clozes: List[str] = field(init=False)
    labels: List[str] = field(init=False)
    label_to_index: Dict[str, int] = field(init=False)
    whole_revealed: List[bool] = field(init=False)
    incremental_states: List[IncrementalRevealState] = field(init=False)

    def __post_init__(self) -> None:
        self.reveal_mode = RevealMode(self.reveal_mode)
        self.text_parts, self.clozes = parse_note_clozes(
            self.source_text, cloze_open=self.cloze_open, cloze_close=self.cloze_close
        )
        self.labels = [LABEL_CHARS[idx] for idx in range(len(self.clozes))]
        self.label_to_index = {label: idx for idx, label in enumerate(self.labels)}
        self.whole_revealed = [False] * len(self.clozes)
        self.incremental_states = [build_incremental_reveal_state(hidden) for hidden in self.clozes]

    def reveal_for_label(self, label: str) -> CardView | None:
        if label == REVEAL_ALL_LABEL:
            return self.answer_view()

        idx = self.label_to_index.get(label)
        if idx is None:
            return None
        if self.reveal_mode == RevealMode.INCREMENTAL:
            if self.incremental_states[idx].fully_revealed:
                return None
            reveal_next_incremental_char(self.incremental_states[idx])
            return self.question_view()
        if self.whole_revealed[idx]:
            return None
        self.whole_revealed[idx] = True
        return self.question_view()

    def suggested_rating(self) -> Rating | None:
        total_hidden = sum(self._hidden_char_count(hidden) for hidden in self.clozes)
        revealed_hidden = 0
        for idx, hidden in enumerate(self.clozes):
            hidden_count = self._hidden_char_count(hidden)
            if self.reveal_mode == RevealMode.INCREMENTAL:
                state = self.incremental_states[idx]
                if state.fully_revealed:
                    revealed_hidden += hidden_count
                else:
                    revealed_hidden += min(len(state.revealed_positions), hidden_count)
                continue
            if self.whole_revealed[idx]:
                revealed_hidden += hidden_count
        return suggest_rating(revealed_hidden, total_hidden)

    def _hidden_char_count(self, hidden: str) -> int:
        return sum(1 for ch in hidden if ch != "\n")

    def question_view(self) -> CardView:
        current = self._question_block()
        return self._build_view(current_block=current)

    def answer_view(self) -> CardView:
        if self.reveal_mode == RevealMode.INCREMENTAL:
            for state in self.incremental_states:
                state.fully_revealed = True
        else:
            for idx in range(len(self.whole_revealed)):
                self.whole_revealed[idx] = True
        return self._build_view(current_block=self._question_block())

    def context_view(self) -> CardView:
        return self._build_view(current_block=self._masked_context_block(self.source_text))

    def _question_block(self) -> str:
        parts: List[str] = [self.text_parts[0]]
        for idx, hidden in enumerate(self.clozes):
            if self.reveal_mode == RevealMode.INCREMENTAL:
                state = self.incremental_states[idx]
                if state.fully_revealed:
                    parts.append(f"`{hidden}`")
                else:
                    parts.append(f"[{self.labels[idx]}]{self._incremental_hidden_view(hidden, state)}")
            elif self.whole_revealed[idx]:
                parts.append(f"`{hidden}`")
            else:
                parts.append(f"[{self.labels[idx]}]{mask_hidden_text(hidden, self.mask_char)}")
            parts.append(self.text_parts[idx + 1])
        return "".join(parts)

    def _build_view(self, current_block: str) -> CardView:
        return CardView(blocks=[ViewBlock(start_line=self.index_entry.start_line, text=current_block, is_primary=True)])

    def _masked_context_block(self, block: str) -> str:
        text_parts, clozes = parse_note_clozes(block, self.cloze_open, self.cloze_close)
        if not clozes:
            label_re = re.compile(r"\[[^\]]\]")
            return label_re.sub("", block)
        parts = [text_parts[0]]
        for idx, hidden in enumerate(clozes):
            parts.append(mask_hidden_text(hidden, self.mask_char))
            parts.append(text_parts[idx + 1])
        masked = "".join(parts)
        label_re = re.compile(r"\[[^\]]\]")
        return label_re.sub("", masked)

    def _incremental_hidden_view(self, hidden: str, state: IncrementalRevealState) -> str:
        if state.fully_revealed:
            return hidden
        return "".join(
            ch if ch == "\n" or idx in state.revealed_positions else self.mask_char for idx, ch in enumerate(hidden)
        )


@dataclass(frozen=True)
class ClozeParser(Parser):
    parser_id: ClassVar[str] = CLOZE_PARSER_ID
    priority: ClassVar[int] = 0
    reveal_mode: RevealMode
    cloze_open: str
    cloze_close: str
    mask_char: str

    def interpret_text(self, note_text: str) -> List[Tuple[int, int, str]]:
        cards: List[Tuple[int, int, str]] = []
        cloze_re = re.compile(re.escape(self.cloze_open) + r".*?" + re.escape(self.cloze_close))
        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if cloze_re.search(line):
                cards.append((line_number, line_number, line))
        return cards

    def build_card(self, source_text: str, index_entry: IndexEntry, metadata: Metadata) -> Card:
        return ClozeCard(
            source_text=source_text,
            index_entry=index_entry,
            metadata=metadata,
            context={},
            reveal_mode=self.reveal_mode,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
            mask_char=self.mask_char,
        )


def register_pack(registry: "ParserRegistry", config: ReviewConfig) -> None:
    registry.register(
        ClozeParser(
            reveal_mode=config.cloze.reveal_mode,
            cloze_open=config.cloze.cloze_open,
            cloze_close=config.cloze.cloze_close,
            mask_char=config.cloze.mask_char,
        )
    )
