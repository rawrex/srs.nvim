from collections.abc import Callable

from core.index.hunks import (
    classify_range_touch,
    find_claimed_range_index,
    remap_line_range,
)
from core.index.model import Hunk, IndexRowTuple, PathRemapResult


def remap_rows_for_path(
    modified_path: str,
    path_rows: list[IndexRowTuple],
    hunks: list[Hunk],
    collect_parser_rows: Callable[[str], list[tuple[str, int, int]]],
    create_card_row: Callable[[str, int, int], tuple[IndexRowTuple, str]],
    remove_card_file: Callable[[str], str | None],
) -> PathRemapResult:
    changed = False
    touched_paths: set[str] = set()
    remapped_rows: list[IndexRowTuple] = []
    pending_rows: list[tuple[IndexRowTuple, bool, tuple[int, int] | None]] = []

    for row in sorted(path_rows, key=lambda item: (item[2], item[3])):
        note_id, parser_id, start_line, end_line = row
        within_range, adjacent_insert = classify_range_touch(
            start_line,
            end_line,
            hunks,
        )
        remapped_range = remap_line_range(start_line, end_line, hunks)

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

    parsed_rows = collect_parser_rows(modified_path)
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
        match_index = find_claimed_range_index(
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
            removed_path = remove_card_file(note_id)
            if removed_path is not None:
                touched_paths.add(removed_path)
            changed = True
            continue

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
        row, touched_path = create_card_row(parsed_parser_id, start_line, end_line)
        touched_paths.add(touched_path)
        remapped_rows.append(row)

    return PathRemapResult(
        rows=remapped_rows,
        changed=changed,
        touched_paths=touched_paths,
    )
