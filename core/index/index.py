#!/usr/bin/env python3
import os
import re

from fsrs import Card as SchedulerCard

from core import util
from core.index.model import DiffChangeSet, IndexEntry, Metadata


class Index:
    """Plain-text mapping between cards, their notes, and their location within the notes

    The index is the source of truth for which cards exist.
    the review engine only reads entries and metadata.
    """

    def __init__(self) -> None:
        self.path = util._RUNTIME_CONTEXT.index_path
        self.entry_re = re.compile(r"^'(\d+)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")

    # Queries -----------------------------------------------------------------

    def load_entries(self) -> list[IndexEntry]:
        entries: list[IndexEntry] = []
        for raw_line in self._readlines():
            if entry := self._parse(raw_line):
                entries.append(entry)
        return entries

    def entries_for_note(self, note_path: str) -> list[IndexEntry]:
        return [entry for entry in self.load_entries() if entry.note_path == note_path]

    # Writes ------------------------------------------------------------------

    def add_card(self, note_path: str, card_type: str, start_line: int, end_line: int) -> IndexEntry:
        scheduler_card = SchedulerCard()
        index_entry = IndexEntry(
            card_id=scheduler_card.card_id,
            note_path=note_path,
            card_type=card_type,
            start_line=start_line,
            end_line=end_line,
        )
        index_entry.write_metadata(Metadata(scheduler_card=scheduler_card, review_logs=[]))
        lines = self._readlines()
        lines.append(self._format_entry(index_entry))
        self._write(lines)
        return index_entry

    def remove_note(self, note_path: str) -> list[IndexEntry]:
        entries = self.entries_for_note(note_path)
        if not entries:
            return []
        rest = [line for line in self._readlines() if not self._matches_note(line, note_path)]
        self._write(rest)
        for entry in entries:
            if os.path.exists(entry.card_path):
                os.remove(entry.card_path)
        return entries

    def rename_note(self, old_path: str, new_path: str) -> list[IndexEntry]:
        renamed: list[IndexEntry] = []
        lines: list[str] = []
        for line in self._readlines():
            entry = self._parse(line)
            if entry is None or entry.note_path != old_path:
                lines.append(line)
                continue
            entry = IndexEntry(
                card_id=entry.card_id,
                note_path=new_path,
                card_type=entry.card_type,
                start_line=entry.start_line,
                end_line=entry.end_line,
            )
            renamed.append(entry)
            lines.append(self._format_entry(entry))
        if renamed:
            self._write(lines)
        return renamed

    def apply_diff(self, diff_text: str) -> bool:
        """Apply note deletions and renames from a git diff.

        Card *creation* is intentionally absent: parsing is an explicit add-on,
        never part of the hook/commit flow.
        """
        changes = DiffChangeSet.from_diff_text(diff_text)
        touched_paths: set[str] = set()
        changed = False
        for note_path in sorted(changes.deletes):
            removed = self.remove_note(note_path)
            if removed:
                changed = True
                touched_paths.update(self.card_path(entry.card_id) for entry in removed)
        for old_path, new_path in sorted(changes.renames.items()):
            if self.rename_note(old_path, new_path):
                changed = True
        if changed:
            touched_paths.add(self.index_file_path())
            self._stage_paths(self.repo_root(), touched_paths)
        return changed

    # Helpers -----------------------------------------------------------------

    def index_file_path(self) -> str:
        rel_path = os.path.relpath(self.path, self.repo_root())
        return util.normalize_path(rel_path)

    def card_path(self, card_id: int) -> str:
        return f"/.srs/{card_id}.json"

    def repo_root(self) -> str:
        return util._RUNTIME_CONTEXT.repo_root_path

    def _matches_note(self, raw_line: str, note_path: str) -> bool:
        entry = self._parse(raw_line)
        return entry is not None and entry.note_path == note_path

    def _stage_paths(self, repo_root: str, indexed_paths: set[str]) -> None:
        rel_paths = sorted(path.lstrip("/") for path in indexed_paths)
        if rel_paths:
            util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

    def _readlines(self) -> list[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: list[str]) -> None:
        util.write_text_atomic(self.path, "".join(lines))

    def _parse(self, raw_line: str) -> IndexEntry | None:
        if match := self.entry_re.match(raw_line.rstrip("\n")):
            return IndexEntry(
                card_id=int(match.group(1)),
                note_path=match.group(2),
                card_type=match.group(3),
                start_line=int(match.group(4)),
                end_line=int(match.group(5)),
            )
        return None

    def _format_entry(self, entry: IndexEntry) -> str:
        return f"'{entry.card_id}','{entry.note_path}','{entry.card_type}','{entry.start_line}','{entry.end_line}'\n"
