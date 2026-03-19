import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .api import NoteParser


@dataclass
class ParserRegistry:
    parsers: Dict[str, NoteParser]

    def register(self, parser: NoteParser) -> None:
        self.parsers[parser.parser_id] = parser

    def get(self, parser_id: str) -> NoteParser:
        return self.parsers[parser_id]

    def default(self) -> NoteParser:
        ordered = self.ordered()
        if not ordered:
            raise KeyError("No parsers are registered")
        return ordered[-1]

    def ordered(self) -> list[NoteParser]:
        return sorted(
            self.parsers.values(),
            key=lambda parser: (-parser.priority, parser.parser_id),
        )


def _pack_modules_dir() -> Path:
    return Path(__file__).resolve().parent / "packs"


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
    import_name = f"reviewing.packs.{module_name}"
    spec = importlib.util.spec_from_file_location(import_name, module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = module
    spec.loader.exec_module(module)
    return module


def _load_registered_packs(registry: ParserRegistry) -> None:
    for module_name in _pack_module_names():
        module = _load_pack_module(module_name)
        if module is None:
            continue
        register_pack = getattr(module, "register_pack", None)
        if callable(register_pack):
            register_pack(registry)


def _build_parser_registry() -> ParserRegistry:
    registry = ParserRegistry(parsers={})
    _load_registered_packs(registry)
    if not registry.parsers:
        raise RuntimeError("No parser packs found in reviewing/packs")
    return registry


PARSER_REGISTRY: ParserRegistry = _build_parser_registry()


from .packs.cloze import ClozeParser  # noqa: E402


__all__ = [
    "PARSER_REGISTRY",
    "ClozeParser",
]
