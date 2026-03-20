import re

from core import util
from core.index.model import Hunk


class HunkParser:
    def __init__(self) -> None:
        self.hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def parse_modified_hunks(self, patch_text: str) -> dict[str, list[Hunk]]:
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


def find_claimed_range_index(
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


def classify_range_touch(
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


def remap_line_range(
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
