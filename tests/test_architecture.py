import ast
import unittest
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1] / "core"
FORBIDDEN_ROOTS = ("autoparse", "hooks")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class CoreBoundaryTest(unittest.TestCase):
    def test_core_does_not_import_autoparse_or_hooks(self) -> None:
        offenders: list[str] = []
        for path in sorted(CORE_DIR.rglob("*.py")):
            for module in _imported_modules(path):
                if any(module == root or module.startswith(root + ".") for root in FORBIDDEN_ROOTS):
                    offenders.append(f"{path.relative_to(CORE_DIR.parent)}: {module}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
