import os
import signal
import sys
import time
from typing import Dict

from fsrs import Rating
from rich.console import Console
from rich.markdown import Markdown

from review_card import ReviewCard


RATING_BUTTONS: Dict[Rating, str] = {
    Rating.Again: "n",
    Rating.Hard: "e",
    Rating.Good: "i",
    Rating.Easy: "o",
}

BUTTON_TO_RATING_BYTE: Dict[str, bytes] = {
    button: bytes([rating.value]) for rating, button in RATING_BUTTONS.items()
}


class ReviewUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

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
        prompt = "Rate [n=Again, e=Hard, i=Good, o=Easy]: "
        while True:
            print(prompt, end="", flush=True)
            key = read_single_key().lower()
            if maybe_suspend_for_key(key):
                print()
                continue
            try:
                rating = Rating.from_bytes(BUTTON_TO_RATING_BYTE[key])
            except (KeyError, ValueError):
                print()
                print("Invalid rating")
                continue

            print()
            print(f"Set rating: {rating.name}")
            time.sleep(0.5)
            return rating

    def _clear_screen(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")


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
