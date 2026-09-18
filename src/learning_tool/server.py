"""FastMCP adapter: registers the tools and the study-widget resource."""

from __future__ import annotations

from importlib import resources
from typing import Any

from mcp.server.fastmcp import FastMCP

from learning_tool.config import load_config
from learning_tool.service import StudyService

SERVER_NAME = "learning-tool"
"""Name this server reports to the MCP host."""

WIDGET_URI = "ui://learning-tool/study"
"""URI of the MCP Apps study widget resource."""

WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
"""MIME type marking the resource as an MCP Apps UI document."""

WIDGET_TOOL_META = {"ui": {"resourceUri": WIDGET_URI}, "ui/resourceUri": WIDGET_URI}
"""UI tool metadata linking the widget.

The nested ``ui`` object is what the MCP Apps extension specifies. The flat
``ui/resourceUri`` alias carries the same value for hosts that read the
metadata that way; the reference example server publishes both, and Claude
Desktop renders only when the flat key is present.
"""

_WIDGET_FILENAME = "study.html"
"""Name of the widget file bundled inside the package's ui subpackage."""


def load_widget_html() -> str:
    """Read the study-widget HTML bundled inside the installed package.

    Returns:
        The widget's HTML source.
    """
    return (
        resources.files("learning_tool.ui")
        .joinpath(_WIDGET_FILENAME)
        .read_text(encoding="utf-8")
    )


def build_service() -> StudyService:
    """Build the study service from the environment configuration.

    Returns:
        A service rooted at the configured data directory.
    """
    return StudyService(load_config().data_dir)


