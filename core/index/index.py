#!/usr/bin/env python3
import os

from core import util
from core.card import SchedulerCard
from core.index.hunks import HunkParser, remap_line_range
from core.index.model import (
    DiffChangeSet,
    Hunk,
    IndexRowTuple,
    IndexUpdateAbortError,
    IndexUpdateResult,
    PathRows,
)
from core.index.remap import remap_rows_for_path
from core.index.row_codec import (
    IndexRowReader,
    format_row,
    replace_rows_for_path,
    rows_by_path,
)
from core.index.storage import Metadata, write_metadata
from core.parsers import ParserRegistry


class Index:
    def __init__(
        self,
        path: str,
        parser_registry: ParserRegistry,
    ) -> None:
        self.path = path
        self.parser_registry = parser_registry
        self.row_reader = IndexRowReader()
        self.hunk_parser = HunkParser()

    def apply_diff(
        self,
        diff_text: str,
        patch_text: str,
        repo_root: str,
    ) -> bool:
        changes = DiffChangeSet.from_diff_text(diff_text)
        if not changes.has_changes():
            return False

        result = self._update_index_lines(
            self._read(),
            changes,
            self._parse_modified_hunks(patch_text),
        )
        if not result.changed:
            return False

        self._write(result.lines)
        touched_paths = set(result.touched_paths)
        touched_paths.add(self._index_file_path())
        if repo_root:
            self._stage_paths(repo_root, touched_paths)
            return True
        return False

    def sync_tracked_paths(
        self,
        tracked_paths: set[str],
        repo_root: str,
    ) -> bool:
        changed, touched_paths = self._sync_tracked_paths(tracked_paths)
        if changed and repo_root:
            self._stage_paths(repo_root, touched_paths)
        return changed

    def add_missing_tracked_paths(
        self,
        tracked_paths: set[str],
    ) -> int:
        lines = self._read()
        original_count = len(lines)
        existing_paths = set(self._rows_by_path(lines))

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

    def read_rows(self) -> list[tuple[str, str, str, int, int]]:
        rows: list[tuple[str, str, str, int, int]] = []
        for raw_line in self._read():
            row = self.row_reader.parse(raw_line)
            if row is None:
                continue
            rows.append(
                (row.note_id, row.path, row.parser_id, row.start_line, row.end_line)
            )
        return rows

    def _update_index_lines(
        self,
        lines: list[str],
        changes: DiffChangeSet,
        modified_hunks: dict[str, list[Hunk]],
    ) -> IndexUpdateResult:
        updated, deleted_or_renamed, touched_paths = self._apply_deletes_and_renames(
            lines,
            changes.renames,
            changes.deletes,
        )
        updated, added_new, added_paths = self._apply_adds(
            updated,
            changes.adds,
        )
        updated, remapped_modified, remapped_paths = self._apply_modifies(
            updated,
            changes.modifies,
            modified_hunks,
        )
        touched_paths.update(added_paths)
        touched_paths.update(remapped_paths)
        changed = deleted_or_renamed or added_new or remapped_modified
        return IndexUpdateResult(
            lines=updated, changed=changed, touched_paths=touched_paths
        )

    def _apply_deletes_and_renames(
        self,
        lines: list[str],
        renames: dict[str, str],
        deletes: set[str],
    ) -> tuple[list[str], bool, set[str]]:
        updated: list[str] = []
        changed = False
        touched_paths: set[str] = set()

        for line in lines:
            row = self.row_reader.parse(line)
            if row is None:
                updated.append(line)
                continue
            if row.path in deletes:
                changed = True
                removed_path = self._remove_card_file(row.note_id)
                if removed_path is not None:
                    touched_paths.add(removed_path)
                continue
            if row.path in renames:
                changed = True
                updated.append(
                    self._format_row(
                        row.note_id,
                        renames[row.path],
                        row.parser_id,
                        row.start_line,
                        row.end_line,
                    )
                )
                continue
            updated.append(line)

        return updated, changed, touched_paths

    def _apply_adds(
        self,
        lines: list[str],
        adds: set[str],
    ) -> tuple[list[str], bool, set[str]]:
        changed = False
        touched_paths: set[str] = set()
        existing_paths = set(self._rows_by_path(lines))

        for new_path in sorted(adds):
            if not self._is_note_path(new_path) or new_path in existing_paths:
                continue
            changed = True
            touched_paths.update(self._add_new(new_path, lines))
            existing_paths.add(new_path)

        return lines, changed, touched_paths

    def _apply_modifies(
        self,
        lines: list[str],
        modifies: set[str],
        modified_hunks: dict[str, list[Hunk]],
    ) -> tuple[list[str], bool, set[str]]:
        updated = lines
        changed = False
        touched_paths: set[str] = set()

        for modified_path in sorted(modifies):
            if not self._is_note_path(modified_path):
                continue
            grouped_rows = self._rows_by_path(updated)
            path_rows = grouped_rows.get(modified_path)
            if path_rows is None:
                continue

            remap_result = remap_rows_for_path(
                modified_path=modified_path,
                path_rows=path_rows,
                hunks=modified_hunks.get(modified_path, []),
                collect_parser_rows=self._collect_parser_rows,
                create_card_row=self._create_card_row,
                remove_card_file=self._remove_card_file,
            )
            if remap_result.error_message:
                raise IndexUpdateAbortError(remap_result.error_message)

            replacement = replace_rows_for_path(
                lines=updated,
                indexed_path=modified_path,
                replacement_rows=remap_result.rows,
                row_reader=self.row_reader,
            )
            if replacement != updated:
                updated = replacement
                changed = True
            changed = changed or remap_result.changed
            touched_paths.update(remap_result.touched_paths)

        return updated, changed, touched_paths

    def _sync_tracked_paths(
        self,
        tracked_paths: set[str],
    ) -> tuple[bool, set[str]]:
        lines = self._read()
        updated: list[str] = []
        changed = False
        touched_paths: set[str] = set()

        for line in lines:
            row = self.row_reader.parse(line)
            if row is None:
                updated.append(line)
                continue
            if not self._is_note_path(row.path) or row.path in tracked_paths:
                updated.append(line)
                continue

            changed = True
            removed_path = self._remove_card_file(row.note_id)
            if removed_path is not None:
                touched_paths.add(removed_path)

        grouped_rows = self._rows_by_path(updated)
        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path) or tracked_path in grouped_rows:
                continue
            before_count = len(updated)
            touched_paths.update(self._add_new(tracked_path, updated))
            if len(updated) != before_count:
                changed = True
                grouped_rows[tracked_path] = [("", "", 0, 0)]

        if changed:
            self._write(updated)
            touched_paths.add(self._index_file_path())
        return changed, touched_paths

    def _stage_paths(self, repo_root: str, indexed_paths: set[str]) -> None:
        rel_paths = sorted(path.lstrip("/") for path in indexed_paths)
        if rel_paths:
            util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

    def _read(self) -> list[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: list[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def _parse_modified_hunks(self, patch_text: str) -> dict[str, list[Hunk]]:
        return self.hunk_parser.parse_modified_hunks(patch_text)

    def _remap_line_range(
        self,
        start_line: int,
        end_line: int,
        hunks: list[Hunk],
    ) -> tuple[int, int] | None:
        return remap_line_range(start_line, end_line, hunks)

    def _add_new(
        self,
        new_path: str,
        updated: list[str],
    ) -> set[str]:
        touched_card_paths: set[str] = set()
        for parser_id, start_line, end_line in self._collect_parser_rows(new_path):
            row, touched_path = self._create_card_row(parser_id, start_line, end_line)
            note_id, row_parser_id, row_start_line, row_end_line = row
            updated.append(
                self._format_row(
                    note_id,
                    new_path,
                    row_parser_id,
                    row_start_line,
                    row_end_line,
                )
            )
            touched_card_paths.add(touched_path)
        return touched_card_paths

    def _create_card_row(
        self,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> tuple[IndexRowTuple, str]:
        return self.create_card_row(parser_id, start_line, end_line)

    def _remove_card_file(self, note_id: str) -> str | None:
        return self.remove_card_file(note_id)

    def _collect_parser_rows(self, indexed_path: str) -> list[tuple[str, int, int]]:
        return self.collect_parser_rows(indexed_path)

    def _is_note_path(self, indexed_path: str) -> bool:
        return not (
            indexed_path.startswith("/.srs/")
            or indexed_path == "/.srs"
            or indexed_path.startswith("/.git/")
            or indexed_path == "/.git"
        )

    def _index_file_path(self) -> str:
        return self.index_file_path()

    def index_file_path(self) -> str:
        rel_path = os.path.relpath(self.path, self.repo_root())
        return util.normalize_path(rel_path)

    def remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self.card_path(note_id)
        return None

    def collect_parser_rows(
        self,
        indexed_path: str,
    ) -> list[tuple[str, int, int]]:
        note_text = self.read_note_text(indexed_path)
        if note_text is None:
            return []

        selected: list[tuple[str, int, int]] = []
        claimed: list[tuple[int, int]] = []
        for parser in self.parser_registry.ordered():
            cards = parser.split_note_into_cards(note_text)
            for start_line, end_line, _ in cards:
                if any(
                    not (end_line < claimed_start or start_line > claimed_end)
                    for claimed_start, claimed_end in claimed
                ):
                    continue
                selected.append((parser.parser_id, start_line, end_line))
                claimed.append((start_line, end_line))

        return sorted(selected, key=lambda row: (row[1], row[2], row[0]))

    def create_card_row(
        self,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> tuple[IndexRowTuple, str]:
        scheduler_card = SchedulerCard()
        metadata = Metadata(scheduler_card=scheduler_card, review_logs=[])
        card_id = str(scheduler_card.card_id)
        card_path = self._card_abs_path(card_id)
        write_metadata(card_path, metadata)
        return (card_id, parser_id, start_line, end_line), self.card_path(card_id)

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
                return handle.read()
        return None

    def _rows_by_path(self, lines: list[str]) -> PathRows:
        return rows_by_path(lines, row_reader=self.row_reader)

    def _format_row(
        self,
        note_id: str,
        indexed_path: str,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> str:
        return format_row(note_id, indexed_path, parser_id, start_line, end_line)


__all__ = ["Index", "IndexUpdateAbortError", "IndexRowReader"]
