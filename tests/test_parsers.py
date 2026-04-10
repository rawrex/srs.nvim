import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.api import Parser
from core.config import ReviewConfig
from core.parsers import (
    ParserRegistry,
    _build_parser_registry,
    _load_pack_module,
    _load_registered_packs,
    _pack_module_names,
)


class _Parser(Parser):
    parser_id = ""
    priority = 0

    def split_note_into_cards(self, note_text: str):
        return []

    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        end_line: int,
        card_path: str,
        metadata,
    ):
        raise NotImplementedError


class _LowParser(_Parser):
    parser_id = "z_low"
    priority = 0


class _HighParser(_Parser):
    parser_id = "a_high"
    priority = 10


class ParsersTest(unittest.TestCase):
    def test_registry_orders_by_priority_then_parser_id(self) -> None:
        registry = ParserRegistry(parsers={})
        registry.register(_LowParser())
        registry.register(_HighParser())

        ordered_ids = [parser.parser_id for parser in registry.ordered()]

        self.assertEqual(["a_high", "z_low"], ordered_ids)

    def test_registry_default_returns_last_ordered_parser(self) -> None:
        registry = ParserRegistry(parsers={})
        registry.register(_HighParser())
        registry.register(_LowParser())

        default_parser = registry.default()

        self.assertEqual("z_low", default_parser.parser_id)

    def test_registry_default_raises_when_empty(self) -> None:
        registry = ParserRegistry(parsers={})
        with self.assertRaises(KeyError):
            registry.default()

    def test_pack_module_names_filters_private_and_init(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir)
            for name in ["__init__.py", "_private.py", "alpha.py", "beta.py"]:
                (packs_dir / name).write_text("", encoding="utf-8")

            with patch("core.parsers._pack_modules_dir", return_value=packs_dir):
                names = _pack_module_names()

        self.assertEqual(["alpha", "beta"], names)

    def test_load_pack_module_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir)
            with patch("core.parsers._pack_modules_dir", return_value=packs_dir):
                self.assertIsNone(_load_pack_module("missing"))

    def test_load_registered_packs_calls_register_pack_when_callable(self) -> None:
        registry = ParserRegistry(parsers={})
        register_pack = Mock()
        module_with_register = types.SimpleNamespace(register_pack=register_pack)
        module_without_register = types.SimpleNamespace(register_pack=1)

        with (
            patch("core.parsers._pack_module_names", return_value=["a", "b"]),
            patch(
                "core.parsers._load_pack_module",
                side_effect=[module_with_register, module_without_register],
            ),
        ):
            _load_registered_packs(registry, ReviewConfig())

        register_pack.assert_called_once_with(registry, ReviewConfig())

    def test_build_parser_registry_raises_when_no_packs_register(self) -> None:
        with patch("core.parsers._load_registered_packs"):
            with self.assertRaises(RuntimeError):
                _build_parser_registry(ReviewConfig())

    def test_build_parser_registry_returns_registry_with_parsers(self) -> None:
        def fake_load(registry: ParserRegistry, _config: ReviewConfig) -> None:
            registry.register(_LowParser())

        with patch("core.parsers._load_registered_packs", side_effect=fake_load):
            registry = _build_parser_registry(ReviewConfig())

        self.assertIn("z_low", registry.parsers)


if __name__ == "__main__":
    unittest.main()
