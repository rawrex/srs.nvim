import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rich.markdown import Markdown

from tui import ReviewRenderer, SessionEntryUI, compose_view_text
from tests.setup_test_helpers import FakeConsole


class ComposeViewTextTest(unittest.TestCase):
    def test_separates_quote_blocks_when_showing_context(self) -> None:
        segments = [
            {"start": 1, "end": 2, "text": ">[!note]- Primary\n>Line 1\n"},
            {"start": 3, "end": 4, "text": ">[!note]- Context\n>Line 2\n"},
        ]

        text = compose_view_text(segments, (1, 2), show_context=True)

        self.assertEqual(">Primary <|---\n>\n>Line 1\n\n>Context\n>\n>Line 2", text)

    def test_hides_context_when_disabled(self) -> None:
        segments = [{"start": 1, "end": 1, "text": ">[!note]- Primary\n"}, {"start": 2, "end": 2, "text": "Context\n"}]

        text = compose_view_text(segments, (1, 1), show_context=False)

        self.assertEqual(">Primary <|---\n>", text)


class ReviewRendererImageTest(unittest.TestCase):
    def test_print_markdown_with_images_renders_markdown_when_chafa_unavailable(self) -> None:
        cases = ["![](diagram.png)\n", "![[diagram.png]]\n", "> ![[_Pasted image 20241023210525.png]]\n"]

        for text in cases:
            with self.subTest(text=text):
                console = FakeConsole()
                with patch("tui.shutil.which", return_value=None):
                    renderer = ReviewRenderer(  # type: ignore[arg-type]
                        console, show_context=True, media="/repo/.attachments"
                    )

                renderer.print_markdown_with_images(text)

                self.assertEqual(1, len(console.printed))
                printed_value, printed_kwargs = console.printed[0]
                self.assertIsInstance(printed_value, Markdown)
                self.assertEqual({}, printed_kwargs)

    def test_print_markdown_with_images_splits_inline_wiki_image_in_blockquote(self) -> None:
        console = FakeConsole()
        completed = Mock(returncode=0, stdout="ASCII ART\n")
        with (
            patch("tui.shutil.which", return_value="/usr/bin/chafa"),
            patch("tui.shutil.get_terminal_size", return_value=os.terminal_size((100, 40))),
            patch("tui.os.path.exists", return_value=True),
            patch("tui.subprocess.run", return_value=completed),
        ):
            renderer = ReviewRenderer(console, show_context=True, media="/repo/.attachments")  # type: ignore[arg-type]
            renderer.print_markdown_with_images(">[!note] Example ![[diagram.png]]\n")

        self.assertEqual(2, len(console.printed))
        self.assertIsInstance(console.printed[0][0], Markdown)
        self.assertEqual(
            ("ASCII ART\n\n", {"end": "", "markup": False, "highlight": False, "soft_wrap": True}), console.printed[1]
        )

    def test_print_markdown_with_images_renders_with_chafa_when_available(self) -> None:
        console = FakeConsole()
        completed = Mock(returncode=0, stdout="ASCII ART\n")
        with (
            patch("tui.shutil.which", return_value="/usr/bin/chafa"),
            patch("tui.shutil.get_terminal_size", return_value=os.terminal_size((100, 40))),
            patch("tui.os.path.exists", return_value=True),
            patch("tui.subprocess.run", return_value=completed) as run_mock,
        ):
            renderer = ReviewRenderer(console, show_context=True, media="/repo/.attachments")  # type: ignore[arg-type]
            renderer.print_markdown_with_images("![[diagram.png]]\n")

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


class SessionEntryUiTest(unittest.TestCase):
    def test_show_start_menu_returns_on_enter(self) -> None:
        console = FakeConsole()
        with patch.object(SessionEntryUI, "_load_session_logo", return_value="ASCII LOGO"):
            ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", return_value="\n"):
            ui.show_start_menu(due_cards_count=3, note_paths=[])

        self.assertIn(("ASCII LOGO", {"markup": False, "highlight": False}), console.printed)
        self.assertIn(("Due cards: 3", {}), console.printed)
        printed_lines = [value for value, _kwargs in console.printed if isinstance(value, str)]
        self.assertFalse(any(line.startswith("Estimated time:") for line in printed_lines))

    def test_show_start_menu_reprompts_on_non_enter_key(self) -> None:
        console = FakeConsole()
        ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", side_effect=["x", "\n"]):
            ui.show_start_menu(due_cards_count=1, note_paths=[])

        prompts = [value for value, _kwargs in console.printed if isinstance(value, str)]
        self.assertGreaterEqual(prompts.count("Press Enter to start"), 2)

    def test_show_start_menu_works_without_logo(self) -> None:
        console = FakeConsole()
        with patch("tui.SESSION_LOGO_PATH", Path("/nonexistent/session_logo.txt")):
            ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with patch("tui.os.system", return_value=0), patch("tui.read_single_key", return_value="\n"):
            ui.show_start_menu(due_cards_count=0, note_paths=[])

        self.assertIn(("Due cards: 0", {}), console.printed)
        self.assertEqual(("Due cards: 0", {}), console.printed[0])


if __name__ == "__main__":
    unittest.main()
