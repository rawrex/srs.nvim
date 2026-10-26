import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fsrs import Scheduler

from core.config import load_review_config, write_scheduler_parameters
from tests.setup_test_helpers import runtime_context


class ReviewConfigTest(unittest.TestCase):
    @staticmethod
    def _config_path(repo_root: str) -> str:
        srs_dir = os.path.join(repo_root, ".srs")
        os.makedirs(srs_dir, exist_ok=True)
        return os.path.join(srs_dir, "config.json")

    @classmethod
    def _load_config(cls, repo_root: str):
        with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
            return load_review_config()

    def test_load_review_config_uses_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            config = self._load_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_reads_custom_values(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "scheduler": {
                            "parameters": [
                                0.5,
                                1.2931,
                                2.3065,
                                8.2956,
                                6.4133,
                                0.8334,
                                3.0194,
                                0.001,
                                1.8722,
                                0.1666,
                                0.796,
                                1.4835,
                                0.0614,
                                0.2629,
                                1.6483,
                                0.6014,
                                1.8729,
                                0.5425,
                                0.0912,
                                0.0658,
                                0.1542,
                            ],
                            "desired_retention": 0.88,
                            "learning_steps": [30, 300],
                            "relearning_steps": [120],
                            "maximum_interval": 12345,
                            "enable_fuzzing": False,
                        }
                    },
                    handle,
                )

            config = self._load_config(repo_root)

        scheduler = config.build_scheduler()
        self.assertEqual(0.5, scheduler.parameters[0])
        self.assertEqual(0.88, scheduler.desired_retention)
        self.assertEqual([30, 300], [int(step.total_seconds()) for step in scheduler.learning_steps])
        self.assertEqual([120], [int(step.total_seconds()) for step in scheduler.relearning_steps])
        self.assertEqual(12345, scheduler.maximum_interval)
        self.assertFalse(scheduler.enable_fuzzing)

    def test_load_review_config_uses_default_scheduler_when_section_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"review": {}}, handle)

            config = self._load_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_falls_back_to_defaults_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json")

            config = self._load_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_ignores_legacy_cloze_section(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"cloze": {"syntax": {"open": "", "close": 1}}}, handle)

            config = self._load_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_uses_default_scheduler_when_scheduler_values_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "scheduler": {
                            "parameters": [0.1],
                            "desired_retention": 2,
                            "learning_steps": [60, -1],
                            "relearning_steps": ["bad"],
                            "maximum_interval": 0,
                            "enable_fuzzing": "yes",
                        }
                    },
                    handle,
                )

            config = self._load_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_write_scheduler_parameters_preserves_other_keys(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {"cloze": {"syntax": {"open": "[[", "close": "]]"}}, "scheduler": {"desired_retention": 0.9}},
                    handle,
                )

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                write_scheduler_parameters((0.1, 0.2, 0.3))

            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        self.assertEqual([0.1, 0.2, 0.3], stored["scheduler"]["parameters"])
        self.assertEqual(0.9, stored["scheduler"]["desired_retention"])
        self.assertEqual({"syntax": {"open": "[[", "close": "]]"}}, stored["cloze"])

    def test_write_scheduler_parameters_creates_config_when_missing(self) -> None:
        parameters = list(Scheduler().parameters)
        parameters[0] = 0.5
        with tempfile.TemporaryDirectory() as repo_root:
            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                write_scheduler_parameters(parameters)
                config = load_review_config()

            path = os.path.join(repo_root, ".srs", "config.json")
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        self.assertEqual(parameters, stored["scheduler"]["parameters"])
        self.assertEqual(0.5, config.build_scheduler().parameters[0])

    def test_write_scheduler_parameters_uses_atomic_replace_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = self._config_path(repo_root)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                write_scheduler_parameters((0.1,))

            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".tmp"))
            with open(path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()

        self.assertTrue(raw_text.endswith("\n"))
