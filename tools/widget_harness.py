"""Serve the study widget to a browser host stub for manual verification.

Spec 10 requires widget changes to be exercised against a host, because the
pytest suite can only assert against the widget's source text. This script
serves the live widget and a live due-items payload to `widget_host.html`,
which implements the host half of the bridge.

Usage:
    .venv/bin/python tools/widget_harness.py [--port 8901] [--document 1]
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from learning_tool.server import load_widget_html
from learning_tool.service import StudyService

TOOLS_DIR = Path(__file__).resolve().parent


class HarnessHandler(BaseHTTPRequestHandler):
    """Serves the host stub, the live widget, and a live due-items payload."""

    def __init__(
        self, *args: object, service: StudyService, document_id: int, **kw: object
    ) -> None:
        """Bind the handler to the service it reports on.

        Args:
            service: Study service supplying the due-items payload.
            document_id: Which document to serve due items for.
        """
        self._service = service
        self._document_id = document_id
        super().__init__(*args, **kw)  # type: ignore[arg-type]

    def _respond(self, body: str, content_type: str) -> None:
        """Write one response with no-cache headers.

        Args:
            body: The response body.
            content_type: Its MIME type.
        """
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        """Route the three paths the host stub needs."""
        route = self.path.split("?", 1)[0]
        if route in ("/", "/host.html", "/widget_host.html"):
            self._respond(
                (TOOLS_DIR / "widget_host.html").read_text(encoding="utf-8"),
                "text/html; charset=utf-8",
            )
        elif route == "/study.html":
            # Read live, so a reload always tests the current source.
            self._respond(load_widget_html(), "text/html; charset=utf-8")
        elif route == "/due.json":
            try:
                payload = self._service.get_due_items(self._document_id)
            except Exception as exc:  # surfaced in the page, not the console
                payload = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "due": [],
                    "due_count": 0,
                }
            self._respond(json.dumps(payload), "application/json")
        else:
            self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the default per-request logging."""


def main() -> None:
    """Run the harness server until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8901)
    parser.add_argument("--document", type=int, default=1, help="document id to study")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".learning-tool",
        help="data directory to read due items from",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = parser.parse_args()

    handler = partial(
        HarnessHandler,
        service=StudyService(args.data_dir),
        document_id=args.document,
    )
    url = f"http://localhost:{args.port}/host.html"
    server = HTTPServer(("127.0.0.1", args.port), handler)  # type: ignore[arg-type]
    print(f"serving {args.data_dir} document {args.document} at {url}")
    print("the widget and payload are read live; reload the page after editing")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
