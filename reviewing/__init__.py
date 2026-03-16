from .card import Card, RevealMode, SchedulerCard

__all__ = ["Card", "RevealMode", "ReviewSession", "ReviewUI", "SchedulerCard"]


def __getattr__(name: str):
    if name == "ReviewSession":
        from .session import ReviewSession

        return ReviewSession
    if name == "ReviewUI":
        from .ui import ReviewUI

        return ReviewUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
