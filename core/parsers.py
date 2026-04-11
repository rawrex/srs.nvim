import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from core.config import ReviewConfig

from .api import Parser


@dataclass
class ParserRegistry:
    parsers: Dict[str, Parser]

    def register(self, parser: Parser) -> None:
        self.parsers[parser.parser_id] = parser

    def get(self, parser_id: str) -> Parser:
        return self.parsers[parser_id]

    def default(self) -> Parser:
        ordered = self.ordered()
        if not ordered:
            raise KeyError("No parsers are registered")
        return ordered[-1]

    def ordered(self) -> list[Parser]:
        return sorted(self.parsers.values(), key=lambda parser: (-parser.priority, parser.parser_id))


def _pack_modules_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "packs"


def _pack_module_names() -> list[str]:
    names: list[str] = []
    packs_dir = _pack_modules_dir()
    if not packs_dir.exists():
        return names
    for path in sorted(packs_dir.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        names.append(path.stem)
    return names


def _load_pack_module(module_name: str):
    module_path = _pack_modules_dir() / f"{module_name}.py"
    if not module_path.exists():
        return None
    import_name = f"packs.{module_name}"
    return importlib.import_module(import_name)


def _load_registered_packs(registry: ParserRegistry, config: ReviewConfig) -> None:
    for module_name in _pack_module_names():
        module = _load_pack_module(module_name)
        if module is None:
            continue
        register_pack = getattr(module, "register_pack", None)
        if callable(register_pack):
            register_pack(registry, config)


def build_parser_registry(config: ReviewConfig) -> ParserRegistry:
    registry = ParserRegistry(parsers={})
    _load_registered_packs(registry, config)
    if not registry.parsers:
        raise RuntimeError("No parser packs found in packs/")
    return registry


def _build_parser_registry(config: ReviewConfig) -> ParserRegistry:
    return build_parser_registry(config)


__all__ = ["ParserRegistry", "build_parser_registry"]
