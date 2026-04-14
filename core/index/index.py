#!/usr/bin/env python3
import os
import re

from core import util
from core.card import SchedulerCard
from core.index.model import DiffChangeSet, IndexEntry, IndexUpdateResult
from core.index.storage import Metadata, write_metadata
from core.parsers import ParserRegistry


class Index:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.path = util.get_index_path()
        self.parser_registry = parser_registry
        self.entry_re = re.compile(r"^'([^']*)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")

    def apply_diff(self, diff_text: str) -> bool:
        changes = DiffChangeSet.from_diff_text(diff_text)
        if not changes.has_changes():
            return False

        result = self._update_index_lines(self._readlines(), changes)
        if not result.changed:
            return False

        self._write(result.lines)
        touched_paths = set(result.touched_paths)
        touched_paths.add(self.index_file_path())

        self._stage_paths(util.get_repo_root_path(), touched_paths)
        return True

    def sync_tracked_paths(self, tracked_paths: set[str], repo_root: str) -> bool:
        lines = self._readlines()
        updated: list[str] = []
        changed = False
        touched_paths: set[str] = set()

        for line in lines:
            entry = self._parse(line)
            if entry is None:
                updated.append(line)
                continue
            if not self._is_note_path(entry.note_path) or entry.note_path in tracked_paths:
                updated.append(line)
                continue

            changed = True
            removed_path = self.remove_card_file(entry.card_id)
            if removed_path is not None:
                touched_paths.add(removed_path)

        grouped_entries = self._enries_by_path(updated)
        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path) or tracked_path in grouped_entries:
                continue
            before_count = len(updated)
            touched_paths.update(self._add_new(tracked_path, updated))
            if len(updated) != before_count:
                changed = True
                grouped_entries[tracked_path] = [IndexEntry('', '', '', 0, 0)]

        if changed:
            self._write(updated)
            touched_paths.add(self.index_file_path())

        if changed and repo_root:
            self._stage_paths(repo_root, touched_paths)
        return changed

    def add_missing_tracked_paths(self, tracked_paths: set[str]) -> int:
        lines = self._readlines()
        original_count = len(lines)
        existing_paths = set(self._enries_by_path(lines))

        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path):
                continue
            if tracked_path in existing_paths:
                continue
            self._add_new(tracked_path, lines)
            existing_paths.add(tracked_path)

        if len(lines) != original_count:
            self._write(lines)
        return len(lines) - original_count

    def load_entries(self) -> list[IndexEntry]:
        entries: list[IndexEntry] = []
        for raw_line in self._readlines():
            if entry := self._parse(raw_line):
                entries.append(entry)
        return entries

    def _update_index_lines(self, lines: list[str], changes: DiffChangeSet) -> IndexUpdateResult:
        updated, deleted_or_renamed, touched_paths = self._apply_deletes_and_renames(
            lines, changes.renames, changes.deletes
        )
        updated, added_new, added_paths = self._apply_adds(updated, changes.adds)
        touched_paths.update(added_paths)
        changed = deleted_or_renamed or added_new
        return IndexUpdateResult(lines=updated, changed=changed, touched_paths=touched_paths)

    def _apply_deletes_and_renames(
        self, lines: list[str], renames: dict[str, str], deletes: set[str]
    ) -> tuple[list[str], bool, set[str]]:
        updated: list[str] = []
        changed = False
        touched_paths: set[str] = set()

        for line in lines:
            entry = self._parse(line)
            if entry is None:
                updated.append(line)
                continue
            if entry.note_path in deletes:
                changed = True
                removed_path = self.remove_card_file(entry.card_id)
                if removed_path is not None:
                    touched_paths.add(removed_path)
                continue
            if entry.note_path in renames:
                changed = True
                updated.append(
                    self._format_entry(
                        IndexEntry(
                            card_id=entry.card_id,
                            note_path=renames[entry.note_path],
                            parser_id=entry.parser_id,
                            start_line=entry.start_line,
                            end_line=entry.end_line,
                        )
                    )
                )
                continue
            updated.append(line)

        return updated, changed, touched_paths

    def _apply_adds(self, lines: list[str], adds: set[str]) -> tuple[list[str], bool, set[str]]:
        changed = False
        touched_paths: set[str] = set()
        existing_paths = set(self._enries_by_path(lines))

        for new_path in sorted(adds):
            if not self._is_note_path(new_path) or new_path in existing_paths:
                continue
            changed = True
            touched_paths.update(self._add_new(new_path, lines))
            existing_paths.add(new_path)

        return lines, changed, touched_paths

    def _stage_paths(self, repo_root: str, indexed_paths: set[str]) -> None:
        rel_paths = sorted(path.lstrip("/") for path in indexed_paths)
        if rel_paths:
            util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

    def _readlines(self) -> list[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: list[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def _add_new(self, new_path: str, updated: list[str]) -> set[str]:
        touched_card_paths: set[str] = set()
        for parser_id, start_line, end_line in self.collect_parsed_blocks(new_path):
            scheduler_card = SchedulerCard()
            metadata = Metadata(scheduler_card=scheduler_card, review_logs=[])
            card_id = str(scheduler_card.card_id)
            card_path = self._card_abs_path(card_id)
            write_metadata(card_path, metadata)
            entry, touched_path = (
                IndexEntry(
                    card_id=card_id, note_path=new_path, parser_id=parser_id, start_line=start_line, end_line=end_line
                ),
                self.card_path(card_id),
            )
            updated.append(self._format_entry(entry))
            touched_card_paths.add(touched_path)
        return touched_card_paths

    def _is_note_path(self, indexed_path: str) -> bool:
        return not (
            indexed_path.startswith("/.srs/")
            or indexed_path == "/.srs"
            or indexed_path.startswith("/.git/")
            or indexed_path == "/.git"
        )

    def index_file_path(self) -> str:
        rel_path = os.path.relpath(self.path, self.repo_root())
        return util.normalize_path(rel_path)

    def remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self.card_path(note_id)
        return None

    def collect_parsed_blocks(self, indexed_path: str) -> list[tuple[str, int, int]]:
        note_text = self.read_note_text(indexed_path)
        if note_text is None:
            return []

        selected: list[tuple[str, int, int]] = []
        claimed_ranges: list[tuple[int, int]] = []
        for parser in self.parser_registry.ordered():
            cards = parser.interpret_text(note_text)
            for line_start, line_end, _ in cards:
                if not any(
                    line_start <= claimed_end and line_end >= claimed_start
                    for claimed_start, claimed_end in claimed_ranges
                ):
                    selected.append((parser.parser_id, line_start, line_end))
                    claimed_ranges.append((line_start, line_end))

        return sorted(selected, key=lambda entry: (entry[1], entry[2], entry[0]))

    def card_path(self, note_id: str) -> str:
        return f"/.srs/{note_id}.json"

    def repo_root(self) -> str:
        return os.path.dirname(os.path.dirname(self.path))

    def _card_abs_path(self, note_id: str) -> str:
        return os.path.join(os.path.dirname(self.path), f"{note_id}.json")

    def read_note_text(self, indexed_path: str) -> str | None:
        note_path = os.path.join(self.repo_root(), indexed_path.lstrip("/"))
        if os.path.exists(note_path):
            with open(note_path, "r", encoding="utf-8") as handle:
                try:
                    return handle.read()
                except UnicodeDecodeError:
                    return None
        return None

    def _enries_by_path(self, lines: list[str]) -> dict[str, list[IndexEntry]]:
        grouped: dict[str, list[IndexEntry]] = {}
        for line in lines:
            if entry := self._parse(line):
                grouped.setdefault(entry.note_path, []).append(entry)
        return grouped

    def _parse(self, raw_line: str) -> IndexEntry | None:
        if match := self.entry_re.match(raw_line.rstrip("\n")):
            return IndexEntry(
                card_id=match.group(1),
                note_path=match.group(2),
                parser_id=match.group(3),
                start_line=int(match.group(4)),
                end_line=int(match.group(5)),
            )
        return None

    def _format_entry(self, entry: IndexEntry) -> str:
        return f"'{entry.card_id}','{entry.note_path}','{entry.parser_id}','{entry.start_line}','{entry.end_line}'\n"

    __all__ = ["Index"]
