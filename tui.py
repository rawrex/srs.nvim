#!/usr/bin/env python3
# ruff: noqa: E402
"""Terminal UI client for the SRS backend.

Run directly from the repository root:

    python3 tui.py

Spawns the shared backend (``core/rpc.py``) as a subprocess and drives it over
the JSON-line transport, exactly like the nvim plugin does. All review-flow
state (reveal/pause/next/rating) lives in the backend; this client only keeps
enough local state to render and forwards key events.

Everything terminal-specific lives here: rich markdown, Obsidian callout
rewriting, the active-line marker, inline wiki-image rendering via ``chafa`` and
the start menu. An optional ``session_logo.txt`` next to this file is shown on
the start screen when present.
"""

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.markdown import Markdown

from core import util
from core.config import ReviewConfig, load_review_config
from core.protocol import JsonLineTransport

WIKI_IMAGE_RE = re.compile(r"!\[\[[^\]]+\]\]")
CALLOUT_HEADING_RE = re.compile(r"^>\s*\[!(?P<kind>[^\]]+)\](?:[+-])?\s*(?P<title>.*)$")
SESSION_LOGO_PATH = Path(__file__).with_name("session_logo.txt")
BACKEND_SCRIPT = PROJECT_ROOT / "core" / "rpc.py"


# Rendering primitives ------------------------------------------------------


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def mark_active_line(text: str) -> str:
    mark = "<|---"
    first_line, sep, rest = text.partition("\n")
    return f"{first_line} {mark}{sep}{rest}"


def _pad_to_span(text: str, span: int) -> str:
    missing = span - len(text.splitlines())
    return text + "\n" * missing if missing > 0 else text


def _format_callout_heading(text: str) -> str:
    if lines := text.splitlines(keepends=True):
        if heading := CALLOUT_HEADING_RE.match(lines[0].rstrip("\n")):
            newline = "\n" if lines[0].endswith("\n") else ""
            rendered_heading = f">{heading.group('title')}{newline}"
            return "".join([rendered_heading, ">\n", *lines[1:]])
    return text


def terminalize_block(text: str, span: int) -> str:
    return _format_callout_heading(_pad_to_span(text, span))


def compose_view_text(segments: list[dict], active: tuple[int, int], show_context: bool) -> str:
    rendered_blocks: list[str] = []
    primary_block: str | None = None

    for segment in segments:
        line_range = (segment["start"], segment["end"])
        span = segment["end"] - segment["start"] + 1
        if line_range == active:
            primary_block = mark_active_line(terminalize_block(segment["text"], span))
            rendered_blocks.append(primary_block)
        else:
            rendered_blocks.append(terminalize_block(segment["text"], span))

    if primary_block is None:
        return ""
    if not show_context:
        return primary_block.rstrip("\n")
    return "\n\n".join(block.rstrip("\n") for block in rendered_blocks).rstrip("\n")


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


# Rendering -----------------------------------------------------------------


class SessionEntryUI:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.session_logo = self._load_session_logo()

    def show_start_menu(self, due_cards_count: int, note_paths: list[str]) -> None:
        while True:
            clear_screen()
            if self.session_logo:
                self.console.print(self.session_logo, markup=False, highlight=False)
                self.console.print("")
            self.console.print(f"Due cards: {due_cards_count}")
            self.console.print("")
            for path in note_paths:
                self.console.print(f"  {path}")
            self.console.print("")
            self.console.print("Press Enter to start")

            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            if key in {"\r", "\n"}:
                return

    def _load_session_logo(self) -> str:
        if SESSION_LOGO_PATH.exists():
            return SESSION_LOGO_PATH.read_text(encoding="utf-8").rstrip("\n")
        return ""


class ReviewRenderer:
    """Turns protocol messages into terminal output."""

    def __init__(self, console: Console, *, show_context: bool, media: str | None = None) -> None:
        self.console = console
        self.show_context = show_context
        self.media = media
        self.chafa_path = shutil.which("chafa") if media is not None else None
        self.entry_ui = SessionEntryUI(console)

    # Basic output ---------------------------------------------------------

    def clear(self) -> None:
        clear_screen()

    def print_message(self, message: str) -> None:
        self.console.print(message)

    def print_title(self, title: str) -> None:
        self.console.print(title)

    def print_blank_line(self) -> None:
        self.console.print("")

    def print_rating_prompt(self, prompt: str) -> None:
        self.console.print(prompt, end="", markup=False, highlight=False)

    def print_set_rating(self, name: str) -> None:
        self.console.print(f"Set rating: {name}")

    def print_invalid_rating(self) -> None:
        self.console.print("Invalid rating")

    # Review steps ---------------------------------------------------------

    def intro(self, total: int, note_paths: list[str]) -> None:
        self.entry_ui.show_start_menu(total, note_paths)

    def print_view(self, render: dict) -> None:
        active = (render["active"]["start"], render["active"]["end"])
        text = compose_view_text(render["segments"], active, self.show_context)
        self.print_markdown_with_images(text)

    # Images ---------------------------------------------------------------

    def print_markdown_with_images(self, text: str) -> None:
        markdown_lines: list[str] = []

        def flush_markdown_lines() -> None:
            if not markdown_lines:
                return
            markdown = "".join(markdown_lines).rstrip("\n")
            self.console.print(Markdown(self._preserve_blockquote_line_breaks(markdown)))
            markdown_lines.clear()

        for line in self._split_inline_wiki_images(text):
            if image_reference := self._extract_image_reference_from_line(line):
                if rendered_image := self._render_image(image_reference):
                    flush_markdown_lines()
                    image_block = f"{rendered_image.rstrip('\n')}\n\n"
                    self.console.print(image_block, end="", markup=False, highlight=False, soft_wrap=True)
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
            [self.chafa_path, "--size", f"{render_width}x{render_height}", path],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout


