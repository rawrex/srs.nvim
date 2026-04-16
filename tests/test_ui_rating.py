import os
import unittest
from unittest.mock import Mock, patch

from fsrs import Rating
from rich.markdown import Markdown

from core.card import CardView, ViewBlock
from core.config import ReviewConfig
from core.ui import ReviewUI, SessionEntryUI
from tests.setup_test_helpers import FakeConsole


class ReviewUiRatingTest(unittest.TestCase):
    def test_prompt_rating_step_accepts_enter_for_suggested_rating(self) -> None:
        console = FakeConsole()
        ui = ReviewUI(config=ReviewConfig(), console=console)  # type: ignore[arg-type]

        with patch("core.ui.read_single_key", return_value="\n"):
            rating = ui.rating_step(default_rating=Rating.Good)

        self.assertEqual(Rating.Good, rating)
        self.assertIn(("Set rating: Good", {}), console.printed)

    def test_prompt_rating_step_keeps_enter_invalid_without_suggestion(self) -> None:
        console = FakeConsole()
        ui = ReviewUI(config=ReviewConfig(), console=console)  # type: ignore[arg-type]

        with patch("core.ui.read_single_key", side_effect=["\n", "i"]):
            rating = ui.rating_step(default_rating=None)

        self.assertEqual(Rating.Good, rating)
        self.assertIn(("Invalid rating", {}), console.printed)

    def test_print_markdown_with_images_renders_markdown_when_chafa_unavailable(self) -> None:
        cases = [
            "![](diagram.png)\n",
            "![[diagram.png]]\n",
            "> ![[_Pasted image 20241023210525.png]]\n",
        ]

        for text in cases:
            with self.subTest(text=text):
                console = FakeConsole()
                with patch("core.ui.shutil.which", return_value=None):
                    ui = ReviewUI(config=ReviewConfig(media="/repo/.attachments"), console=console)  # type: ignore[arg-type]

                ui._print_markdown_with_images(text)

                self.assertEqual(1, len(console.printed))
                printed_value, printed_kwargs = console.printed[0]
                self.assertIsInstance(printed_value, Markdown)
                self.assertEqual({}, printed_kwargs)

    def test_print_markdown_with_images_splits_inline_wiki_image_in_blockquote(self) -> None:
        console = FakeConsole()
        completed = Mock(returncode=0, stdout="ASCII ART\n")
        with (
            patch("core.ui.shutil.which", return_value="/usr/bin/chafa"),
            patch("core.ui.shutil.get_terminal_size", return_value=os.terminal_size((100, 40))),
            patch("core.ui.os.path.exists", return_value=True),
            patch("core.ui.subprocess.run", return_value=completed),
        ):
            ui = ReviewUI(config=ReviewConfig(media="/repo/.attachments"), console=console)  # type: ignore[arg-type]
            ui._print_markdown_with_images(">[!note] Example ![[diagram.png]]\n")

        self.assertEqual(2, len(console.printed))
        self.assertIsInstance(console.printed[0][0], Markdown)
        self.assertEqual(
            ("ASCII ART\n\n", {"end": "", "markup": False, "highlight": False, "soft_wrap": True}), console.printed[1]
        )

    def test_print_markdown_with_images_renders_with_chafa_when_available(self) -> None:
        console = FakeConsole()
        completed = Mock(returncode=0, stdout="ASCII ART\n")
        with (
            patch("core.ui.shutil.which", return_value="/usr/bin/chafa"),
            patch("core.ui.shutil.get_terminal_size", return_value=os.terminal_size((100, 40))),
            patch("core.ui.os.path.exists", return_value=True),
            patch("core.ui.subprocess.run", return_value=completed) as run_mock,
        ):
            ui = ReviewUI(config=ReviewConfig(media="/repo/.attachments"), console=console)  # type: ignore[arg-type]
            ui._print_markdown_with_images("![[diagram.png]]\n")

        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertEqual("/usr/bin/chafa", command[0])
        self.assertEqual("--size", command[1])
        self.assertRegex(command[2], r"^\d+x\d+$")
        self.assertEqual("/repo/.attachments/diagram.png", command[3])
        self.assertEqual({"capture_output": True, "text": True, "check": False}, run_mock.call_args.kwargs)
        self.assertIn(
            ("ASCII ART\n\n", {"end": "", "markup": False, "highlight": False, "soft_wrap": True}), console.printed
        )

    def test_print_view_separates_quote_blocks_when_showing_context(self) -> None:
        ui = ReviewUI(config=ReviewConfig(show_context=True), console=FakeConsole())  # type: ignore[arg-type]
        captured: list[str] = []
        ui._print_markdown_with_images = captured.append  # type: ignore[method-assign]

        view = CardView(
            blocks=[
                ViewBlock(start_line=1, text=">[!note]- Primary\n>Line 1\n", is_primary=True),
                ViewBlock(start_line=3, text=">[!note]- Context\n>Line 2\n", is_primary=False),
            ]
        )

        card = Mock()
        card.context = {
            (1, 2): ">[!note]- Primary\n>Line 1\n",
            (3, 4): ">[!note]- Context\n>Line 2\n",
        }
        card.index_entry = Mock(start_line=1, end_line=2)

        ui._print_view(card=card, view=view)

        self.assertEqual([">[!note]- Primary <|---\n>Line 1\n\n>[!note]- Context\n>Line 2"], captured)

class SessionEntryUiTest(unittest.TestCase):
    def test_show_start_menu_returns_on_enter(self) -> None:
        console = FakeConsole()
        with patch.object(SessionEntryUI, "_load_session_logo", return_value="ASCII LOGO"):
            ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with patch("core.ui.os.system", return_value=0), patch("core.ui.read_single_key", return_value="\n"):
            ui.show_start_menu(due_cards_count=3)

        self.assertIn(("ASCII LOGO", {"markup": False, "highlight": False}), console.printed)
        self.assertIn(("Due cards: 3", {}), console.printed)
        printed_lines = [value for value, _kwargs in console.printed if isinstance(value, str)]
        self.assertFalse(any(line.startswith("Estimated time:") for line in printed_lines))

    def test_show_start_menu_reprompts_on_non_enter_key(self) -> None:
        console = FakeConsole()
        ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with patch("core.ui.os.system", return_value=0), patch("core.ui.read_single_key", side_effect=["x", "\n"]):
            ui.show_start_menu(due_cards_count=1)

        prompts = [value for value, _kwargs in console.printed if isinstance(value, str)]
        self.assertGreaterEqual(prompts.count("Press Enter to start"), 2)
