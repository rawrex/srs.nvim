from dataclasses import dataclass
from typing import TYPE_CHECKING

from fsrs.review_log import ReviewLog
from fsrs.scheduler import DEFAULT_PARAMETERS

from core.config import write_scheduler_parameters
from core.index.model import IndexEntry

if TYPE_CHECKING:
    from fsrs.optimizer import Optimizer

__all__ = [
    "OptimizationReport",
    "SKIPPED_INSUFFICIENT_DATA",
    "SKIPPED_NO_LOGS",
    "collect_review_logs",
    "optimize_review_logs",
    "run_optimization",
]

SKIPPED_NO_LOGS = "no_review_logs"
SKIPPED_INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class OptimizationReport:
    card_count: int
    review_log_count: int
    parameters: tuple[float, ...]
    changed: bool
    skipped_reason: str | None = None


def _optimizer_factory(review_logs: list[ReviewLog]) -> "Optimizer":
    # Imported lazily: `fsrs.Optimizer` pulls in the optional torch/pandas/numpy/tqdm extra.
    from fsrs import Optimizer

    return Optimizer(review_logs)


def collect_review_logs(entries: list[IndexEntry]) -> list[ReviewLog]:
    logs: list[ReviewLog] = []
    for entry in entries:
        logs.extend(entry.read_metadata().review_logs)
    return logs


def optimize_review_logs(review_logs: list[ReviewLog], verbose: bool = False) -> list[float]:
    optimizer = _optimizer_factory(review_logs)
    return [float(value) for value in optimizer.compute_optimal_parameters(verbose=verbose)]


def run_optimization(entries: list[IndexEntry], verbose: bool = False, dry_run: bool = False) -> OptimizationReport:
    if review_logs := collect_review_logs(entries):
        card_count = len({log.card_id for log in review_logs})
        parameters = optimize_review_logs(review_logs, verbose=verbose)
        if [float(value) for value in parameters] == list(DEFAULT_PARAMETERS):
            return OptimizationReport(
                card_count=card_count,
                review_log_count=len(review_logs),
                parameters=tuple(parameters),
                changed=False,
                skipped_reason=SKIPPED_INSUFFICIENT_DATA,
            )
        if dry_run:
            return OptimizationReport(
                card_count=card_count,
                review_log_count=len(review_logs),
                parameters=tuple(parameters),
                changed=not dry_run,
            )
        write_scheduler_parameters(parameters)
    return OptimizationReport(
        card_count=0, review_log_count=0, parameters=(), changed=False, skipped_reason=SKIPPED_NO_LOGS
    )
