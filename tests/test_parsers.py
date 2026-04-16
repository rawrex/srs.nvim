import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.api import Parser
from core.config import ReviewConfig
from core.parsers import ParserRegistry, build_parser_registry


class _Parser(Parser):
    parser_id = ""
    priority = 0

    def interpret_text(self, note_text: str):
        return []

    def build_card(self, source_text: str, index_entry, metadata):
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

    def test_build_parser_registry_loads_builtin_packs(self) -> None:
        registry = build_parser_registry(ReviewConfig())

        self.assertIn("cloze", registry.parsers)
        self.assertIn("quote_block", registry.parsers)
        self.assertIn("quote_block_cloze", registry.parsers)

    def test_build_parser_registry_raises_when_no_pack_modules_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir)

            with patch("core.parsers._pack_modules_dir", return_value=packs_dir):
                with self.assertRaises(RuntimeError):
                    build_parser_registry(ReviewConfig())
