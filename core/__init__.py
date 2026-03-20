__all__ = ["ReviewSession", "util", "ReviewUI"]


def __getattr__(name: str):
    if name == "ReviewSession":
        from .session import ReviewSession

        return ReviewSession
    if name == "ReviewUI":
        from ui.ui import ReviewUI

        return ReviewUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
