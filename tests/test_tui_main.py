import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tui
from core.config import ReviewConfig
from tests.setup_test_helpers import FakeConsole, runtime_context


class TuiMainTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        with (
            patch("tui.util.init_runtime_context"),
            patch("tui.util._RUNTIME_CONTEXT", runtime_context(""), create=True),
            patch("builtins.print") as print_mock,
        ):
            code = tui.main()

        self.assertEqual(1, code)
        print_mock.assert_called_once_with("Not inside a git repository.")

    def test_main_runs_session_with_loaded_config(self) -> None:
        runtime = runtime_context("/repo")
        with (
            patch("tui.util.init_runtime_context", return_value=runtime),
            patch("tui.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("tui.load_review_config", return_value=ReviewConfig()),
            patch("tui.run", return_value=7) as run_mock,
        ):
            code = tui.main()

        self.assertEqual(7, code)
        run_mock.assert_called_once()

    def test_main_handles_keyboard_interrupt(self) -> None:
        runtime = runtime_context("/repo")
        with (
            patch("tui.util.init_runtime_context", return_value=runtime),
            patch("tui.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("tui.load_review_config", return_value=ReviewConfig()),
            patch("tui.run", side_effect=KeyboardInterrupt),
            patch("builtins.print") as print_mock,
        ):
            code = tui.main()

        self.assertEqual(0, code)
        print_mock.assert_called_once_with("\nExit.")

    def test_run_spawns_backend_and_drives_client(self) -> None:
        process = SimpleNamespace(stdout=io.StringIO(""), stdin=io.StringIO(), wait=lambda: None, returncode=0)
        with (
            patch("tui.spawn_backend", return_value=process) as spawn_mock,
            patch("tui.terminate_backend") as terminate_mock,
        ):
            code = tui.run(console=FakeConsole(), config=ReviewConfig(), repo_root="/repo")  # type: ignore[arg-type]

        self.assertEqual(0, code)
        spawn_mock.assert_called_once_with("/repo")
        terminate_mock.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
