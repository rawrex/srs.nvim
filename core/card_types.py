import importlib
from pathlib import Path

from core.config import ReviewConfig
from core.parsers import ParserRegistry


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
    return importlib.import_module(f"packs.{module_name}")


def build_card_type_registry(config: ReviewConfig) -> ParserRegistry:
    registry = ParserRegistry(parsers={})
    for module_name in _pack_module_names():
        module = _load_pack_module(module_name)
        if module is None:
            continue
        register_pack = getattr(module, "register_pack", None)
        if callable(register_pack):
            register_pack(registry, config)
    if not registry.parsers:
        raise RuntimeError("No card type packs found in packs/")
    return registry


__all__ = ["build_card_type_registry"]
