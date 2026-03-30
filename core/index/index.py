#!/usr/bin/env python3
import os
from dataclasses import dataclass

from card.parsers import ParserRegistry
from core import util
from core.index.card_store import IndexCardStore
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


class Index:
    def __init__(self, path: str, parser_registry: ParserRegistry) -> None:
        self.path = path
        self._parser_registry = parser_registry
        self.row_reader = IndexRowReader()
        self.hunk_parser = HunkParser()
        self.card_store = IndexCardStore(path, parser_registry)

    @property
    def parser_registry(self) -> ParserRegistry:
        return self._parser_registry

    @parser_registry.setter
    def parser_registry(self, parser_registry: ParserRegistry) -> None:
        self._parser_registry = parser_registry
        self.card_store.parser_registry = parser_registry

    def apply_diff_and_stage(
        self,
        repo_root: str,
        diff_text: str,
        patch_text: str = "",
    ) -> None:
        changed, staged_paths = self._apply_diff(diff_text, patch_text)
        if changed:
            self._stage_paths(repo_root, staged_paths)

    def apply_diff(self, diff_text: str, patch_text: str = "") -> bool:
        changed, _staged_paths = self._apply_diff(diff_text, patch_text)
        return changed

    def sync_tracked_paths_and_stage(
        self,
        repo_root: str,
        tracked_paths: set[str],
    ) -> bool:
        changed, touched_paths = self._sync_tracked_paths(tracked_paths)
        if changed:
            self._stage_paths(repo_root, touched_paths)
        return changed

    def sync_tracked_paths(self, tracked_paths: set[str]) -> bool:
        changed, _touched_paths = self._sync_tracked_paths(tracked_paths)
        return changed

    def add_missing_tracked_paths(self, tracked_paths: set[str]) -> int:
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

    def build_cleanup_report(self, tracked_paths: set[str]) -> "IndexCleanupReport":
        lines = self._read()
        grouped_rows = self._rows_by_path(lines)

        expected_rows_cache: dict[str, set[tuple[str, int, int]]] = {}
        missing_rows_by_path: dict[str, list[tuple[str, int, int]]] = {}
        missing_tracked_paths: list[str] = []

        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path):
                continue
            indexed_rows = grouped_rows.get(tracked_path, [])
            if not indexed_rows:
                missing_tracked_paths.append(tracked_path)

            expected_rows = self._expected_rows_set(tracked_path)
            expected_rows_cache[tracked_path] = expected_rows
            indexed_row_keys = {
                (parser_id, start_line, end_line)
                for _note_id, parser_id, start_line, end_line in indexed_rows
            }
            missing_rows = sorted(expected_rows - indexed_row_keys)
            if missing_rows:
                missing_rows_by_path[tracked_path] = missing_rows

        invalid_rows: list[IndexInvalidRow] = []
        for raw_line in lines:
            row = self.row_reader.parse(raw_line)
            if row is None:
                continue
            if not self._is_note_path(row.path):
                invalid_rows.append(
                    IndexInvalidRow(
                        note_id=row.note_id,
                        path=row.path,
                        parser_id=row.parser_id,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        reason="non_note_path",
                    )
                )
                continue
            if self._read_note_text(row.path) is None:
                invalid_rows.append(
                    IndexInvalidRow(
                        note_id=row.note_id,
                        path=row.path,
                        parser_id=row.parser_id,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        reason="missing_note",
                    )
                )
                continue

            expected_rows = expected_rows_cache.get(row.path)
            if expected_rows is None:
                expected_rows = self._expected_rows_set(row.path)
                expected_rows_cache[row.path] = expected_rows
            if (row.parser_id, row.start_line, row.end_line) not in expected_rows:
                invalid_rows.append(
                    IndexInvalidRow(
                        note_id=row.note_id,
                        path=row.path,
                        parser_id=row.parser_id,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        reason="missing_parser_row",
                    )
                )

        referenced_card_ids = {
            row.note_id
            for raw_line in lines
            for row in [self.row_reader.parse(raw_line)]
            if row is not None
        }
        orphan_card_ids = sorted(self._list_card_ids() - referenced_card_ids)

        return IndexCleanupReport(
            missing_tracked_paths=missing_tracked_paths,
            missing_rows_by_path=missing_rows_by_path,
            invalid_rows=invalid_rows,
            orphan_card_ids=orphan_card_ids,
        )

    def apply_cleanup_report(
        self,
        report: "IndexCleanupReport",
        *,
        add_missing: bool,
        remove_invalid: bool,
        remove_orphan_cards: bool,
    ) -> "IndexCleanupApplyResult":
        lines = self._read()
        added_rows = 0
        removed_invalid_rows = 0
        removed_orphan_cards = 0

        if add_missing:
            for tracked_path in sorted(report.missing_rows_by_path):
                missing_rows = report.missing_rows_by_path[tracked_path]
                added_rows += self._append_missing_rows(
                    tracked_path, missing_rows, lines
                )

        if remove_invalid:
            invalid_row_keys = {
                (row.note_id, row.path, row.parser_id, row.start_line, row.end_line)
                for row in report.invalid_rows
            }
            if invalid_row_keys:
                updated: list[str] = []
                removed_note_ids: list[str] = []
                for raw_line in lines:
                    row = self.row_reader.parse(raw_line)
                    if row is None:
                        updated.append(raw_line)
                        continue
                    key = (
                        row.note_id,
                        row.path,
                        row.parser_id,
                        row.start_line,
                        row.end_line,
                    )
                    if key in invalid_row_keys:
                        removed_invalid_rows += 1
                        removed_note_ids.append(row.note_id)
                        continue
                    updated.append(raw_line)
                lines = updated

                remaining_note_ids = {
                    parsed_row.note_id
                    for raw_line in lines
                    for parsed_row in [self.row_reader.parse(raw_line)]
                    if parsed_row is not None
                }
                for note_id in removed_note_ids:
                    if note_id in remaining_note_ids:
                        continue
                    self._remove_card_file(note_id)

        if add_missing or remove_invalid:
            self._write(lines)

        if remove_orphan_cards:
            referenced_note_ids = {
                row.note_id
                for raw_line in lines
                for row in [self.row_reader.parse(raw_line)]
                if row is not None
            }
            orphan_card_ids = sorted(self._list_card_ids() - referenced_note_ids)
            for note_id in orphan_card_ids:
                removed = self._remove_card_file(note_id)
                if removed is not None:
                    removed_orphan_cards += 1

        return IndexCleanupApplyResult(
            added_rows=added_rows,
            removed_invalid_rows=removed_invalid_rows,
            removed_orphan_cards=removed_orphan_cards,
        )

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

    def _apply_diff(self, diff_text: str, patch_text: str) -> tuple[bool, set[str]]:
        changes = DiffChangeSet.from_diff_text(diff_text)
        if not changes.has_changes():
            return False, set()

        result = self._update_index_lines(
            self._read(),
            changes,
            self._parse_modified_hunks(patch_text),
        )
        if not result.changed:
            return False, set()

        self._write(result.lines)
        touched_paths = set(result.touched_paths)
        touched_paths.add(self._index_file_path())
        return True, touched_paths

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
        updated, added_new, added_paths = self._apply_adds(updated, changes.adds)
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

    def _sync_tracked_paths(self, tracked_paths: set[str]) -> tuple[bool, set[str]]:
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

    def _add_new(self, new_path: str, updated: list[str]) -> set[str]:
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
        return self.card_store.create_card_row(parser_id, start_line, end_line)

    def _remove_card_file(self, note_id: str) -> str | None:
        return self.card_store.remove_card_file(note_id)

    def _collect_parser_rows(self, indexed_path: str) -> list[tuple[str, int, int]]:
        return self.card_store.collect_parser_rows(indexed_path)

    def _read_note_text(self, indexed_path: str) -> str | None:
        return self.card_store.read_note_text(indexed_path)

    def _append_missing_rows(
        self,
        indexed_path: str,
        missing_rows: list[tuple[str, int, int]],
        lines: list[str],
    ) -> int:
        added_rows = 0
        grouped_rows = self._rows_by_path(lines)
        existing_row_keys = {
            (parser_id, start_line, end_line)
            for _note_id, parser_id, start_line, end_line in grouped_rows.get(
                indexed_path, []
            )
        }
        for parser_id, start_line, end_line in missing_rows:
            key = (parser_id, start_line, end_line)
            if key in existing_row_keys:
                continue
            row, _touched_path = self._create_card_row(parser_id, start_line, end_line)
            note_id, row_parser_id, row_start_line, row_end_line = row
            lines.append(
                self._format_row(
                    note_id,
                    indexed_path,
                    row_parser_id,
                    row_start_line,
                    row_end_line,
                )
            )
            existing_row_keys.add((row_parser_id, row_start_line, row_end_line))
            added_rows += 1
        return added_rows

    def _expected_rows_set(self, indexed_path: str) -> set[tuple[str, int, int]]:
        return {
            (parser_id, start_line, end_line)
            for parser_id, start_line, end_line in self._collect_parser_rows(
                indexed_path
            )
        }

    def _is_note_path(self, indexed_path: str) -> bool:
        return self.card_store.is_note_path(indexed_path)

    def _index_file_path(self) -> str:
        return self.card_store.index_file_path()

    def _list_card_ids(self) -> set[str]:
        srs_dir = os.path.dirname(self.path)
        if not os.path.isdir(srs_dir):
            return set()
        card_ids: set[str] = set()
        for name in os.listdir(srs_dir):
            if not name.endswith(".json"):
                continue
            card_ids.add(name[: -len(".json")])
        return card_ids

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


@dataclass(frozen=True)
class IndexInvalidRow:
    note_id: str
    path: str
    parser_id: str
    start_line: int
    end_line: int
    reason: str


@dataclass(frozen=True)
class IndexCleanupReport:
    missing_tracked_paths: list[str]
    missing_rows_by_path: dict[str, list[tuple[str, int, int]]]
    invalid_rows: list[IndexInvalidRow]
    orphan_card_ids: list[str]


@dataclass(frozen=True)
class IndexCleanupApplyResult:
    added_rows: int
    removed_invalid_rows: int
    removed_orphan_cards: int


__all__ = [
    "Index",
    "IndexCleanupApplyResult",
    "IndexCleanupReport",
    "IndexInvalidRow",
    "IndexUpdateAbortError",
    "IndexRowReader",
]
