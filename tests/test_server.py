"""Tests for the FastMCP adapter and the served widget (specs 08, 09)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from learning_tool.config import DATA_DIR_ENV_VAR
from learning_tool.server import (
    SERVER_NAME,
    WIDGET_MIME_TYPE,
    WIDGET_TOOL_META,
    WIDGET_URI,
    build_service,
    create_server,
    load_widget_html,
)
from learning_tool.service import StudyService

EXPECTED_TOOLS = {
    "ingest_material",
    "get_material",
    "list_documents",
    "get_study_items",
    "get_due_items",
    "save_flashcards",
    "save_quiz",
    "submit_response",
    "get_session_state",
    "delete_document",
    "reset_progress",
    "export_document",
}


@pytest.fixture
def server(tmp_path: Path):
    """Build the production server over a temporary data directory."""
    return create_server(StudyService(tmp_path / "data"))


def tools_by_name(server) -> dict[str, Any]:
    """Return the server's registered tools keyed by name.

    Args:
        server: The FastMCP instance.

    Returns:
        A mapping from tool name to its registered definition.
    """
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def test_server_is_named_learning_tool(server) -> None:
    """The server identifies itself to the host by name."""
    assert SERVER_NAME == "learning-tool"
    assert server.name == "learning-tool"


def test_exactly_twelve_tools_with_the_expected_names(server) -> None:
    """The tool catalog is closed: these 12 and nothing else."""
    registered = tools_by_name(server)

    assert len(registered) == 12
    assert set(registered) == EXPECTED_TOOLS


def test_the_ui_resource_is_registered_with_the_mcp_app_mime_type(server) -> None:
    """Exactly one resource serves the widget at its ui:// URI."""
    resources = asyncio.run(server.list_resources())

    assert len(resources) == 1
    resource = resources[0]
    assert str(resource.uri) == WIDGET_URI == "ui://learning-tool/study"
    assert resource.name == "study_widget"
    assert resource.mimeType == WIDGET_MIME_TYPE == "text/html;profile=mcp-app"
    assert resource.description == (
        "Interactive study-session widget (flashcards, quizzes, progress)"
    )
    assert resource.meta == {"ui": {"prefersBorder": True}}


def test_the_resource_serves_non_empty_widget_html(server) -> None:
    """Reading the resource yields the bundled HTML document."""
    contents = list(asyncio.run(server.read_resource(WIDGET_URI)))

    assert len(contents) == 1
    html = contents[0].content
    assert contents[0].mime_type == WIDGET_MIME_TYPE
    assert html.strip().startswith("<!DOCTYPE html>")
    assert len(html) > 1000


def test_widget_html_is_loaded_from_the_installed_package() -> None:
    """The widget ships inside the package, not beside a repo checkout."""
    assert load_widget_html().strip().endswith("</html>")


def test_widget_html_contains_no_external_urls() -> None:
    """The widget is fully self-contained; the iframe may have no network."""
    html = load_widget_html()

    assert "http://" not in html
    assert "https://" not in html


def test_get_due_items_carries_the_ui_resource_metadata(server) -> None:
    """Only get_due_items links the widget resource."""
    registered = tools_by_name(server)

    assert registered["get_due_items"].meta == WIDGET_TOOL_META
    assert registered["get_due_items"].meta["ui"] == {"resourceUri": WIDGET_URI}
    assert registered["get_due_items"].meta["ui/resourceUri"] == WIDGET_URI
    for name, tool in registered.items():
        if name != "get_due_items":
            assert not (tool.meta or {}).get("ui")
            assert not (tool.meta or {}).get("ui/resourceUri")


def test_destructive_tool_descriptions_demand_confirmation(server) -> None:
    """Both destructive tools say so and ask the host to confirm."""
    registered = tools_by_name(server)

    for name in ("delete_document", "reset_progress"):
        description = registered[name].description
        assert "DESTRUCTIVE" in description
        assert "irreversible" in description
        assert "onfirm with the user" in description


def test_no_destructive_tool_takes_a_confirm_parameter(server) -> None:
    """Confirmation is guidance, not a host-set boolean."""
    registered = tools_by_name(server)

    for name in ("delete_document", "reset_progress"):
        assert set(registered[name].inputSchema["properties"]) == {"document_id"}


