from dataclasses import dataclass

from core import util

IndexRowTuple = tuple[str, str, int, int]
PathRows = dict[str, list[IndexRowTuple]]


@dataclass(frozen=True)
class DiffChangeSet:
    renames: dict[str, str]
    deletes: set[str]
    adds: set[str]

    @classmethod
    def from_diff_text(cls, diff_text: str) -> "DiffChangeSet":
        renames, deletes, adds = util.parse_diff(diff_text)
        return cls(
            renames=renames,
            deletes=deletes,
            adds=adds,
        )

    def has_changes(self) -> bool:
        return bool(self.renames or self.deletes or self.adds)


@dataclass(frozen=True)
class IndexUpdateResult:
    lines: list[str]
    changed: bool
    touched_paths: set[str]


@dataclass(frozen=True)
class IndexEntry:
    card_id: str
    note_path: str
    parser_id: str
    start_line: int
    end_line: int
