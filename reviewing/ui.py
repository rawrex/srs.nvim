import os
import signal
import sys
from typing import Dict

from fsrs import Rating
from rich.console import Console
from rich.markdown import Markdown

from .card import REVEAL_ALL_LABEL, Card, CardView
from .config import ReviewConfig


class ReviewUI:
    def __init__(
        self,
        config: ReviewConfig,
        console: Console | None = None,
    ) -> None:
        self.console = console or Console()
        self.rating_buttons = config.rating_buttons
        self.show_context = config.show_context
        self.context_dim_style = config.context_dim_style
        self.button_to_rating_byte: Dict[str, bytes] = {
            button: bytes([rating.value])
            for rating, button in self.rating_buttons.items()
        }

    def print_message(self, message: str) -> None:
        self.console.print(message)

    def run_question_step(self, title: str, card: Card) -> CardView:
        current_view = card.question_view()
        while True:
            self._clear_screen()
            self.console.print(title)
            self._print_view(current_view)

            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            if key in {"\r", "\n"}:
                return card.reveal_for_label(REVEAL_ALL_LABEL) or current_view
            maybe_view = card.reveal_for_label(key)
            if maybe_view is not None:
                current_view = maybe_view

    def show_answer_step(self, title: str, view: CardView) -> None:
        self._clear_screen()
        self.console.print(title)
        self._print_view(view)

    def prompt_rating_step(self) -> Rating:
        prompt = self._rating_prompt()
        while True:
            print(prompt, end="", flush=True)
            key = read_single_key()
            if maybe_suspend_for_key(key):
                print()
                continue
            try:
                rating = Rating.from_bytes(self.button_to_rating_byte[key])
            except (KeyError, ValueError):
                print()
                print("Invalid rating")
                continue

            print()
            print(f"Set rating: {rating.name}")
            return rating

    def prompt_cloze_reveal(self, title: str, card: Card) -> CardView:
        return self.run_question_step(title, card)

    def show_rating_view(self, title: str, view: CardView) -> None:
        self.show_answer_step(title, view)

    def prompt_rating(self) -> Rating:
        return self.prompt_rating_step()

    def _clear_screen(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _rating_prompt(self) -> str:
        parts = [
            f"{self.rating_buttons[Rating.Again]}=Again",
            f"{self.rating_buttons[Rating.Hard]}=Hard",
            f"{self.rating_buttons[Rating.Good]}=Good",
            f"{self.rating_buttons[Rating.Easy]}=Easy",
        ]
        return f"Rate [{', '.join(parts)}]: "

    def _print_view(self, view: CardView) -> None:
        if not self.show_context:
            self.console.print(Markdown(view.primary_block().text.rstrip("\n")))
            return
        for block in view.blocks:
            style = None if block.is_primary else self.context_dim_style
            self.console.print(Markdown(block.text.rstrip("\n")), style=style)


def read_single_key() -> str:
    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            if key == "\x03":
                raise KeyboardInterrupt
            return key

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x03":
            raise KeyboardInterrupt
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def maybe_suspend_for_key(key: str) -> bool:
    if key != "\x1a":
        return False
    if hasattr(signal, "SIGTSTP"):
        os.kill(os.getpid(), signal.SIGTSTP)
    return True
