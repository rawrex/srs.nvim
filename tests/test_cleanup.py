import unittest
from unittest.mock import Mock, patch

import setup.cleanup as cleanup
from core.index.index import (
    IndexCleanupApplyResult,
    IndexCleanupReport,
    IndexInvalidRow,
)
from setup.common import RepoContext


class CleanupCliTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        with (
            patch("setup.cleanup.common.resolve_repo_context", return_value=None),
            patch("builtins.print") as print_mock,
        ):
            code = cleanup.main()

        self.assertEqual(1, code)
        print_mock.assert_called_once_with("Not inside a git repository.")

    def test_main_prompts_and_applies_selected_actions(self) -> None:
        context = RepoContext(repo_root="/repo", git_dir="/repo/.git")
        report = IndexCleanupReport(
            missing_tracked_paths=["/note.md"],
            missing_rows_by_path={"/note.md": [("cloze", 1, 1)]},
            invalid_rows=[
                IndexInvalidRow(
                    note_id="10",
                    path="/note.md",
                    parser_id="cloze",
                    start_line=9,
                    end_line=9,
                    reason="missing_parser_row",
                )
            ],
            orphan_card_ids=["999"],
        )
        index = Mock()
        index.build_cleanup_report.return_value = report
        index.apply_cleanup_report.return_value = IndexCleanupApplyResult(
            added_rows=1,
            removed_invalid_rows=0,
            removed_orphan_cards=1,
        )

        with (
            patch("setup.cleanup.common.resolve_repo_context", return_value=context),
            patch("setup.cleanup.os.path.exists", return_value=True),
            patch("setup.cleanup.load_review_config", return_value=Mock()),
            patch("setup.cleanup.build_parser_registry", return_value=Mock()),
            patch("setup.cleanup.Index", return_value=index),
            patch(
                "setup.cleanup.find_repeat_tracked_paths",
                return_value=["/note.md"],
            ),
            patch("builtins.input", side_effect=["y", "n", "y"]),
        ):
            code = cleanup.main()

        self.assertEqual(0, code)
        index.apply_cleanup_report.assert_called_once_with(
            report,
            add_missing=True,
            remove_invalid=False,
            remove_orphan_cards=True,
        )


if __name__ == "__main__":
    unittest.main()
