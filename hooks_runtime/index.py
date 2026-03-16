#!/usr/bin/env python3
import os
import re
from typing import Dict, List, Set, Tuple

from fsrs import Card

import util


class Index:
    def __init__(self, path: str) -> None:
        self.path = path
        self.row_re = re.compile(r"^'([^']*)','([^']*)','(\d+)'\s*$")

    def _stage(self, repo_root: str) -> None:
        rel_index_path = os.path.relpath(self.path, repo_root)
        util.run_git(["add", "--", rel_index_path], cwd=repo_root)

    def _read(self) -> List[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _write(self, lines: List[str]) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp_path, self.path)

    def apply_diff_and_stage(self, repo_root: str, diff_text: str) -> None:
        if changed := self.apply_diff(diff_text):
            self._stage(repo_root)

    def apply_diff(self, diff_text: str) -> bool:
        renames, deletes, adds, modifies = util.parse_diff(diff_text)
        if not renames and not deletes and not adds and not modifies:
            return False
        updated, changed = self._update_index_lines(
            self._read(), renames, deletes, adds, modifies
        )
        if changed:
            self._write(updated)
        return changed

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
    ) -> Tuple[List[str], bool]:
        change_flag = False
        updated: List[str] = []
        for line in lines:
            match = self.row_re.match(line.rstrip("\n"))
            if not match:
                updated.append(line)
                continue
            note_id, path, start_line = match.groups()
            if path in deletes:
                change_flag = True
                self._remove_card_file(note_id)
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
            if new_path not in existing_paths:
                change_flag = True
                self._add_new(new_path, updated)

        rows_by_path = self._rows_by_path(updated)
        for modified_path in sorted(modifies):
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
                self._write_card_file(str(new_card.card_id), new_card.to_json())
                updated.append(
                    f"'{new_card.card_id}','{modified_path}','{start_line}'\n"
                )

        return updated, change_flag

    def _remove_card_file(self, note_id: str) -> None:
        card_path = os.path.join(os.path.dirname(self.path), f"{note_id}.json")
        if os.path.exists(card_path):
            os.remove(card_path)

    def _add_new(self, new_path: str, updated: List[str]) -> None:
        for start_line, _block_text in self._load_note_cards(new_path):
            new_card = Card()
            self._write_card_file(str(new_card.card_id), new_card.to_json())
            updated.append(f"'{new_card.card_id}','{new_path}','{start_line}'\n")

    def _rows_by_path(self, lines: List[str]) -> Dict[str, List[Tuple[str, int]]]:
        rows_by_path: Dict[str, List[Tuple[str, int]]] = {}
        for line in lines:
            match = self.row_re.match(line.rstrip("\n"))
            if not match:
                continue
            note_id, path, raw_start_line = match.groups()
            rows_by_path.setdefault(path, []).append((note_id, int(raw_start_line)))
        return rows_by_path

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
        card_path = os.path.join(os.path.dirname(self.path), f"{card_id}.json")
        tmp_card_path = card_path + ".tmp"
        with open(tmp_card_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
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
