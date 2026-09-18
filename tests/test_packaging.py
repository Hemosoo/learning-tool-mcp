"""Tests for project metadata and packaging (spec 02)."""

from __future__ import annotations

from pathlib import Path

import pytest

import learning_tool

tomllib = pytest.importorskip("tomllib", reason="tomllib is stdlib from 3.11")

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    """Return the parsed project configuration."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_distribution_metadata(pyproject: dict) -> None:
    """Name, version, and Python floor are as specified."""
    project = pyproject["project"]

    assert project["name"] == "learning-tool-mcp"
    assert project["version"] == learning_tool.__version__ == "0.7.0"
    assert project["requires-python"] == ">=3.10"
    assert project["description"] == (
        "An MCP server that turns PDFs into flashcards and quizzes, "
        "with session tracking"
    )


def test_project_is_mit_licensed_with_the_file_packaged(pyproject: dict) -> None:
    """An open-source project needs a licence to actually be open source."""
    project = pyproject["project"]
    licence = Path(__file__).resolve().parents[1] / "LICENSE"

    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert licence.is_file()
    assert "MIT License" in licence.read_text(encoding="utf-8")


def test_runtime_dependencies_carry_the_normative_bounds(pyproject: dict) -> None:
    """Only the three runtime dependencies, each bounded."""
    dependencies = set(pyproject["project"]["dependencies"])

    assert dependencies == {"mcp>=1.12,<2", "pypdf>=4,<6", "pydantic>=2,<3"}


def test_no_llm_database_or_http_dependency_creeps_in(pyproject: dict) -> None:
    """The fully local, no-LLM stance is a packaging constraint too."""
    declared = " ".join(
        pyproject["project"]["dependencies"]
        + pyproject["project"]["optional-dependencies"]["dev"]
    ).lower()

    for forbidden in (
        "boto3",
        "openai",
        "anthropic",
        "langchain",
        "requests",
        "httpx",
        "sqlalchemy",
        "psycopg",
    ):
        assert forbidden not in declared


def test_dev_extra_is_pytest_and_ruff(pyproject: dict) -> None:
    """The dev extra is exactly the test and lint tooling."""
    assert set(pyproject["project"]["optional-dependencies"]["dev"]) == {
        "pytest>=8,<9",
        "ruff>=0.15,<1",
    }


def test_console_script_starts_the_stdio_server(pyproject: dict) -> None:
    """The installed script points at the server entry point."""
    assert pyproject["project"]["scripts"] == {
        "learning-tool-mcp": "learning_tool.server:main"
    }


def test_wheel_packages_the_src_layout_package(pyproject: dict) -> None:
    """Hatchling builds the package from the src layout."""
    assert pyproject["build-system"]["build-backend"] == "hatchling.build"
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/learning_tool"
    ]


def test_widget_ships_inside_the_package_so_the_wheel_carries_it() -> None:
    """The widget is package data, not a repo-only file."""
    widget = Path(learning_tool.__file__).parent / "ui" / "study.html"

    assert widget.is_file()
    assert widget.read_text(encoding="utf-8").strip().startswith("<!DOCTYPE html>")


def test_pytest_and_ruff_configuration(pyproject: dict) -> None:
    """Tooling configuration lives in the single config file."""
    tools = pyproject["tool"]

    assert tools["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert tools["pytest"]["ini_options"]["pythonpath"] == ["src"]
    assert tools["ruff"]["line-length"] == 88
    assert tools["ruff"]["lint"]["select"] == ["E", "W", "F", "I", "UP"]
    assert tools["ruff"]["lint"]["ignore"] == ["E501"]
