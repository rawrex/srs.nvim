#!/usr/bin/env python3
import os
import re
from dataclasses import dataclass

from reviewing.card import (
    SchedulerCard,
)
from reviewing.parsers import DEFAULT_PARSER_ID, ParserRegistry, default_parser_registry
from reviewing.storage import Metadata, write_metadata_file

import util


Hunk = tuple[int, int, int, int]
PathRows = dict[str, list[tuple[str, str, int, int]]]
IndexRowTuple = tuple[str, str, int, int]


@dataclass(frozen=True)
class DiffChangeSet:
    renames: dict[str, str]
    deletes: set[str]
    adds: set[str]
    modifies: set[str]

    @classmethod
    def from_diff_text(cls, diff_text: str) -> "DiffChangeSet":
        renames, deletes, adds, modifies = util.parse_diff(diff_text)
        return cls(
            renames=renames,
            deletes=deletes,
            adds=adds,
            modifies=modifies,
        )

    def has_changes(self) -> bool:
        return bool(self.renames or self.deletes or self.adds or self.modifies)


@dataclass(frozen=True)
class PathRemapResult:
    rows: list[IndexRowTuple]
    changed: bool
    touched_paths: set[str]
    error_message: str | None = None


class IndexUpdateAbortError(Exception):
    pass


@dataclass(frozen=True)
class IndexUpdateResult:
    lines: list[str]
    changed: bool
    touched_paths: set[str]


@dataclass(frozen=True)
class IndexRow:
    note_id: str
    path: str
    parser_id: str
    start_line: int
    end_line: int


class IndexRowReader:
    def __init__(self) -> None:
        self.row_re = re.compile(r"^'([^']*)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")

    def parse(self, raw_line: str) -> IndexRow | None:
        match = self.row_re.match(raw_line.rstrip("\n"))
        if not match:
            return None
        return IndexRow(
            note_id=match.group(1),
            path=match.group(2),
            parser_id=match.group(3),
            start_line=int(match.group(4)),
            end_line=int(match.group(5)),
        )


