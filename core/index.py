#!/usr/bin/env python3
import os
import re
from datetime import datetime
from itertools import filterfalse

from fsrs import Card as SchedulerCard

from core import util
from core.model import DiffChangeSet, IndexEntry, Metadata


class Index:
    """Plain-text mapping between cards, their notes, and their location within the notes"""

    entry_re = re.compile(r"^'(\d+)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")

    def __init__(self) -> None:
        self.entries: list[IndexEntry] = Index.load()
        self.entries_by_note: dict[str, list[IndexEntry]] = {}
        self.entries_removed: list[IndexEntry] = []
        for entry in self.entries:
            self.entries_by_note.setdefault(entry.note_path, []).append(entry)

    @classmethod
    def load(cls) -> list[IndexEntry]:
        lines: list[str] = []
        entries: list[IndexEntry] = []
        with open(util._RUNTIME_CONTEXT.index_path, "r", encoding="utf-8") as handle:
            for line in handle.readlines():
                if entry := Index.parse(line):
                    entries.append(entry)
        return entries

    @classmethod
    def parse(cls, raw_line: str) -> IndexEntry | None:
        if match := Index.entry_re.match(raw_line.rstrip("\n")):
            return IndexEntry(
                metadata=None,
                card_id=int(match.group(1)),
                note_path=match.group(2),
                card_type=match.group(3),
                start_line=int(match.group(4)),
                end_line=int(match.group(5)),
            )
        return None

    def get_entries(self, time_point: datetime | None = None) -> list[IndexEntry]:
        if time_point:
            return [entry for entry in self.entries if entry.is_due(time_point=time_point)]
        return self.entries

    def get_entries_by_note(self, path: str) -> list[IndexEntry]:
        if entries := self.entries_by_note.get(path):
            return entries
        return []

    def add_card(self, note_path: str, card_type: str, start_line: int, end_line: int) -> IndexEntry:
        fsrs_card = SchedulerCard()
        entry = IndexEntry(
            metadata=Metadata(scheduler_card=fsrs_card, review_logs=[]),
            card_id=fsrs_card.card_id,
            note_path=note_path,
            card_type=card_type,
            start_line=start_line,
            end_line=end_line,
        )
        self.entries.append(entry)
        self.entries_by_note.setdefault(note_path, []).append(entry)
        return entry

    def remove_note(self, note_path: str) -> bool:
        if not (note_path in self.entries_by_note):
            return False
        predicate = lambda entry: entry.note_path == note_path
        removed = list(filter(predicate, self.entries))
        self.entries = list(filterfalse(predicate, self.entries))
        self.entries_by_note.pop(note_path, None)
        self.entries_removed.extend(removed)
        return True

    def rename_note(self, old_path: str, new_path: str) -> bool:
        if not (old_path in self.entries_by_note):
            return False
        for entry in self.entries:
            if entry.note_path == old_path:
                entry.note_path = new_path
        self.entries_by_note[new_path] = self.entries_by_note[old_path]
        self.entries_by_note.pop(old_path, None)
        return True

    def apply_diff(self, diff_text: str):
        changed = False
        changes = DiffChangeSet.from_diff_text(diff_text)
        for note_path in sorted(changes.deletes):
            if self.remove_note(note_path):
                changed = True
        for old_path, new_path in sorted(changes.renames.items()):
            if self.rename_note(old_path, new_path):
                changed = True
        if changed:
            touched_paths = {entry.card_path for entry in self.entries_removed}
            touched_paths.add(util._RUNTIME_CONTEXT.index_path)
            self.flush()
            repo_root = util._RUNTIME_CONTEXT.repo_root_path
            if rel_paths := sorted(util.repo_relative_path(repo_root, path).lstrip("/") for path in touched_paths):
                util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

    def flush(self) -> None:
        for entry in self.entries_removed:
            os.remove(entry.card_path)
        self.entries_removed.clear()
        lines: list[str] = []
        for entry in self.entries:
            lines.append(entry.format())
            entry.write()
        util.write_text_atomic(util._RUNTIME_CONTEXT.index_path, "".join(lines))
