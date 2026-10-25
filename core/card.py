from dataclasses import dataclass

__all__ = ["CardRef"]


@dataclass(frozen=True)
class CardRef:
    """Everything a UI needs to present one card in its note."""

    index: int  # 1-based position in the due list
    total: int  # number of due cards in the session
    card_id: int  # index entry id / metadata file name
    note_path: str  # repo-relative source path (leading "/")
    card_type: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
