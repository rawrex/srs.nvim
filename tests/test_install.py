import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from setup.install import find_repeat_tracked_paths
from tests.setup_test_helpers import runtime_context


class InstallDiscoveryTest(unittest.TestCase):
    @staticmethod
    def _find_repeat_tracked_paths(repo_dir: Path) -> list[str]:
        with patch("core.util._RUNTIME_CONTEXT", runtime_context(str(repo_dir)), create=True):
            return find_repeat_tracked_paths()

    def test_find_repeat_tracked_paths_returns_empty_without_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "notes.md").write_text("~{a}\n", encoding="utf-8")

            self.assertEqual([], self._find_repeat_tracked_paths(repo_dir))

    def test_find_repeat_tracked_paths_includes_recursive_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            notes_dir = repo_dir / "notes"
            nested_dir = notes_dir / "nested"
            notes_dir.mkdir()
            nested_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (notes_dir / "top.md").write_text("~{a}\n", encoding="utf-8")
            (nested_dir / "deep.md").write_text("~{b}\n", encoding="utf-8")
            (repo_dir / "outside.md").write_text("~{skip}\n", encoding="utf-8")

            self.assertEqual(["/notes/nested/deep.md", "/notes/top.md"], self._find_repeat_tracked_paths(repo_dir))

    def test_find_repeat_tracked_paths_deduplicates_nested_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            notes_dir = repo_dir / "notes"
            nested_dir = notes_dir / "nested"
            notes_dir.mkdir()
            nested_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (nested_dir / ".repeat").write_text("", encoding="utf-8")
            (nested_dir / "deep.md").write_text("~{b}\n", encoding="utf-8")

            self.assertEqual(["/notes/nested/deep.md"], self._find_repeat_tracked_paths(repo_dir))

    def test_find_repeat_tracked_paths_skips_git_and_srs_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            notes_dir = repo_dir / "notes"
            git_hidden_dir = notes_dir / ".git"
            srs_hidden_dir = notes_dir / ".srs"
            notes_dir.mkdir()
            git_hidden_dir.mkdir()
            srs_hidden_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (notes_dir / "ok.md").write_text("~{ok}\n", encoding="utf-8")
            (git_hidden_dir / "ignored.md").write_text("~{git}\n", encoding="utf-8")
            (srs_hidden_dir / "ignored.md").write_text("~{srs}\n", encoding="utf-8")

            self.assertEqual(["/notes/ok.md"], self._find_repeat_tracked_paths(repo_dir))

    def test_find_repeat_tracked_paths_honors_norepeat_subtree_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            notes_dir = repo_dir / "notes"
            skip_dir = notes_dir / "skip"
            notes_dir.mkdir()
            skip_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (skip_dir / ".norepeat").write_text("", encoding="utf-8")
            (notes_dir / "keep.md").write_text("~{ok}\n", encoding="utf-8")
            (skip_dir / "drop.md").write_text("~{no}\n", encoding="utf-8")

            self.assertEqual(["/notes/keep.md"], self._find_repeat_tracked_paths(repo_dir))

    def test_find_repeat_tracked_paths_allows_repeat_inside_norepeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            notes_dir = repo_dir / "notes"
            skip_dir = notes_dir / "skip"
            reenabled_dir = skip_dir / "reenabled"
            notes_dir.mkdir()
            skip_dir.mkdir()
            reenabled_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (skip_dir / ".norepeat").write_text("", encoding="utf-8")
            (reenabled_dir / ".repeat").write_text("", encoding="utf-8")
            (notes_dir / "keep.md").write_text("~{ok}\n", encoding="utf-8")
            (skip_dir / "drop.md").write_text("~{no}\n", encoding="utf-8")
            (reenabled_dir / "again.md").write_text("~{yes}\n", encoding="utf-8")

            self.assertEqual(
                ["/notes/keep.md", "/notes/skip/reenabled/again.md"], self._find_repeat_tracked_paths(repo_dir)
            )
