#!/usr/bin/env python3
import os

from card.card import SchedulerCard
from card.parsers import ParserRegistry
from core.index.hunks import (
    HunkParser,
    classify_range_touch,
    find_claimed_range_index,
    remap_line_range,
)
from core.index.model import (
    DiffChangeSet,
    Hunk,
    IndexRowTuple,
    IndexUpdateAbortError,
    IndexUpdateResult,
    PathRemapResult,
    PathRows,
)
from core.index.row_codec import (
    IndexRowReader,
    format_row,
    format_rows_for_path,
    replace_rows_for_path,
    rows_by_path,
)
from core.index.storage import Metadata, write_metadata_file

from core import util


class Index:
    def __init__(self, path: str, parser_registry: ParserRegistry) -> None:
        self.path = path
        self.parser_registry = parser_registry
        self.row_reader = IndexRowReader()
        self.hunk_parser = HunkParser()

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
        existing_paths = set(self._rows_by_path(lines))
        original_count = len(lines)

        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path):
                continue
            if tracked_path in existing_paths:
                continue
            self._add_new(tracked_path, lines)
            existing_paths.add(tracked_path)

        if lines != self._read():
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

    def _read(self) -> list[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: list[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def _stage_paths(self, repo_root: str, indexed_paths: set[str]) -> None:
        rel_paths = sorted(path.lstrip("/") for path in indexed_paths)
        if rel_paths:
            util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

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
            if not self._is_note_path(row.path):
                updated.append(line)
                continue
            if row.path in tracked_paths:
                updated.append(line)
                continue

            changed = True
            removed_path = self._remove_card_file(row.note_id)
            if removed_path is not None:
                touched_paths.add(removed_path)

        grouped_rows = self._rows_by_path(updated)
        for tracked_path in sorted(tracked_paths):
            if not self._is_note_path(tracked_path):
                continue
            if tracked_path in grouped_rows:
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

    def _apply_diff(self, diff_text: str, patch_text: str) -> tuple[bool, set[str]]:
        changes = DiffChangeSet.from_diff_text(diff_text)
        if not changes.has_changes():
            return False, set()

        modified_hunks = self._parse_modified_hunks(patch_text)
        result = self._update_index_lines(
            self._read(),
            changes,
            modified_hunks,
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
        updated, removed_or_renamed, touched_paths = self._apply_deletes_and_renames(
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
        changed = removed_or_renamed or added_new or remapped_modified
        return IndexUpdateResult(
            lines=updated, changed=changed, touched_paths=touched_paths
        )

    def _apply_deletes_and_renames(
        self,
        lines: list[str],
        renames: dict[str, str],
        deletes: set[str],
    ) -> tuple[list[str], bool, set[str]]:
        changed = False
        touched_paths: set[str] = set()
        updated: list[str] = []
        for line in lines:
            row = self.row_reader.parse(line)
            if row is None:
                updated.append(line)
                continue
            if row.path in deletes:
                changed = True
                if removed_path := self._remove_card_file(row.note_id):
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
        grouped_rows = self._rows_by_path(lines)
        existing_paths = set(grouped_rows)
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
        changed = False
        touched_paths: set[str] = set()
        updated = lines
        for modified_path in sorted(modifies):
            if not self._is_note_path(modified_path):
                continue
            grouped_rows = self._rows_by_path(updated)
            if modified_path not in grouped_rows:
                continue

            remap_result = self._remap_rows_for_path(
                modified_path,
                grouped_rows[modified_path],
                modified_hunks.get(modified_path, []),
            )
            if remap_result.error_message:
                raise IndexUpdateAbortError(remap_result.error_message)

            replacement = self._replace_rows_for_path(
                updated,
                modified_path,
                remap_result.rows,
            )
            if replacement != updated:
                updated = replacement
                remap_result = PathRemapResult(
                    rows=remap_result.rows,
                    changed=True,
                    touched_paths=remap_result.touched_paths,
                )

            changed = changed or remap_result.changed
            touched_paths.update(remap_result.touched_paths)

        return updated, changed, touched_paths

    def _remap_rows_for_path(
        self,
        modified_path: str,
        path_rows: list[IndexRowTuple],
        hunks: list[Hunk],
    ) -> PathRemapResult:
        changed = False
        touched_paths: set[str] = set()
        remapped_rows: list[IndexRowTuple] = []
        pending_rows: list[tuple[IndexRowTuple, bool, tuple[int, int] | None]] = []

        for row in sorted(path_rows, key=lambda item: (item[2], item[3])):
            note_id, parser_id, start_line, end_line = row
            within_range, adjacent_insert = self._classify_range_touch(
                start_line,
                end_line,
                hunks,
            )
            remapped_range = self._remap_line_range(start_line, end_line, hunks)

            if within_range or adjacent_insert:
                pending_rows.append((row, within_range, remapped_range))
                continue
            if remapped_range is None:
                pending_rows.append((row, True, None))
                continue

            remapped_start_line, remapped_end_line = remapped_range
            if remapped_start_line != start_line or remapped_end_line != end_line:
                changed = True
            remapped_rows.append(
                (note_id, parser_id, remapped_start_line, remapped_end_line)
            )

        parsed_rows = self._collect_parser_rows(modified_path)
        parsed_ranges = [
            (start_line, end_line) for _parser_id, start_line, end_line in parsed_rows
        ]

        claimed_ranges = {
            (start_line, end_line)
            for _note_id, _parser_id, start_line, end_line in remapped_rows
        }
        parsed_cursor = 0

        for (
            note_id,
            parser_id,
            start_line,
            end_line,
        ), within_range, fallback_range in pending_rows:
            target_start, target_end = (
                fallback_range if fallback_range is not None else (start_line, end_line)
            )
            match_index = self._find_claimed_range_index(
                parsed_ranges,
                claimed_ranges,
                target_start,
                target_end,
                parsed_cursor,
            )
            if match_index is not None:
                matched_parser_id, matched_start, matched_end = parsed_rows[match_index]
                if matched_start != start_line or matched_end != end_line:
                    changed = True
                remapped_rows.append(
                    (note_id, matched_parser_id, matched_start, matched_end)
                )
                claimed_ranges.add((matched_start, matched_end))
                parsed_cursor = match_index + 1
                continue

            if within_range:
                return PathRemapResult(
                    rows=path_rows,
                    changed=False,
                    touched_paths=touched_paths,
                    error_message=(
                        "SRS index update aborted: parser could not claim an edited "
                        f"card range in {modified_path}. Please resolve manually."
                    ),
                )

            if fallback_range is None:
                return PathRemapResult(
                    rows=path_rows,
                    changed=False,
                    touched_paths=touched_paths,
                    error_message=(
                        "SRS index update aborted: failed to remap card range "
                        f"in {modified_path}. Please resolve manually."
                    ),
                )

            fallback_start, fallback_end = fallback_range
            if fallback_start != start_line or fallback_end != end_line:
                changed = True
            remapped_rows.append((note_id, parser_id, fallback_start, fallback_end))
            claimed_ranges.add((fallback_start, fallback_end))

        existing_ranges = {
            (start_line, end_line)
            for _note_id, _parser_id, start_line, end_line in remapped_rows
        }
        for parsed_parser_id, start_line, end_line in parsed_rows:
            if (start_line, end_line) in existing_ranges:
                continue
            changed = True
            row, touched_path = self._create_card_row(
                parsed_parser_id,
                start_line,
                end_line,
            )
            touched_paths.add(touched_path)
            remapped_rows.append(row)

        return PathRemapResult(
            rows=remapped_rows,
            changed=changed,
            touched_paths=touched_paths,
        )

    def _remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self._card_path(note_id)
        return None

    def _add_new(self, new_path: str, updated: list[str]) -> set[str]:
        touched_card_paths: set[str] = set()
        for parser_id, start_line, end_line in self._collect_parser_rows(new_path):
            row, touched_path = self._create_card_row(parser_id, start_line, end_line)
            note_id, row_parser_id, row_start_line, row_end_line = row
            touched_card_paths.add(touched_path)
            updated.append(
                self._format_row(
                    note_id,
                    new_path,
                    row_parser_id,
                    row_start_line,
                    row_end_line,
                )
            )
        return touched_card_paths

    def _create_card_row(
        self,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> tuple[IndexRowTuple, str]:
        scheduler_card = SchedulerCard()
        metadata = Metadata(scheduler_card=scheduler_card, review_logs=[])
        card_id = str(scheduler_card.card_id)
        self._write_card_file(card_id, metadata)
        return (card_id, parser_id, start_line, end_line), self._card_path(card_id)

    def _is_note_path(self, indexed_path: str) -> bool:
        return not (
            indexed_path.startswith("/.srs/")
            or indexed_path == "/.srs"
            or indexed_path.startswith("/.git/")
            or indexed_path == "/.git"
        )

    def _rows_by_path(self, lines: list[str]) -> PathRows:
        return rows_by_path(lines, row_reader=self.row_reader)

    def _replace_rows_for_path(
        self,
        lines: list[str],
        indexed_path: str,
        replacement_rows: list[IndexRowTuple],
    ) -> list[str]:
        return replace_rows_for_path(
            lines,
            indexed_path,
            replacement_rows,
            row_reader=self.row_reader,
        )

    def _format_rows_for_path(
        self,
        indexed_path: str,
        rows: list[IndexRowTuple],
    ) -> list[str]:
        return format_rows_for_path(indexed_path, rows)

    def _format_row(
        self,
        note_id: str,
        indexed_path: str,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> str:
        return format_row(
            note_id,
            indexed_path,
            parser_id,
            start_line,
            end_line,
        )

    def _parse_modified_hunks(self, patch_text: str) -> dict[str, list[Hunk]]:
        return self.hunk_parser.parse_modified_hunks(patch_text)

    def _find_claimed_range_index(
        self,
        parsed_ranges: list[tuple[int, int]],
        claimed_ranges: set[tuple[int, int]],
        target_start: int,
        target_end: int,
        cursor: int,
    ) -> int | None:
        return find_claimed_range_index(
            parsed_ranges,
            claimed_ranges,
            target_start,
            target_end,
            cursor,
        )

    def _classify_range_touch(
        self,
        start_line: int,
        end_line: int,
        hunks: list[Hunk],
    ) -> tuple[bool, bool]:
        return classify_range_touch(start_line, end_line, hunks)

    def _remap_line_range(
        self,
        start_line: int,
        end_line: int,
        hunks: list[Hunk],
    ) -> tuple[int, int] | None:
        return remap_line_range(start_line, end_line, hunks)

    def _index_file_path(self) -> str:
        rel_path = os.path.relpath(self.path, self._repo_root())
        return util.normalize_path(rel_path)

    def _card_path(self, note_id: str) -> str:
        return f"/.srs/{note_id}.json"

    def _card_abs_path(self, note_id: str) -> str:
        return os.path.join(os.path.dirname(self.path), f"{note_id}.json")

    def _repo_root(self) -> str:
        return os.path.dirname(os.path.dirname(self.path))

    def _note_abs_path(self, indexed_path: str) -> str:
        return os.path.join(self._repo_root(), indexed_path.lstrip("/"))

    def _read_note_text(self, indexed_path: str) -> str | None:
        note_path = self._note_abs_path(indexed_path)
        if not os.path.exists(note_path):
            return None
        try:
            with open(note_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError):
            return None

    def _collect_parser_rows(
        self,
        indexed_path: str,
    ) -> list[tuple[str, int, int]]:
        note_text = self._read_note_text(indexed_path)
        if note_text is None:
            return []

        selected: list[tuple[str, int, int]] = []
        claimed: list[tuple[int, int]] = []
        for parser in self.parser_registry.ordered():
            cards = parser.split_note_into_cards(note_text)
            for start_line, end_line, _block_text in cards:
                if any(
                    not (end_line < claimed_start or start_line > claimed_end)
                    for claimed_start, claimed_end in claimed
                ):
                    continue
                selected.append((parser.parser_id, start_line, end_line))
                claimed.append((start_line, end_line))

        return sorted(selected, key=lambda row: (row[1], row[2], row[0]))

    def _write_card_file(self, card_id: str, metadata: Metadata) -> None:
        card_path = self._card_abs_path(card_id)
        write_metadata_file(card_path, metadata)


__all__ = ["Index", "IndexUpdateAbortError", "IndexRowReader"]