def create_server(service: StudyService) -> FastMCP:
    """Create the FastMCP server exposing the study tools.

    Every tool body is a one-line delegation to the service; no business
    logic lives here.

    Args:
        service: The study service to delegate to.

    Returns:
        The configured FastMCP instance.
    """
    mcp = FastMCP(SERVER_NAME)

    @mcp.tool(
        description=(
            "Ingest a PDF and store its text as study material. Returns "
            "document_id, title and concept_count. Call get_material next to "
            "read the stored material before generating any flashcards or "
            "quiz questions."
        )
    )
    def ingest_material(pdf_path: str, title: str | None = None) -> dict[str, Any]:
        """Ingest a PDF and store its text as study material."""
        return service.ingest_material(pdf_path, title)

    @mcp.tool(
        description=(
            "Return the stored source material (text concepts) of a document. "
            "Use this material as the ONLY source when generating flashcards "
            "and quiz questions: every item must come from this document's "
            "material, never from outside facts or your own knowledge."
        )
    )
    def get_material(document_id: int) -> dict[str, Any]:
        """Return a document's stored source material."""
        return service.get_material(document_id)

    @mcp.tool(
        description=(
            "List every stored document with its id, title, concept count, "
            "flashcard count and quiz count. Call this at the start of a "
            "session to discover document ids."
        )
    )
    def list_documents() -> list[dict[str, Any]]:
        """List every stored document with its counts."""
        return service.list_documents()

    @mcp.tool(
        description=(
            "Return the flashcards and quiz questions already saved for a "
            "document. This returns generated study items; get_material "
            "returns the raw source concepts instead."
        )
    )
    def get_study_items(document_id: int) -> dict[str, Any]:
        """Return a document's saved flashcards and quiz questions."""
        return service.get_study_items(document_id)

    @mcp.tool(
        description=(
            "Return the study items due for review now, most overdue first, "
            "scheduled with the SM-2 spaced-repetition algorithm. "
            "Never-reviewed items are included after the overdue ones. Use "
            "this to pick what to study next. In hosts that support MCP "
            "Apps, calling this renders the interactive study widget."
        ),
        meta=WIDGET_TOOL_META,
    )
    def get_due_items(document_id: int) -> dict[str, Any]:
        """Return the items due for review now."""
        return service.get_due_items(document_id)

    @mcp.tool(
        description=(
            "Save generated flashcards to a document. Each card must have a "
            "front and a back. Returns the stored cards with their assigned "
            "ids."
        )
    )
    def save_flashcards(
        document_id: int, cards: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Save generated flashcards to a document."""
        return service.save_flashcards(document_id, cards)

    @mcp.tool(
        description=(
            "Save generated quiz questions to a document. Each question needs "
            "question, answer and question_type (multiple_choice or "
            "short_answer). A multiple_choice question also needs options: at "
            "least 2, with the answer exactly one of them. Returns the stored "
            "questions with their assigned ids."
        )
    )
    def save_quiz(
        document_id: int, questions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Save generated quiz questions to a document."""
        return service.save_quiz(document_id, questions)

    @mcp.tool(
        description=(
            "Record an answer to a study item. Quiz questions are graded "
            "automatically against the stored answer; flashcards are "
            "self-reported, so answer must be 'correct' or 'incorrect'. "
            "item_type is 'flashcard' or 'quiz'. Optional confidence is "
            "'guessed', 'unsure' or 'confident'. Returns is_correct and the "
            "updated progress."
        )
    )
    def submit_response(
        document_id: int,
        item_type: str,
        item_id: int,
        answer: str,
        confidence: str | None = None,
    ) -> dict[str, Any]:
        """Record and grade one answer."""
        return service.submit_response(
            document_id, item_type, item_id, answer, confidence
        )

    @mcp.tool(
        description=(
            "Return study progress for a document: mastered, to_review, "
            "in_progress, remaining and total item counts, plus a confidence "
            "breakdown counting each answered item's latest self-reported "
            "confidence (guessed, unsure, confident, unreported)."
        )
    )
    def get_session_state(document_id: int) -> dict[str, Any]:
        """Return a document's study progress."""
        return service.get_session_state(document_id)

    @mcp.tool(
        description=(
            "Export a document's flashcards and quiz questions to an "
            "Anki-importable CSV file on this machine. Writes the file and "
            "returns its path; it does not return the CSV text. Defaults to "
            "<data_dir>/exports/document-<id>-anki.csv, or pass output_path "
            "to choose the location. Set include_quiz false to export only "
            "flashcards."
        )
    )
    def export_document(
        document_id: int,
        output_path: str | None = None,
        include_quiz: bool = True,
    ) -> dict[str, Any]:
        """Write a document's items to an Anki-importable CSV file."""
        return service.export_document(document_id, output_path, include_quiz)

    @mcp.tool(
        description=(
            "DESTRUCTIVE and irreversible: permanently deletes a document "
            "along with its material, flashcards, quiz questions and all "
            "answer history. Confirm with the user by name (state the "
            "document's title) before calling this tool."
        )
    )
    def delete_document(document_id: int) -> dict[str, Any]:
        """Delete a document and everything stored against it."""
        return service.delete_document(document_id)

    @mcp.tool(
        description=(
            "DESTRUCTIVE and irreversible: erases a document's entire answer "
            "history, discarding mastery progress and review schedules. "
            "Flashcards and quiz questions are kept. Confirm with the user "
            "before calling this tool."
        )
    )
    def reset_progress(document_id: int) -> dict[str, Any]:
        """Erase a document's answer history."""
        return service.reset_progress(document_id)

    @mcp.resource(
        WIDGET_URI,
        name="study_widget",
        description="Interactive study-session widget (flashcards, quizzes, progress)",
        mime_type=WIDGET_MIME_TYPE,
        meta={"ui": {"prefersBorder": True}},
    )
    def study_widget() -> str:
        """Serve the bundled study-widget HTML."""
        return load_widget_html()

    return mcp


def main() -> None:
    """Run the Learning Tool MCP server over stdio."""
    create_server(build_service()).run()


if __name__ == "__main__":  # pragma: no cover - module entry point
    main()
