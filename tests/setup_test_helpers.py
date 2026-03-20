import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.py"
UNINSTALL_SCRIPT = REPO_ROOT / "uninstall.py"


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def init_git_repo(repo_dir: Path) -> None:
    run_command(["git", "init"], cwd=repo_dir)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)
    run_command(["git", "config", "user.name", "Test User"], cwd=repo_dir)


def install_system(repo_dir: Path) -> None:
    run_command([sys.executable, str(INSTALL_SCRIPT)], cwd=repo_dir)


def uninstall_system(repo_dir: Path) -> None:
    run_command([sys.executable, str(UNINSTALL_SCRIPT)], cwd=repo_dir)


def tracked_head_files(repo_dir: Path) -> set[str]:
    return set(
        run_command(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo_dir
        ).stdout.splitlines()
    )


def read_index_rows(index_path: Path) -> list[tuple[str, str, str, int, int]]:
    if not index_path.exists():
        return []
    row_re = re.compile(r"^'([^']*)','([^']*)','([^']*)','(\d+)','(\d+)'$")
    rows: list[tuple[str, str, str, int, int]] = []
    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = row_re.match(line)
        if not match:
            raise AssertionError(f"unexpected index row format: {line}")
        rows.append(
            (
                match.group(1),
                match.group(2),
                match.group(3),
                int(match.group(4)),
                int(match.group(5)),
            )
        )
    return rows
