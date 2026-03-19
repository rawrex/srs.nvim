import json
import os
import tempfile
import unittest
from unittest.mock import patch

from reviewing.config import ReviewConfig
from reviewing.packs.cloze import ClozeCard
from reviewing.session import ReviewSession


class _DummyUI:
    pass


class ReviewSessionTest(unittest.TestCase):
    def test_load_due_cards_keeps_unclaimed_lines_as_context(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            note_path = os.path.join(repo_root, "note.md")
            os.makedirs(os.path.join(repo_root, ".srs"), exist_ok=True)
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("Prelude line\nTerm ~{hidden}\nTail line\n")

            with open(
                os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8"
            ) as handle:
                handle.write("'1','/note.md','cloze','2','2'\n")

            with open(
                os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump(ClozeCard.new_storage_dict(), handle)

            session = ReviewSession(
                repo_root=repo_root,
                ui=_DummyUI(),  # type: ignore[arg-type]
                config=ReviewConfig(),
            )

            with patch("reviewing.card.Card.is_due", return_value=True):
                cards = session._load_due_cards()

            self.assertEqual(1, len(cards))
            blocks = cards[0].note_blocks
            self.assertIn((1, 1), blocks)
            self.assertIn((2, 2), blocks)
            self.assertIn((3, 3), blocks)
            self.assertEqual("Prelude line\n", blocks[(1, 1)])
            self.assertIn("[a]", blocks[(2, 2)])
            self.assertEqual("Tail line\n", blocks[(3, 3)])


if __name__ == "__main__":
    unittest.main()
