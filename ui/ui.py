import os
import re
import shutil
import signal
import subprocess
import sys

from fsrs import Rating
from rich.console import Console
from rich.markdown import Markdown

from card.card import Card, CardView
from core.config import ReviewConfig

WIKI_IMAGE_RE = re.compile(r"!\[\[[^\]]+\]\]")


class ReviewUI:
    def __init__(
        self,
        config: ReviewConfig,
        console: Console,
    ) -> None:
        self.console = console
        self.rating_buttons = config.rating_buttons
        self.show_context = config.show_context
        self.media = config.media
        self.chafa_path = shutil.which("chafa") if self.media is not None else None
        self.button_to_rating_byte: dict[str, bytes] = {
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
            self._print_view(card, current_view)

            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            if key in {"\r", "\n"}:
                return current_view
            maybe_view = card.reveal_for_label(key)
            if maybe_view is not None:
                current_view = maybe_view

    def show_answer_step(self, title: str, card: Card, view: CardView) -> None:
        self._clear_screen()
        self.console.print(title)
        self._print_view(card, view)

    def prompt_rating_step(self, default_rating: Rating | None) -> Rating:
        prompt = self._rating_prompt(default_rating)
        while True:
            self.console.print(prompt, end="", markup=False, highlight=False)
            key = read_single_key()
            if maybe_suspend_for_key(key):
                self.console.print("")
                continue
            if key in {"\r", "\n"} and default_rating is not None:
                self.console.print("")
                self.console.print(f"Set rating: {default_rating.name}")
                return default_rating
            try:
                rating = Rating.from_bytes(self.button_to_rating_byte[key])
            except (KeyError, ValueError):
                self.console.print("")
                self.console.print("Invalid rating")
                continue

            self.console.print("")
            self.console.print(f"Set rating: {rating.name}")
            return rating

    def _clear_screen(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _rating_prompt(self, default_rating: Rating | None) -> str:
        parts = [
            f"{self.rating_buttons[Rating.Again]}=Again",
            f"{self.rating_buttons[Rating.Hard]}=Hard",
            f"{self.rating_buttons[Rating.Good]}=Good",
            f"{self.rating_buttons[Rating.Easy]}=Easy",
        ]
        if default_rating is not None:
            parts.append(f"Enter={default_rating.name}")
        return f"Rate [{', '.join(parts)}]: "

    def _print_view(self, card: Card, view: CardView) -> None:
        primary_block = self._mark_active_line(view.primary_block().text)

        if not self.show_context:
            self._print_markdown_with_images(primary_block.rstrip("\n"))
            return

        rendered_blocks = [
            primary_block if block.is_primary else block.text for block in view.blocks
        ]
        if not rendered_blocks:
            rendered_blocks = [primary_block]
        merged_text = "\n\n".join(block.rstrip("\n") for block in rendered_blocks)
        primary_block_index = next(
            (idx for idx, block in enumerate(view.blocks) if block.is_primary),
            0,
        )
        target_line_index = self._line_index_for_block(
            rendered_blocks, primary_block_index
        )
        viewport_text = self._center_viewport_on_line(
            merged_text.rstrip("\n"),
            target_line_index,
        )
        self._print_markdown_with_images(viewport_text)

    def _line_index_for_block(self, blocks: list[str], block_index: int) -> int:
        line_index = 0
        for idx, block in enumerate(blocks):
            if idx == block_index:
                return line_index
            line_index += len(block.rstrip("\n").splitlines())
            if idx < len(blocks) - 1:
                line_index += 1
        return line_index

    def _center_viewport_on_line(self, text: str, target_line_index: int) -> str:
        lines = text.splitlines(keepends=True)
        if not lines:
            return text

        terminal_size = shutil.get_terminal_size()
        viewport_height = max(1, terminal_size.lines - 2)
        if len(lines) <= viewport_height:
            return text

        clamped_target = min(max(0, target_line_index), len(lines) - 1)
        start = max(0, clamped_target - ((viewport_height - 1) // 2))
        end = start + viewport_height
        if end > len(lines):
            end = len(lines)
            start = max(0, end - viewport_height)
        return "".join(lines[start:end]).rstrip("\n")

    def _print_markdown_with_images(self, text: str) -> None:
        markdown_lines: list[str] = []

        def flush_markdown_lines() -> None:
            if not markdown_lines:
                return
            markdown = "".join(markdown_lines).rstrip("\n")
            self.console.print(
                Markdown(self._preserve_blockquote_line_breaks(markdown))
            )
            markdown_lines.clear()

        for line in self._split_inline_wiki_images(text):
            if image_reference := self._extract_image_reference_from_line(line):
                if rendered_image := self._render_image(image_reference):
                    flush_markdown_lines()
                    image_block = f"{rendered_image.rstrip('\n')}\n\n"
                    self.console.print(
                        image_block,
                        end="",
                        markup=False,
                        highlight=False,
                        soft_wrap=True,
                    )
                    continue
            markdown_lines.append(line)
        flush_markdown_lines()

    def _split_inline_wiki_images(self, text: str) -> list[str]:
        lines: list[str] = []
        for line in text.splitlines(keepends=True):
            newline = "\n" if line.endswith("\n") else ""
            content = line[:-1] if newline else line
            prefix_match = re.match(r"^(\s*(?:>\s*)*)", content)
            prefix = prefix_match.group(1) if prefix_match else ""
            remainder = content[len(prefix) :]
            images = WIKI_IMAGE_RE.findall(remainder)
            if not images:
                lines.append(line)
                continue

            text_without_images = WIKI_IMAGE_RE.sub("", remainder).strip()
            if text_without_images:
                lines.append(f"{prefix}{text_without_images}{newline}")
            for image in images:
                lines.append(f"{prefix}{image}{newline}")
        return lines

    def _preserve_blockquote_line_breaks(self, text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if not line.endswith("\n"):
                lines.append(line)
                continue
            if re.match(r"^\s*>\s*\S", line):
                lines.append(f"{line[:-1]}  \n")
                continue
            lines.append(line)
        return "".join(lines)

    def _extract_image_reference_from_line(self, line: str) -> str | None:
        if image_match := re.match(r"^\s*(?:>\s*)*!\[\[([^\]]+)\]\]\s*$", line):
            return image_match.group(1).strip()
        return None

    def _render_image(self, image_reference: str) -> str | None:
        if self.media is None or self.chafa_path is None:
            return None

        filename = os.path.basename(image_reference)
        if not filename:
            return None
        path = os.path.join(self.media, filename)
        if not os.path.exists(path):
            return None

        terminal_size = shutil.get_terminal_size(fallback=(120, 40))
        render_width = max(40, terminal_size.columns - 2)
        render_height = max(16, terminal_size.lines // 2)

        result = subprocess.run(
            [
                self.chafa_path,
                "--size",
                f"{render_width}x{render_height}",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _mark_active_line(self, text: str) -> str:
        mark = "<|---"
        first_line, sep, rest = text.partition("\n")
        return f"{first_line} {mark}{sep}{rest}"


class SessionEntryUI:
    def __init__(self, console: Console) -> None:
        self.console = console

    def show_start_menu(
        self,
        due_cards_count: int,
        estimated_minutes: int | None,
    ) -> None:
        while True:
            self._clear_screen()
            self.console.print("Session")
            self.console.print(f"Due cards: {due_cards_count}")
            if estimated_minutes:
                self.console.print(f"Estimated time: {estimated_minutes} min")
            self.console.print("")
            self.console.print("Press Enter to start")

            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            if key in {"\r", "\n"}:
                return

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
