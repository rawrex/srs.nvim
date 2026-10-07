import unittest
from unittest.mock import Mock, patch

import core.optimize as optimize
from core.config import ReviewConfig
from core.optimization import SKIPPED_INSUFFICIENT_DATA, SKIPPED_NO_LOGS, OptimizationReport
from tests.setup_test_helpers import runtime_context, temporary_session_repo


def _default_parameters() -> tuple[float, ...]:
    return tuple(ReviewConfig().build_scheduler().parameters)


def _changed_report() -> OptimizationReport:
    parameters = list(_default_parameters())
    parameters[0] = 0.5
    return OptimizationReport(card_count=2, review_log_count=10, parameters=tuple(parameters), changed=True)


class OptimizeCliTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        runtime = Mock(repo_root_path="")
        console = Mock()

        with (
            patch("core.optimize.util.init_runtime_context"),
            patch("core.optimize.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("core.optimize.Console", return_value=console),
        ):
            code = optimize.main([])

        self.assertEqual(1, code)
        console.print.assert_called_once_with("Not inside a git repository.", markup=False)

    def test_main_returns_1_when_index_is_missing(self) -> None:
        runtime = runtime_context("/repo")
        console = Mock()

        with (
            patch("core.optimize.util.init_runtime_context", return_value=runtime),
            patch("core.optimize.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("core.optimize.Console", return_value=console),
        ):
            code = optimize.main([])

        self.assertEqual(1, code)
        console.print.assert_called_once_with("Missing index", markup=False)

    def _run_with_report(self, report: OptimizationReport, argv: list[str] | None = None):
        console = Mock()
        index = Mock()
        index.load_entries.return_value = [Mock()]
        entries = index.load_entries.return_value

        with temporary_session_repo(with_index=True) as repo_root:
            runtime = runtime_context(repo_root)
            with (
                patch("core.optimize.util.init_runtime_context", return_value=runtime),
                patch("core.optimize.util._RUNTIME_CONTEXT", runtime, create=True),
                patch("core.optimize.Console", return_value=console),
                patch("core.optimize.load_review_config", return_value=ReviewConfig()),
                patch("core.optimize.build_parser_registry", return_value=Mock()),
                patch("core.optimize.Index", return_value=index),
                patch("core.optimize.run_optimization", return_value=report) as run,
            ):
                code = optimize.main(argv or [])

        return code, console, run, entries

    def test_main_reports_when_there_are_no_review_logs(self) -> None:
        report = OptimizationReport(
            card_count=0, review_log_count=0, parameters=(), changed=False, skipped_reason=SKIPPED_NO_LOGS
        )

        code, console, _run, _entries = self._run_with_report(report)

        self.assertEqual(0, code)
        console.print.assert_called_once_with("No review logs found. Nothing to optimize.", markup=False)

    def test_main_reports_insufficient_data_without_writing(self) -> None:
        report = OptimizationReport(
            card_count=1,
            review_log_count=1,
            parameters=_default_parameters(),
            changed=False,
            skipped_reason=SKIPPED_INSUFFICIENT_DATA,
        )

        code, console, _run, _entries = self._run_with_report(report)

        self.assertEqual(0, code)
        self.assertIn("Not enough review history", console.print.call_args_list[0].args[0])

    def test_main_runs_optimization_with_flags(self) -> None:
        report = _changed_report()

        code, _console, run, entries = self._run_with_report(report, argv=["--verbose", "--dry-run"])

        self.assertEqual(0, code)
        run.assert_called_once_with(entries, verbose=True, dry_run=True)

    def test_main_handles_missing_optimizer_dependencies(self) -> None:
        console = Mock()
        index = Mock()
        index.load_entries.return_value = []

        with temporary_session_repo(with_index=True) as repo_root:
            runtime = runtime_context(repo_root)
            with (
                patch("core.optimize.util.init_runtime_context", return_value=runtime),
                patch("core.optimize.util._RUNTIME_CONTEXT", runtime, create=True),
                patch("core.optimize.Console", return_value=console),
                patch("core.optimize.load_review_config", return_value=ReviewConfig()),
                patch("core.optimize.build_parser_registry", return_value=Mock()),
                patch("core.optimize.Index", return_value=index),
                patch("core.optimize.run_optimization", side_effect=ImportError),
            ):
                code = optimize.main([])

        self.assertEqual(1, code)
        self.assertIn("fsrs[optimizer]", console.print.call_args_list[0].args[0])
