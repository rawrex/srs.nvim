import os
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from fsrs import Rating
from rich.markdown import Markdown

from card.card import CardView, ViewBlock
from core.config import ReviewConfig
from ui.ui import ReviewUI, SessionEntryUI


class _FakeConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[object, dict[str, object]]] = []

    def print(self, value: object = "", *args: object, **kwargs: object) -> None:
        self.printed.append((value, dict(kwargs)))


class ReviewUiRatingTest(unittest.TestCase):
    def test_prompt_rating_step_accepts_enter_for_suggested_rating(self) -> None:
        console = _FakeConsole()
        ui = ReviewUI(config=ReviewConfig(), console=console)  # type: ignore[arg-type]

        with patch("ui.ui.read_single_key", return_value="\n"):
            rating = ui.prompt_rating_step(default_rating=Rating.Good)

        self.assertEqual(Rating.Good, rating)
        self.assertIn(
            ("Set rating: Good", {}),
            console.printed,
        )

    def test_prompt_rating_step_keeps_enter_invalid_without_suggestion(self) -> None:
        console = _FakeConsole()
        ui = ReviewUI(config=ReviewConfig(), console=console)  # type: ignore[arg-type]

        with patch("ui.ui.read_single_key", side_effect=["\n", "i"]):
            rating = ui.prompt_rating_step()

        self.assertEqual(Rating.Good, rating)
        self.assertIn(("Invalid rating", {}), console.printed)

    def test_print_markdown_with_images_leaves_standard_markdown_image_unchanged(
        self,
    ) -> None:
        console = _FakeConsole()
        with patch("ui.ui.shutil.which", return_value=None):
            ui = ReviewUI(
                config=ReviewConfig(attachments_directory="/repo/.attachments"),
                console=console,
            )  # type: ignore[arg-type]

        ui._print_markdown_with_images("![](diagram.png)\n")

        self.assertEqual(1, len(console.printed))
        printed_value, printed_kwargs = console.printed[0]
        self.assertIsInstance(printed_value, Markdown)
        self.assertEqual({}, printed_kwargs)

    def test_print_markdown_with_images_supports_wiki_image_syntax(self) -> None:
        console = _FakeConsole()
        with patch("ui.ui.shutil.which", return_value=None):
            ui = ReviewUI(
                config=ReviewConfig(attachments_directory="/repo/.attachments"),
                console=console,
            )  # type: ignore[arg-type]

        ui._print_markdown_with_images("![[diagram.png]]\n")

        self.assertEqual(1, len(console.printed))
        printed_value, printed_kwargs = console.printed[0]
        self.assertIsInstance(printed_value, Markdown)
        self.assertEqual({}, printed_kwargs)

    def test_print_markdown_with_images_supports_wiki_image_in_blockquote(self) -> None:
        console = _FakeConsole()
        with patch("ui.ui.shutil.which", return_value=None):
            ui = ReviewUI(
                config=ReviewConfig(attachments_directory="/repo/.attachments"),
                console=console,
            )  # type: ignore[arg-type]

        ui._print_markdown_with_images("> ![[_Pasted image 20241023210525.png]]\n")

        self.assertEqual(1, len(console.printed))
        printed_value, printed_kwargs = console.printed[0]
        self.assertIsInstance(printed_value, Markdown)
        self.assertEqual({}, printed_kwargs)

    def test_print_markdown_with_images_renders_with_chafa_when_available(self) -> None:
        console = _FakeConsole()
        completed = Mock(returncode=0, stdout="ASCII ART\n")
        with (
            patch("ui.ui.shutil.which", return_value="/usr/bin/chafa"),
            patch(
                "ui.ui.shutil.get_terminal_size",
                return_value=os.terminal_size((100, 40)),
            ),
            patch("ui.ui.os.path.exists", return_value=True),
            patch("ui.ui.subprocess.run", return_value=completed) as run_mock,
        ):
            ui = ReviewUI(
                config=ReviewConfig(attachments_directory="/repo/.attachments"),
                console=console,
            )  # type: ignore[arg-type]
            ui._print_markdown_with_images("![[diagram.png]]\n")

        run_mock.assert_called_once_with(
            [
                "/usr/bin/chafa",
                "--size",
                "98x20",
                "/repo/.attachments/diagram.png",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn(
            (
                "ASCII ART\n\n",
                {
                    "end": "",
                    "markup": False,
                    "highlight": False,
                    "soft_wrap": True,
                },
            ),
            console.printed,
        )

    def test_print_view_separates_quote_blocks_when_showing_context(self) -> None:
        ui = ReviewUI(config=ReviewConfig(show_context=True), console=_FakeConsole())  # type: ignore[arg-type]
        captured: list[str] = []
        ui._print_markdown_with_images = captured.append  # type: ignore[method-assign]

        view = CardView(
            blocks=[
                ViewBlock(
                    start_line=1,
                    text=">[!note]- Primary\n>Line 1\n",
                    is_primary=True,
                ),
                ViewBlock(
                    start_line=3,
                    text=">[!note]- Context\n>Line 2\n",
                    is_primary=False,
                ),
            ]
        )

        ui._print_view(card=Mock(), view=view)

        self.assertEqual(
            [
                ">[!note]- Primary <|---\n>Line 1\n\n>[!note]- Context\n>Line 2",
            ],
            captured,
        )


class SessionEntryUiTest(unittest.TestCase):
    def test_show_start_menu_returns_on_enter(self) -> None:
        console = _FakeConsole()
        ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with (
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", return_value="\n"),
        ):
            ui.show_start_menu(due_cards_count=3)

        self.assertIn(("Session", {}), console.printed)
        self.assertIn(("Due cards: 3", {}), console.printed)
        self.assertNotIn(("Estimated time: n/a", {}), console.printed)

    def test_show_start_menu_reprompts_on_non_enter_key(self) -> None:
        console = _FakeConsole()
        ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with (
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", side_effect=["x", "\n"]),
        ):
            ui.show_start_menu(due_cards_count=1)

        prompts = [
            value for value, _kwargs in console.printed if isinstance(value, str)
        ]
        self.assertGreaterEqual(prompts.count("Press Enter to start"), 2)

    def test_show_start_menu_shows_estimated_minutes_when_provided(self) -> None:
        console = _FakeConsole()
        ui = SessionEntryUI(console=console)  # type: ignore[arg-type]

        with (
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", return_value="\n"),
        ):
            ui.show_start_menu(due_cards_count=3, estimated_minutes=7)

        self.assertIn(("Estimated time: 7 min", {}), console.printed)


if __name__ == "__main__":
    unittest.main()
