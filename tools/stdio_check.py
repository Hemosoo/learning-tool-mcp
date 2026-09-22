"""Drive the installed server over real stdio, as an MCP host would.

Exercises the transport, the tool catalog, the UI resource and its metadata
end to end against a throwaway data directory, so a packaging or startup
regression shows up without launching a real host.

Usage:
    .venv/bin/python tools/stdio_check.py [--pdf path/to/file.pdf]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = REPO_ROOT / ".venv" / "bin" / "learning-tool-mcp"
WIDGET_URI = "ui://learning-tool/study"


def server_command() -> list[str] | None:
    """Locate the installed server.

    Prefers the project's virtual environment, and falls back to the console
    script on the PATH so this runs on a CI runner that has no venv.

    Returns:
        Argv for launching the server, or None when it is not installed.
    """
    if VENV_BIN.exists():
        return [str(VENV_BIN)]
    found = shutil.which("learning-tool-mcp")
    if found:
        return [found]
    return None


class StdioClient:
    """A minimal newline-delimited JSON-RPC client over a subprocess."""

    def __init__(self, command: list[str], data_dir: Path) -> None:
        """Start the server.

        Args:
            command: Argv of the server to run.
            data_dir: Value for LEARNING_TOOL_DATA_DIR.
        """
        import os

        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "LEARNING_TOOL_DATA_DIR": str(data_dir)},
        )
        self._next_id = 0

    def request(
        self, method: str, params: dict | None = None, timeout: float = 30
    ) -> dict:
        """Send a request and return its result.

        Args:
            method: JSON-RPC method name.
            params: Method parameters.
            timeout: Seconds to wait for the response.

        Returns:
            The response's `result` member.

        Raises:
            TimeoutError: If the server does not answer in time.
        """
        self._next_id += 1
        self._write(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": method,
                "params": params or {},
            }
        )
        stdout = self._proc.stdout
        assert stdout is not None  # Popen was given a pipe
        box: dict[str, str] = {}
        reader = threading.Thread(
            target=lambda: box.setdefault("line", stdout.readline()),
            daemon=True,
        )
        reader.start()
        reader.join(timeout)
        if not box.get("line"):
            raise TimeoutError(f"no response to {method}")
        return json.loads(box["line"])["result"]

    def notify(self, method: str) -> None:
        """Send a notification.

        Args:
            method: JSON-RPC method name.
        """
        self._write({"jsonrpc": "2.0", "method": method})

    def _write(self, message: dict) -> None:
        """Write one JSON-RPC message.

        Args:
            message: The message to send.
        """
        stdin = self._proc.stdin
        assert stdin is not None  # Popen was given a pipe
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()

    def close(self) -> None:
        """Terminate the server."""
        self._proc.terminate()


def main() -> int:
    """Run the checks and report pass or fail.

    Returns:
        Process exit status: 0 when every check passed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf", type=Path, help="ingest this PDF instead of skipping ingestion"
    )
    args = parser.parse_args()

    command = server_command()
    if command is None:
        print(
            f"server not found at {VENV_BIN} nor on the PATH\n"
            "install it with: pip install -e '.[dev]'"
        )
        return 1

    data_dir = Path(tempfile.mkdtemp())
    client = StdioClient(command, data_dir)
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(
            f"  {'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}"
        )
        if not ok:
            failures.append(label)

    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "stdio_check", "version": "1"},
            },
        )
        client.notify("notifications/initialized")
        print(f"server: {init['serverInfo']['name']}\n")

        tools = {t["name"]: t for t in client.request("tools/list")["tools"]}
        check("12 tools registered", len(tools) == 12, f"{len(tools)} found")

        meta = tools.get("get_due_items", {}).get("_meta", {})
        check(
            "nested ui.resourceUri", meta.get("ui", {}).get("resourceUri") == WIDGET_URI
        )
        check(
            "flat ui/resourceUri (hosts read this one)",
            meta.get("ui/resourceUri") == WIDGET_URI,
        )
        check(
            "no other tool carries ui metadata",
            not any(
                (t.get("_meta") or {}).get("ui")
                or (t.get("_meta") or {}).get("ui/resourceUri")
                for name, t in tools.items()
                if name != "get_due_items"
            ),
        )

        resources = client.request("resources/list")["resources"]
        check("one ui resource", len(resources) == 1)
        check(
            "resource mime type",
            resources[0]["mimeType"] == "text/html;profile=mcp-app",
        )

        html = client.request("resources/read", {"uri": WIDGET_URI})["contents"][0][
            "text"
        ]
        check(
            "widget served",
            html.strip().startswith("<!DOCTYPE html>"),
            f"{len(html)} bytes",
        )
        check("widget self-contained", "http://" not in html and "https://" not in html)
        check(
            "export_document registered",
            "export_document" in tools
            and "Anki" in tools["export_document"]["description"],
        )
        check(
            "session state exposes confidence",
            "confidence" in tools["get_session_state"]["description"],
        )
        check(
            "handshake sends appInfo, not clientInfo",
            "appInfo:" in html and "clientInfo" not in html,
        )

        if args.pdf:
            doc = client.request(
                "tools/call",
                {
                    "name": "ingest_material",
                    "arguments": {"pdf_path": str(args.pdf.resolve())},
                },
            )
            ingested = doc["structuredContent"]
            check(
                "ingest_material",
                ingested["concept_count"] > 0,
                f"{ingested['concept_count']} concepts",
            )
            document_id = ingested["document_id"]
            client.request(
                "tools/call",
                {
                    "name": "save_flashcards",
                    "arguments": {
                        "document_id": document_id,
                        "cards": [{"front": "f", "back": "b"}],
                    },
                },
            )
            graded = client.request(
                "tools/call",
                {
                    "name": "submit_response",
                    "arguments": {
                        "document_id": document_id,
                        "item_type": "flashcard",
                        "item_id": 1,
                        "answer": "correct",
                    },
                },
            )["structuredContent"]
            check("submit_response grades and records", graded["is_correct"] is True)
            check("progress recomputed", graded["progress"]["in_progress"] == 1)
        else:
            print("\n  (pass --pdf to also exercise ingestion and grading)")
    finally:
        client.close()

    print(
        f"\n{'all checks passed' if not failures else str(len(failures)) + ' check(s) failed'}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
