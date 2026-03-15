import os
import signal
import sys
from typing import Dict

from fsrs import Rating
from rich.console import Console
from rich.markdown import Markdown

from .card import ReviewCard


class ReviewUI:
    def __init__(
        self,
        rating_buttons: Dict[Rating, str],
        console: Console | None = None,
    ) -> None:
        self.console = console or Console()
        self.rating_buttons = rating_buttons
        self.button_to_rating_byte: Dict[str, bytes] = {
            button: bytes([rating.value])
            for rating, button in self.rating_buttons.items()
        }

    def print_message(self, message: str) -> None:
        self.console.print(message)

    def prompt_cloze_reveal(self, title: str, card: ReviewCard) -> None:
        while True:
            self._clear_screen()
            self.console.print(title)
            self.console.print(Markdown(card.question_view().rstrip("\n")))

            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            if key in {"\r", "\n"}:
                return
            card.reveal_for_label(key)

    def show_answer(self, title: str, answer_view: str) -> None:
        self._clear_screen()
        self.console.print(title)
        self.console.print(Markdown(answer_view.rstrip("\n")))

    def prompt_rating(self) -> Rating:
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
