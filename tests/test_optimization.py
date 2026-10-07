import unittest
from unittest.mock import Mock, patch

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from core.index.model import Metadata
from core.optimization import (
    SKIPPED_INSUFFICIENT_DATA,
    SKIPPED_NO_LOGS,
    collect_review_logs,
    is_default_parameters,
    optimize_review_logs,
    run_optimization,
)


def _review_log(scheduler: Scheduler, card_id: int):
    _updated_card, review_log = scheduler.review_card(SchedulerCard(card_id=card_id), Rating.Good, review_duration=100)
    return review_log


def _entry_with(review_logs: list) -> Mock:
    entry = Mock()
    entry.read_metadata.return_value = Metadata(scheduler_card=SchedulerCard(), review_logs=review_logs)
    return entry


def _changed_parameters() -> list[float]:
    parameters = list(Scheduler().parameters)
    parameters[0] = 0.5
    return parameters


class CollectReviewLogsTest(unittest.TestCase):
    def test_collect_flattens_logs_across_entries(self) -> None:
        scheduler = Scheduler()
        log_a = _review_log(scheduler, card_id=1)
        log_b = _review_log(scheduler, card_id=2)

        logs = collect_review_logs([_entry_with([log_a]), _entry_with([log_b])])

        self.assertEqual([log_a, log_b], logs)

    def test_collect_returns_empty_for_entries_without_logs(self) -> None:
        logs = collect_review_logs([_entry_with([])])

        self.assertEqual([], logs)


class OptimizeReviewLogsTest(unittest.TestCase):
    def test_optimize_uses_factory_and_forwards_verbose(self) -> None:
        fake_optimizer = Mock()
        fake_optimizer.compute_optimal_parameters.return_value = [0.1, 0.2]

        with patch("core.optimization._optimizer_factory", return_value=fake_optimizer) as factory:
            result = optimize_review_logs(["log"], verbose=True)

        factory.assert_called_once_with(["log"])
        fake_optimizer.compute_optimal_parameters.assert_called_once_with(verbose=True)
        self.assertEqual([0.1, 0.2], result)


class IsDefaultParametersTest(unittest.TestCase):
    def test_true_for_defaults(self) -> None:
        self.assertTrue(is_default_parameters(list(Scheduler().parameters)))

    def test_false_for_changed_parameters(self) -> None:
        self.assertFalse(is_default_parameters(_changed_parameters()))


class RunOptimizationTest(unittest.TestCase):
    def test_skips_when_there_are_no_review_logs(self) -> None:
        with patch("core.optimization.collect_review_logs", return_value=[]):
            report = run_optimization([])

        self.assertEqual(SKIPPED_NO_LOGS, report.skipped_reason)
        self.assertFalse(report.changed)
        self.assertEqual(0, report.review_log_count)

    def test_skips_write_when_optimizer_returns_defaults(self) -> None:
        with (
            patch("core.optimization.collect_review_logs", return_value=[Mock(card_id=1)]),
            patch("core.optimization.optimize_review_logs", return_value=list(Scheduler().parameters)),
            patch("core.optimization.write_scheduler_parameters") as write,
        ):
            report = run_optimization([])

        self.assertEqual(SKIPPED_INSUFFICIENT_DATA, report.skipped_reason)
        self.assertFalse(report.changed)
        write.assert_not_called()

    def test_writes_parameters_and_reports_change(self) -> None:
        parameters = _changed_parameters()

        with (
            patch("core.optimization.collect_review_logs", return_value=[Mock(card_id=1)]),
            patch("core.optimization.optimize_review_logs", return_value=parameters),
            patch("core.optimization.write_scheduler_parameters") as write,
        ):
            report = run_optimization([])

        self.assertIsNone(report.skipped_reason)
        self.assertTrue(report.changed)
        self.assertEqual(1, report.card_count)
        self.assertEqual(tuple(parameters), report.parameters)
        write.assert_called_once_with(parameters)

    def test_dry_run_does_not_write(self) -> None:
        parameters = _changed_parameters()

        with (
            patch("core.optimization.collect_review_logs", return_value=[Mock(card_id=1)]),
            patch("core.optimization.optimize_review_logs", return_value=parameters),
            patch("core.optimization.write_scheduler_parameters") as write,
        ):
            report = run_optimization([], dry_run=True)

        write.assert_not_called()
        self.assertFalse(report.changed)
        self.assertEqual(tuple(parameters), report.parameters)