class Index:
    def __init__(
        self,
        path: str,
        parser_registry: ParserRegistry | None = None,
    ) -> None:
        self.path = path
        self.parser_registry = parser_registry or default_parser_registry()
        self.row_reader = IndexRowReader()
        self.hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

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

    def apply_diff_and_stage(
        self, repo_root: str, diff_text: str, patch_text: str = ""
    ) -> None:
        changed, staged_paths = self._apply_diff(diff_text, patch_text)
        if changed:
            self._stage_paths(repo_root, staged_paths)

    def apply_diff(self, diff_text: str, patch_text: str = "") -> bool:
        changed, _staged_paths = self._apply_diff(diff_text, patch_text)
        return changed

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
        if result.changed:
            self._write(result.lines)
            touched_paths = set(result.touched_paths)
            touched_paths.add(self._index_file_path())
            return True, touched_paths
        return False, set()

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
            lines=updated,
            changed=changed,
            touched_paths=touched_paths,
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
        rows_by_path = self._rows_by_path(lines)
        existing_paths = set(rows_by_path)
        for new_path in sorted(adds):
            if not self._is_note_path(new_path) or new_path in existing_paths:
                continue
            changed = True
            touched_paths.update(self._add_new(new_path, DEFAULT_PARSER_ID, lines))
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
            rows_by_path = self._rows_by_path(updated)
            if modified_path not in rows_by_path:
                continue

            remap_result = self._remap_rows_for_path(
                modified_path,
                rows_by_path[modified_path],
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

        parser_id_for_path = path_rows[0][1] if path_rows else DEFAULT_PARSER_ID
        parsed_ranges = [
            (start_line, end_line)
            for start_line, end_line, _block_text in self._load_note_cards(
                modified_path,
                parser_id_for_path,
            )
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
                matched_start, matched_end = parsed_ranges[match_index]
                if matched_start != start_line or matched_end != end_line:
                    changed = True
                remapped_rows.append((note_id, parser_id, matched_start, matched_end))
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
        for start_line, end_line in parsed_ranges:
            if (start_line, end_line) in existing_ranges:
                continue
            changed = True
            row, touched_path = self._create_card_row(
                parser_id_for_path,
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

    def _find_claimed_range_index(
        self,
        parsed_ranges: list[tuple[int, int]],
        claimed_ranges: set[tuple[int, int]],
        target_start: int,
        target_end: int,
        cursor: int,
    ) -> int | None:
        for index in range(cursor, len(parsed_ranges)):
            parsed_start, parsed_end = parsed_ranges[index]
            if (parsed_start, parsed_end) in claimed_ranges:
                continue
            if parsed_end < target_start:
                continue
            if parsed_start > target_end:
                return None
            return index
        return None

    def _classify_range_touch(
        self,
        start_line: int,
        end_line: int,
        hunks: list[Hunk],
    ) -> tuple[bool, bool]:
        within_range = False
        adjacent_insert = False
        for old_start, old_count, _new_start, _new_count in hunks:
            if old_count == 0:
                if start_line <= old_start <= end_line:
                    within_range = True
                elif old_start == start_line - 1 or old_start == end_line:
                    adjacent_insert = True
                continue

            old_end = old_start + old_count - 1
            if old_end < start_line or old_start > end_line:
                continue
            within_range = True
        return within_range, adjacent_insert

    def _replace_rows_for_path(
        self,
        lines: list[str],
        indexed_path: str,
        replacement_rows: list[IndexRowTuple],
    ) -> list[str]:
        updated: list[str] = []
        inserted = False
        replacement_lines = self._format_rows_for_path(indexed_path, replacement_rows)

        for line in lines:
            row = self.row_reader.parse(line)
            if row is None:
                updated.append(line)
                continue
            if row.path != indexed_path:
                updated.append(line)
                continue
            if not inserted:
                updated.extend(replacement_lines)
                inserted = True

        if not inserted:
            updated.extend(replacement_lines)
        return updated

    def _format_rows_for_path(
        self,
        indexed_path: str,
        rows: list[IndexRowTuple],
    ) -> list[str]:
        return [
            self._format_row(note_id, indexed_path, parser_id, start_line, end_line)
            for note_id, parser_id, start_line, end_line in sorted(
                rows, key=lambda row: (row[2], row[3])
            )
        ]

    def _format_row(
        self,
        note_id: str,
        indexed_path: str,
        parser_id: str,
        start_line: int,
        end_line: int,
    ) -> str:
        return (
            f"'{note_id}','{indexed_path}','{parser_id}','{start_line}','{end_line}'\n"
        )

    def _remap_line_range(
        self,
        start_line: int,
        end_line: int,
        hunks: list[Hunk],
    ) -> tuple[int, int] | None:
        shift = 0
        for old_start, old_count, _new_start, new_count in sorted(hunks):
            if old_count == 0:
                if start_line > old_start:
                    shift += new_count
                elif start_line < old_start <= end_line:
                    return None
                continue

            old_end = old_start + old_count - 1
            if end_line < old_start:
                break
            if start_line > old_end:
                shift += new_count - old_count
                continue

            return None
        return start_line + shift, end_line + shift

    def _parse_modified_hunks(self, patch_text: str) -> dict[str, list[Hunk]]:
        hunks_by_path: dict[str, list[Hunk]] = {}
        current_path = ""
        for line in patch_text.splitlines():
            if line.startswith("diff --git "):
                current_path = ""
                continue
            if line.startswith("+++ "):
                raw_path = line[4:].strip()
                if raw_path == "/dev/null":
                    current_path = ""
                else:
                    if raw_path.startswith("a/") or raw_path.startswith("b/"):
                        raw_path = raw_path[2:]
                    current_path = util.normalize_path(raw_path)
                continue

            if not current_path or not line.startswith("@@"):
                continue

            match = self.hunk_re.match(line)
            if not match:
                continue
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            hunks_by_path.setdefault(current_path, []).append(
                (old_start, old_count, new_start, new_count)
            )
        return hunks_by_path

    def _remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self._card_path(note_id)
        return None

    def _add_new(
        self,
        new_path: str,
        parser_id: str,
        updated: list[str],
    ) -> set[str]:
        touched_card_paths: set[str] = set()
        for start_line, end_line, _block_text in self._load_note_cards(
            new_path, parser_id
        ):
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
        self, parser_id: str, start_line: int, end_line: int
    ) -> tuple[IndexRowTuple, str]:
        scheduler_card = SchedulerCard()
        metadata = Metadata(scheduler_card=scheduler_card, review_logs=[])
        card_id = str(scheduler_card.card_id)
        self._write_card_file(card_id, metadata)
        return (card_id, parser_id, start_line, end_line), self._card_path(card_id)

    def _rows_by_path(self, lines: list[str]) -> PathRows:
        rows_by_path: PathRows = {}
        for line in lines:
            row = self.row_reader.parse(line)
            if row is None:
                continue
            rows_by_path.setdefault(row.path, []).append(
                (row.note_id, row.parser_id, row.start_line, row.end_line)
            )
        return rows_by_path

    def _is_note_path(self, indexed_path: str) -> bool:
        return not (
            indexed_path.startswith("/.srs/")
            or indexed_path == "/.srs"
            or indexed_path.startswith("/.git/")
            or indexed_path == "/.git"
        )

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

    def _load_note_cards(
        self, indexed_path: str, parser_id: str
    ) -> list[tuple[int, int, str]]:
        note_path = self._note_abs_path(indexed_path)
        if not os.path.exists(note_path):
            return []
        try:
            with open(note_path, "r", encoding="utf-8") as handle:
                note_text = handle.read()
        except (OSError, UnicodeDecodeError):
            return []
        try:
            parser = self.parser_registry.get(parser_id)
        except KeyError:
            return []
        return parser.split_note_into_cards(note_text)

    def _write_card_file(
        self,
        card_id: str,
        metadata: Metadata,
    ) -> None:
        card_path = self._card_abs_path(card_id)
        write_metadata_file(card_path, metadata)