# Client --------------------------------------------------------------------


class TuiClient:
    def __init__(self, transport: JsonLineTransport, renderer: ReviewRenderer) -> None:
        self.transport = transport
        self.renderer = renderer
        self.mode = "idle"
        self.paused = False
        self.suggested: str | None = None
        self.choices: list[dict[str, str]] = []
        self.button_to_rating: dict[str, str] = {}

    def run(self) -> int:
        while True:
            message = self.transport.receive()
            if message is None:
                return 0
            self._handle(message)

    def _handle(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "notice":
            self.renderer.print_message(message.get("text", ""))
            if message.get("level") == "error" and self.mode == "rating":
                self._rating_step()
        elif kind == "intro":
            self.mode = "intro"
            self.renderer.intro(message.get("due", 0), message.get("notes", []))
            self.transport.send({"type": "start"})
        elif kind == "render":
            self.mode = message.get("state", "")
            self._render(message)
        elif kind == "rating":
            self.mode = "rating"
            self.suggested = message.get("suggested")
            self.choices = message.get("choices") or []
            self.button_to_rating = {choice["key"]: choice["name"] for choice in self.choices}
            self._rating_step()

    # Rendering ------------------------------------------------------------

    def _render(self, message: dict[str, Any]) -> None:
        state = message.get("state")
        self.renderer.clear()
        self.renderer.print_blank_line()
        title = self._format_title(message.get("card") or {}, state, message.get("duration_s"))
        if state == "question" and self.paused:
            title = title + " (PAUSED)"
        self.renderer.print_title(title)
        self.renderer.print_view(message)
        if state == "question":
            self._question_step()

    @staticmethod
    def _format_title(card: dict[str, Any], state: str | None, duration_s: float | None) -> str:
        note = card.get("note", "")
        name = os.path.basename(note) if note else ""
        title = f"[{card.get('index')}/{card.get('total')}] {name}"
        if state == "answer" and duration_s is not None:
            title += f" — answer ({duration_s:.1f}s)"
        return title

    def _question_step(self) -> None:
        key = self._read_key()
        if key == " ":
            self.paused = not self.paused
            self.transport.send({"type": "pause"})
        elif key == "\x1b":
            self.transport.send({"type": "skip"})
        elif key in {"\r", "\n"}:
            self.transport.send({"type": "next"})
        else:
            self.transport.send({"type": "reveal", "label": key})

    def _rating_step(self) -> None:
        prompt = self._rating_prompt()
        while True:
            self.renderer.print_rating_prompt(prompt)
            key = self._read_key()
            if key in {"\r", "\n"} and self.suggested is not None:
                self.renderer.print_blank_line()
                self.renderer.print_set_rating(self.suggested)
                self.transport.send({"type": "rate", "rating": self.suggested})
                return
            rating = self.button_to_rating.get(key)
            if rating is None:
                self.renderer.print_blank_line()
                self.renderer.print_invalid_rating()
                continue
            self.renderer.print_blank_line()
            self.renderer.print_set_rating(rating)
            self.transport.send({"type": "rate", "rating": rating})
            return

    def _rating_prompt(self) -> str:
        parts = [f"{choice['key']}={choice['name']}" for choice in self.choices]
        if self.suggested is not None:
            parts.append(f"Enter={self.suggested}")
        return f"Rate [{', '.join(parts)}]: "

    def _read_key(self) -> str:
        while True:
            key = read_single_key()
            if maybe_suspend_for_key(key):
                continue
            return key


# Entrypoint ----------------------------------------------------------------


def main() -> int:
    try:
        util.init_runtime_context(os.getcwd())
        repo_root = util._RUNTIME_CONTEXT.repo_root_path
        if not repo_root:
            print("Not inside a git repository.")
            return 1
        config = load_review_config()
        return run(console=Console(), config=config, repo_root=repo_root)
    except KeyboardInterrupt:
        print("\nExit.")
        return 0


def run(*, console: Console, config: ReviewConfig, repo_root: str) -> int:
    process = spawn_backend(repo_root)
    try:
        transport = JsonLineTransport(process.stdout, process.stdin)
        renderer = ReviewRenderer(console, show_context=config.show_context, media=config.media)
        client_code = TuiClient(transport, renderer).run()
        process.wait()
        return process.returncode if process.returncode is not None else client_code
    finally:
        terminate_backend(process)


def spawn_backend(repo_root: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(BACKEND_SCRIPT)],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def terminate_backend(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
