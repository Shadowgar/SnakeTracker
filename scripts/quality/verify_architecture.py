#!/usr/bin/env python3
"""Reject imports that violate SnakeTracker's top-level dependency rules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN_IMPORTS = {
    "application": {"bootstrap", "infrastructure", "presentation", "worker"},
    "infrastructure": {"bootstrap", "presentation", "worker"},
    "presentation": {"bootstrap", "infrastructure", "worker"},
}


def imported_layers(tree: ast.AST) -> set[str]:
    layers: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            parts = module.split(".")
            if len(parts) > 1 and parts[0] == "snaketracker":
                layers.add(parts[1])
    return layers


def violations(source_root: Path) -> list[str]:
    errors: list[str] = []
    package_root = source_root / "snaketracker"
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root)
        if len(relative.parts) < 2:
            continue
        layer = relative.parts[0]
        forbidden = FORBIDDEN_IMPORTS.get(layer, set())
        if not forbidden:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for target in sorted(imported_layers(tree) & forbidden):
            errors.append(f"{relative}: {layer} cannot import {target}")
    return errors


def main() -> int:
    source_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src")
    errors = violations(source_root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
