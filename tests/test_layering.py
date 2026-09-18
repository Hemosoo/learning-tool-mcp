"""Tests for the layering rules (spec 01)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "learning_tool"

ALLOWED_IMPORTS = {
    "config": set(),
    "storage.models": set(),
    "ingestion.pdf": set(),
    "scheduling.sm2": {"storage.models"},
    "export.anki": {"storage.models"},
    "storage.repository": {"storage.models", "scheduling.sm2"},
    "service": {
        "export.anki",
        "ingestion.pdf",
        "storage.models",
        "storage.repository",
        "scheduling.sm2",
    },
    "server": {"config", "service"},
}
"""Inner-package modules each module is permitted to import."""


def module_paths() -> list[tuple[str, Path]]:
    """List the package's modules with their source paths.

    Returns:
        Pairs of dotted module name (relative to the package) and path.
    """
    paths = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        name = ".".join(path.relative_to(PACKAGE_ROOT).with_suffix("").parts)
        paths.append((name, path))
    return paths


def internal_imports(path: Path) -> set[str]:
    """Collect the package-internal modules a source file imports.

    Args:
        path: The module's source path.

    Returns:
        Dotted module names relative to the package.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("learning_tool"):
                    found.add(alias.name[len("learning_tool.") :])
            continue
        else:
            continue
        if module.startswith("learning_tool"):
            found.add(module[len("learning_tool.") :].lstrip("."))
    return {name for name in found if name}


def test_every_module_is_covered_by_the_layering_table() -> None:
    """The table is exhaustive; a new module must declare its layer."""
    assert {name for name, _ in module_paths()} == set(ALLOWED_IMPORTS)


@pytest.mark.parametrize("name,path", module_paths())
def test_module_imports_stay_within_its_layer(name: str, path: Path) -> None:
    """Outer layers depend on inner ones and never the reverse."""
    assert internal_imports(path) <= ALLOWED_IMPORTS[name]


def test_no_module_imports_an_llm_or_network_client() -> None:
    """The server loads no LLM and makes no network calls at runtime."""
    forbidden = {
        "boto3",
        "openai",
        "anthropic",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "http",
    }

    for _, path in module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for imported in names:
                assert imported.split(".")[0] not in forbidden, (
                    f"{path.name} imports {imported}"
                )
