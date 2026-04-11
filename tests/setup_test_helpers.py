import tempfile
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "setup" / "install.py"
UNINSTALL_SCRIPT = REPO_ROOT / "setup" / "uninstall.py"


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\ncwd: {cwd}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
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


@contextmanager
def temporary_git_repo(*, install: bool, with_repeat_marker: bool):
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = Path(tmp_dir)
        init_git_repo(repo_dir)
        if install:
            install_system(repo_dir)
        if with_repeat_marker:
            (repo_dir / ".repeat").write_text("", encoding="utf-8")
        yield repo_dir


@contextmanager
def temporary_session_repo(with_index: bool):
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        srs_dir = repo_root / ".srs"
        srs_dir.mkdir(parents=True, exist_ok=True)
        if with_index:
            (srs_dir / "index.txt").write_text("", encoding="utf-8")
        yield str(repo_root)


def tracked_head_files(repo_dir: Path) -> set[str]:
    return set(run_command(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo_dir).stdout.splitlines())


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
        rows.append((match.group(1), match.group(2), match.group(3), int(match.group(4)), int(match.group(5))))
    return rows
