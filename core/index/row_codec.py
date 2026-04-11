import re

from core.index.model import IndexEntry, PathRows


class IndexRowReader:
    def __init__(self) -> None:
        self.row_re = re.compile(r"^'([^']*)','([^']*)','([^']*)','(\d+)','(\d+)'\s*$")

    def parse(self, raw_line: str) -> IndexEntry | None:
        if match := self.row_re.match(raw_line.rstrip("\n")):
            return IndexEntry(
                card_id=match.group(1),
                note_path=match.group(2),
                parser_id=match.group(3),
                start_line=int(match.group(4)),
                end_line=int(match.group(5)),
            )
        return None


def format_row(
    note_id: str,
    indexed_path: str,
    parser_id: str,
    start_line: int,
    end_line: int,
) -> str:
    return f"'{note_id}','{indexed_path}','{parser_id}','{start_line}','{end_line}'\n"


def rows_by_path(lines: list[str], row_reader: IndexRowReader) -> PathRows:
    grouped: PathRows = {}
    for line in lines:
        row = row_reader.parse(line)
        if row is None:
            continue
        grouped.setdefault(row.note_path, []).append(
            (row.card_id, row.parser_id, row.start_line, row.end_line)
        )
    return grouped
