import unittest
from unittest.mock import patch

from fsrs import Rating

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


if __name__ == "__main__":
    unittest.main()
