import random
import re
import string
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Dict, List, Tuple

from fsrs import Card as SchedulerCard

from reviewing.card import Card, CardView, REVEAL_ALL_LABEL, RevealMode, ViewBlock
from reviewing.api import NoteParser
from reviewing.storage import Metadata

if TYPE_CHECKING:
    from reviewing.parsers import ParserRegistry


CLOZE_PARSER_ID = "cloze"
LABEL_CHARS = (
    string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
)


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

    @classmethod
    def new_storage_dict(cls) -> Dict[str, object]:
        metadata = Metadata(scheduler_card=SchedulerCard(), review_logs=[])
        return metadata.to_storage_dict()

    def reveal_for_label(self, label: str) -> CardView | None:
        if label == REVEAL_ALL_LABEL:
            if self.reveal_mode == RevealMode.INCREMENTAL:
                for state in self.incremental_states:
                    state.fully_revealed = True
            else:
                for idx in range(len(self.whole_revealed)):
                    self.whole_revealed[idx] = True
            return self.question_view()

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

    def question_view(self) -> CardView:
        current = self._question_block()
        return self._build_view(current_block=current, mask_context=True)

    def _question_block(self) -> str:
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

    def _build_view(self, current_block: str, mask_context: bool) -> CardView:
        blocks: List[ViewBlock] = []
        note_blocks = self.note_blocks or {
            (self.start_line, self.end_line): self.note_text
        }
        for line_range in sorted(note_blocks):
            start_line, _end_line = line_range
            if line_range == (self.start_line, self.end_line):
                blocks.append(
                    ViewBlock(
                        start_line=start_line,
                        text=current_block,
                        is_primary=True,
                    )
                )
                continue
            block = note_blocks[line_range]
            if mask_context:
                block = self._masked_context_block(block)
            blocks.append(
                ViewBlock(start_line=start_line, text=block, is_primary=False)
            )
        return CardView(blocks=blocks)

    def _masked_context_block(self, block: str) -> str:
        text_parts, clozes = parse_note_clozes(block, self.cloze_open, self.cloze_close)
        if not clozes:
            return block
        parts = [text_parts[0]]
        for idx, hidden in enumerate(clozes):
            parts.append(mask_hidden_text(hidden, self.mask_char))
            parts.append(text_parts[idx + 1])
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


@dataclass(frozen=True)
class ClozeParser(NoteParser):
    parser_id: ClassVar[str] = CLOZE_PARSER_ID
    priority: ClassVar[int] = 0
    reveal_mode: RevealMode
    cloze_open: str
    cloze_close: str
    mask_char: str

    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, int, str]]:
        cards: List[Tuple[int, int, str]] = []
        for line_number, line in enumerate(
            note_text.splitlines(keepends=True), start=1
        ):
            if line.strip():
                cards.append((line_number, line_number, line))
        return cards

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
        return ClozeCard(
            note_id=note_id,
            note_path=note_path,
            card_path=card_path,
            note_text=note_text,
            start_line=start_line,
            end_line=end_line,
            note_blocks=note_blocks,
            metadata=metadata,
            reveal_mode=self.reveal_mode,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
            mask_char=self.mask_char,
        )


def register_pack(registry: "ParserRegistry") -> None:
    registry.register(
        ClozeParser(
            reveal_mode=RevealMode.INCREMENTAL,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
    )
