from dataclasses import dataclass
from datetime import datetime

from fsrs import Card, Scheduler

from core.entry import IndexEntry

__all__ = ["RescheduleChange", "RescheduleReport", "reschedule_entries"]


@dataclass(frozen=True)
class RescheduleChange:
    card_id: int
    note_path: str
    old_due: datetime
    new_due: datetime
    old_stability: float | None
    new_stability: float | None


@dataclass(frozen=True)
class RescheduleReport:
    scanned: int
    selected: int
    rescheduled: int
    changes: list[RescheduleChange]


def reschedule_entries(
    entries: list[IndexEntry], scheduler: Scheduler, since: datetime | None = None, dry_run: bool = False
) -> RescheduleReport:
    """Replay each card's review history through ``scheduler`` and rewrite its derived state.

    ``since`` limits the work to cards with at least one review on or after that instant.
    Review logs are treated as immutable facts; only stability, difficulty, state, and due change.
    """
    selected = 0
    changes: list[RescheduleChange] = []

    for entry in entries:
        metadata = entry.read_metadata()
        logs = metadata.review_logs
        if not logs:
            continue
        if since is not None and not any(log.review_datetime >= since for log in logs):
            continue
        selected += 1

        card = Card(card_id=entry.card_id)
        for log in sorted(logs, key=lambda item: item.review_datetime):
            card, _ = scheduler.review_card(
                card, log.rating, review_datetime=log.review_datetime, review_duration=log.review_duration
            )

        changes.append(
            RescheduleChange(
                card_id=entry.card_id,
                note_path=entry.note_path,
                old_due=entry.due,
                new_due=card.due,
                old_stability=metadata.scheduler_card.stability,
                new_stability=card.stability,
            )
        )
        metadata.scheduler_card = card
        entry.due = card.due
        if not dry_run:
            entry.write()

    return RescheduleReport(scanned=len(entries), selected=selected, rescheduled=len(changes), changes=changes)