def test_get_material_description_carries_the_grounding_instruction(server) -> None:
    """The only-source instruction is how grounding is enforced."""
    description = tools_by_name(server)["get_material"].description

    assert "ONLY source" in description
    assert "never from outside facts" in description


def test_ingest_material_description_points_at_get_material(server) -> None:
    """Ingestion tells the host to read the material before generating."""
    assert "get_material" in tools_by_name(server)["ingest_material"].description


def test_get_due_items_description_mentions_the_widget_and_ordering(server) -> None:
    """The due-items description explains ordering and the widget."""
    description = tools_by_name(server)["get_due_items"].description

    assert "most overdue first" in description
    assert "SM-2" in description
    assert "widget" in description


def test_save_quiz_description_states_the_option_rules(server) -> None:
    """The host learns the multiple-choice rules from the description."""
    description = tools_by_name(server)["save_quiz"].description

    assert "multiple_choice" in description
    assert "short_answer" in description
    assert "at least 2" in description


def test_submit_response_description_states_the_grading_rules(server) -> None:
    """The host learns self-report and confidence vocabulary."""
    description = tools_by_name(server)["submit_response"].description

    assert "'correct' or 'incorrect'" in description
    assert "guessed" in description


def test_get_session_state_description_mentions_the_confidence_breakdown(
    server,
) -> None:
    """The host learns the breakdown exists and what its keys are."""
    description = tools_by_name(server)["get_session_state"].description

    assert "confidence" in description
    assert "unreported" in description


def test_export_document_description_states_it_writes_a_file(server) -> None:
    """The host must know a path is written, not CSV text returned."""
    description = tools_by_name(server)["export_document"].description

    assert "Anki" in description
    assert "writes the file" in description.lower()
    assert "output_path" in description


def test_every_tool_has_a_description(server) -> None:
    """Descriptions are the product; none may be missing."""
    for tool in tools_by_name(server).values():
        assert tool.description


def test_tools_delegate_to_the_service_end_to_end(tmp_path: Path, pdf_factory) -> None:
    """A full round trip through the adapter reaches real storage."""
    server = create_server(StudyService(tmp_path / "data"))
    pdf = pdf_factory(["Photosynthesis converts light into sugar."], name="bio.pdf")

    async def run() -> dict[str, Any]:
        await server.call_tool("ingest_material", {"pdf_path": str(pdf)})
        await server.call_tool(
            "save_flashcards",
            {"document_id": 1, "cards": [{"front": "Inputs?", "back": "Light"}]},
        )
        _, submitted = await server.call_tool(
            "submit_response",
            {
                "document_id": 1,
                "item_type": "flashcard",
                "item_id": 1,
                "answer": "correct",
            },
        )
        _, due = await server.call_tool("get_due_items", {"document_id": 1})
        return {"submitted": submitted, "due": due}

    result = asyncio.run(run())

    assert result["submitted"]["is_correct"] is True
    assert result["submitted"]["progress"]["in_progress"] == 1
    assert result["due"]["due_count"] == 0
    assert (tmp_path / "data" / "documents" / "1.json").is_file()


def test_build_service_uses_the_environment_data_directory(
    tmp_path: Path, monkeypatch, pdf_factory
) -> None:
    """The console-script path stores data where the environment says."""
    data_dir = tmp_path / "configured"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(data_dir))
    pdf = pdf_factory(["Configured storage location."], name="c.pdf")

    build_service().ingest_material(str(pdf))

    assert (data_dir / "documents" / "1.json").is_file()


def test_main_runs_the_server_over_stdio(monkeypatch, tmp_path: Path) -> None:
    """The entry point composes builder and factory, then serves stdio."""
    from learning_tool import server as server_module

    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path / "data"))
    transports: list[str] = []

    def fake_run(self, transport: str = "stdio", mount_path: str | None = None) -> None:
        transports.append(transport)

    monkeypatch.setattr(server_module.FastMCP, "run", fake_run)

    server_module.main()

    assert transports == ["stdio"]
