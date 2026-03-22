import unittest
from unittest.mock import patch

from fsrs import Rating

from core.config import ReviewConfig
from ui.ui import ReviewUI


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


if __name__ == "__main__":
    unittest.main()
