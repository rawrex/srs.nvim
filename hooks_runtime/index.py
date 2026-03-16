#!/usr/bin/env python3
import json
import os
import re
from typing import Dict, List, Set, Tuple

from fsrs import Card

import util


class Index:
    def __init__(self, path: str) -> None:
        self.path = path
        self.row_re = re.compile(r"^'([^']*)','([^']*)','(\d+)'\s*$")

    def _stage_paths(self, repo_root: str, indexed_paths: Set[str]) -> None:
        rel_paths = sorted(path.lstrip("/") for path in indexed_paths)
        if rel_paths:
            util.run_git(["add", "--"] + rel_paths, cwd=repo_root)

    def _read(self) -> List[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: List[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def apply_diff_and_stage(self, repo_root: str, diff_text: str) -> None:
        changed, staged_paths = self._apply_diff(diff_text)
        if changed:
            self._stage_paths(repo_root, staged_paths)

    def apply_diff(self, diff_text: str) -> bool:
        changed, _staged_paths = self._apply_diff(diff_text)
        return changed

    def _apply_diff(self, diff_text: str) -> Tuple[bool, Set[str]]:
        renames, deletes, adds, modifies = util.parse_diff(diff_text)
        if not renames and not deletes and not adds and not modifies:
            return False, set()
        updated, changed, touched_card_paths = self._update_index_lines(
            self._read(), renames, deletes, adds, modifies
        )
        if changed:
            self._write(updated)
            touched_card_paths.add(self._index_file_path())
        return changed, touched_card_paths

    def read_rows(self) -> List[Tuple[str, str, int]]:
        rows: List[Tuple[str, str, int]] = []
        for raw_line in self._read():
            line = raw_line.strip()
            if not line:
                continue
            match = self.row_re.match(line)
            if not match:
                continue
            rows.append((match.group(1), match.group(2), int(match.group(3))))
        return rows

    def _update_index_lines(
        self,
        lines: List[str],
        renames: Dict[str, str],
        deletes: Set[str],
        adds: Set[str],
        modifies: Set[str],
    ) -> Tuple[List[str], bool, Set[str]]:
        change_flag = False
        touched_card_paths: Set[str] = set()
        updated: List[str] = []
        for line in lines:
            match = self.row_re.match(line.rstrip("\n"))
            if not match:
                updated.append(line)
                continue
            note_id, path, start_line = match.groups()
            if path in deletes:
                change_flag = True
                if removed_path := self._remove_card_file(note_id):
                    touched_card_paths.add(removed_path)
                continue
            if path in renames:
                change_flag = True
                new_path = renames[path]
                updated.append(f"'{note_id}','{new_path}','{start_line}'\n")
            else:
                updated.append(line)

        rows_by_path = self._rows_by_path(updated)
        existing_paths = set(rows_by_path.keys())

        for new_path in sorted(adds):
            if not self._is_note_path(new_path):
                continue
            if new_path not in existing_paths:
                change_flag = True
                touched_card_paths.update(self._add_new(new_path, updated))

        rows_by_path = self._rows_by_path(updated)
        for modified_path in sorted(modifies):
            if not self._is_note_path(modified_path):
                continue
            if modified_path not in rows_by_path:
                continue
            existing_start_lines = {
                start_line for _note_id, start_line in rows_by_path[modified_path]
            }
            max_existing_start_line = (
                max(existing_start_lines) if existing_start_lines else 0
            )
            cards = self._load_note_cards(modified_path)
            for start_line, _block_text in cards:
                if (
                    start_line in existing_start_lines
                    or start_line <= max_existing_start_line
                ):
                    continue
                change_flag = True
                new_card = Card()
                card_id = str(new_card.card_id)
                self._write_card_file(card_id, new_card.to_json())
                touched_card_paths.add(self._card_path(card_id))
                updated.append(f"'{card_id}','{modified_path}','{start_line}'\n")

        return updated, change_flag, touched_card_paths

    def _remove_card_file(self, note_id: str) -> str | None:
        card_path = self._card_abs_path(note_id)
        if os.path.exists(card_path):
            os.remove(card_path)
            return self._card_path(note_id)
        return None

    def _add_new(self, new_path: str, updated: List[str]) -> Set[str]:
        touched_card_paths: Set[str] = set()
        for start_line, _block_text in self._load_note_cards(new_path):
            new_card = Card()
            card_id = str(new_card.card_id)
            self._write_card_file(card_id, new_card.to_json())
            touched_card_paths.add(self._card_path(card_id))
            updated.append(f"'{card_id}','{new_path}','{start_line}'\n")
        return touched_card_paths

    def _rows_by_path(self, lines: List[str]) -> Dict[str, List[Tuple[str, int]]]:
        rows_by_path: Dict[str, List[Tuple[str, int]]] = {}
        for line in lines:
            match = self.row_re.match(line.rstrip("\n"))
            if not match:
                continue
            note_id, path, raw_start_line = match.groups()
            rows_by_path.setdefault(path, []).append((note_id, int(raw_start_line)))
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

    def _load_note_cards(self, indexed_path: str) -> List[Tuple[int, str]]:
        note_path = self._note_abs_path(indexed_path)
        if not os.path.exists(note_path):
            return []
        try:
            with open(note_path, "r", encoding="utf-8") as handle:
                note_text = handle.read()
        except (OSError, UnicodeDecodeError):
            return []
        return split_note_into_cards(note_text)

    def _write_card_file(self, card_id: str, payload: str) -> None:
        card_path = self._card_abs_path(card_id)
        tmp_card_path = card_path + ".tmp"
        parsed = json.loads(payload)
        with open(tmp_card_path, "w", encoding="utf-8") as handle:
            json.dump(parsed, handle, ensure_ascii=False, indent=4, sort_keys=True)
        os.replace(tmp_card_path, card_path)


def split_note_into_cards(note_text: str) -> List[Tuple[int, str]]:
    cards: List[Tuple[int, str]] = []
    lines = note_text.splitlines(keepends=True)
    line_count = len(lines)
    idx = 0

    while idx < line_count:
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        start_idx = idx
        base_indent = _indent_width(line)
        idx += 1

        while idx < line_count:
            next_line = lines[idx]
            if not next_line.strip() or _indent_width(next_line) <= base_indent:
                break
            idx += 1

        block_text = "".join(lines[start_idx:idx])
        cards.append((start_idx + 1, block_text))

    return cards


def _indent_width(line: str) -> int:
    width = 0
    for char in line:
        if char in (" ", "\t"):
            width += 1
            continue
        break
    return width
