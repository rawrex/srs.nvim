#!/usr/bin/env python3
"""Convert the old backtick-wrapped cloze syntax to Markdown bold.

Old form:   `~{some text}`
New form:   **some text**

Usage:
    python migrate_cloze_syntax.py /path/to/vault
    python migrate_cloze_syntax.py /path/to/vault --exclude srs.nvim

The script works on bytes, so UTF-8 text and original line endings are preserved.
Hidden directories (including .git) are skipped. It is safe to rerun: once
converted, no old syntax remains to match.
"""

import argparse
import os
import re
from pathlib import Path

# The content is allowed to contain braces, e.g. `~{:g/{pattern}/t$}`.
# [^`]* is greedy and the final `}` is the last one before the closing backtick.
CLOZE_RE = re.compile(rb"(`+)~\{([^`]*)\}\1")
DEFAULT_EXCLUDES = {"node_modules", "__pycache__"}


def format_content(content: bytes) -> bytes:
    """Wrap content in bold, keeping leading/trailing asterisks valid."""
    if content.startswith(b"*") or content.endswith(b"*"):
        content = content.replace(b"*", b"&#42;")
    return b"**" + content + b"**"


def iter_markdown_files(vault: Path, excludes: set[str]):
    for root, dirs, files in os.walk(vault):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and name not in excludes)
        for name in sorted(files):
            path = Path(root) / name
            if path.suffix.lower() in {".md", ".markdown"}:
                yield path


def migrate_file(path: Path) -> int:
    data = path.read_bytes()
    updated, count = CLOZE_RE.subn(lambda match: format_content(match.group(2)), data)
    if count:
        path.write_bytes(updated)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert `~{...}` clozes to `**...**` in a Markdown vault.")
    parser.add_argument("vault", nargs="?", default=".", help="Vault root directory (default: current directory)")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="Directory name to skip (repeatable), e.g. --exclude srs.nvim",
    )
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        parser.error(f"not a directory: {vault}")

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    files = 0
    replacements = 0

    for path in iter_markdown_files(vault, excludes):
        count = migrate_file(path)
        if count:
            files += 1
            replacements += count
            print(f"{path.relative_to(vault)}: {count}")

    print(f"replaced {replacements} occurrence(s) in {files} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
