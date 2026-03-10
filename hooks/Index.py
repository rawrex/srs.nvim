#!/usr/bin/env python3
import os
import re
import util
from fsrs import Card
from typing import Dict, List, Set, Tuple


class Index:
    def __init__(self, path: str) -> None:
        self.path = path
        self.row_re = re.compile(r"^'([^']*)','([^']*)'\s*$")

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
        renames, deletes, adds = util.parse_diff(diff_text)
        if not renames and not deletes and not adds:
            return False
        updated, changed = self._update_index_lines(self._read(), renames, deletes, adds)
        if changed:
            self._write(updated)
        return changed

    def _update_index_lines(self, lines: List[str], renames: Dict[str, str], deletes: Set[str], adds: Set[str],) -> Tuple[List[str], bool]:
        change_flag = False
        updated: List[str] = []
        existing_paths: Set[str] = set()
        existing_ids: Set[int] = set()
        for line in lines:
            match = self.row_re.match(line.rstrip("\n"))
            if not match:
                updated.append(line)
                continue
            note_id, path = match.groups()
            existing_paths.add(path)
            existing_ids.add(int(note_id))
            if path in deletes:
                change_flag = True
                self._remove_card_file(note_id)
                continue
            if path in renames:
                change_flag = True
                new_path = renames[path]
                updated.append(f"'{note_id}','{new_path}'\n")
                existing_paths.add(new_path)
            else:  # File changed, no path edits
                updated.append(line)
        for new_path in sorted(adds):
            if new_path not in existing_paths:
                change_flag = True
                self._add_new(new_path, updated, existing_ids, existing_paths)
        return updated, change_flag

    def _remove_card_file(self, note_id: str) -> None:
        card_path = os.path.join(os.path.dirname(self.path), f"{note_id}.json")
        if os.path.exists(card_path):
            os.remove(card_path)

    def _add_new(self, new_path: str, updated: List[str], existing_ids: Set[int], existing_paths: Set[str]) -> None:
        new_card = Card()
        card_path = os.path.join(os.path.dirname(self.path), f"{new_card.card_id}.json")
        tmp_card_path = card_path + ".tmp"
        with open(tmp_card_path, "w", encoding="utf-8") as handle:
            handle.write(new_card.to_json())
        os.replace(tmp_card_path, card_path)
        existing_paths.add(new_path)
        existing_ids.add(new_card.card_id)
        updated.append(f"'{new_card.card_id}','{new_path}'\n")
