import re

from core.index.model import IndexRow, IndexRowTuple, PathRows


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


def format_row(
    note_id: str,
    indexed_path: str,
    parser_id: str,
    start_line: int,
    end_line: int,
) -> str:
    return f"'{note_id}','{indexed_path}','{parser_id}','{start_line}','{end_line}'\n"


def format_rows_for_path(indexed_path: str, rows: list[IndexRowTuple]) -> list[str]:
    return [
        format_row(note_id, indexed_path, parser_id, start_line, end_line)
        for note_id, parser_id, start_line, end_line in sorted(
            rows, key=lambda row: (row[2], row[3])
        )
    ]


def rows_by_path(lines: list[str], row_reader: IndexRowReader) -> PathRows:
    grouped: PathRows = {}
    for line in lines:
        row = row_reader.parse(line)
        if row is None:
            continue
        grouped.setdefault(row.path, []).append(
            (row.note_id, row.parser_id, row.start_line, row.end_line)
        )
    return grouped


def replace_rows_for_path(
    lines: list[str],
    indexed_path: str,
    replacement_rows: list[IndexRowTuple],
    row_reader: IndexRowReader,
) -> list[str]:
    updated: list[str] = []
    inserted = False
    replacement_lines = format_rows_for_path(indexed_path, replacement_rows)

    for line in lines:
        row = row_reader.parse(line)
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
