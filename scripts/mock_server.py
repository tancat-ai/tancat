"""Robust HTTP server for the LV Insurance mock site.

Replaces ``python -m http.server 8781`` with a ``ThreadingHTTPServer``
that handles concurrent Playwright requests and gracefully ignores
client disconnects (``BrokenPipeError``, ``ConnectionResetError``).

Usage:
    # Standalone
    python scripts/mock_server.py [--port 8781] [--directory .]

    # From Python (eval runner auto-start)
    from scripts.mock_server import MockServer
    with MockServer.start() as server:
        # generate tests against http://localhost:8781/...
    # server auto-stops
"""

from __future__ import annotations

import http.server
import logging
import os
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _RobustRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Request handler that silences client-disconnect noise."""

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Client disconnected — normal behaviour for Playwright browsers
            pass

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Reduce log noise from successful requests (HTTP 200-399)."""
        # args[1] is the status code for format '"%s" %s %s'
        try:
            status = int(args[1]) if len(args) > 1 else None
        except (ValueError, IndexError):
            status = None
        if status is not None and status < 400:
            return  # silence successful requests
        super().log_message(format, *args)


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threading HTTP server that handles concurrent requests."""

    allow_reuse_address = True
    daemon_threads = True  # threads exit when server stops

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Suppress EPIPE noise from disconnected clients."""
        exc_type, _, _ = sys.exc_info()
        if exc_type in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


class MockServer:
    """Context-managed mock HTTP server for eval and UAT runs.

    Example:
        with MockServer.start(port=8781) as server:
            # Server is running — test against http://localhost:8781/
            ...
        # Server auto-stops
    """

    def __init__(self, port: int = 8781, directory: str | Path = ".") -> None:
        self.port = port
        self.directory = str(Path(directory).resolve())
        self._thread: threading.Thread | None = None
        self._httpd: _ThreadingServer | None = None

    @classmethod
    def start(cls, port: int = 8781, directory: str | Path = ".") -> MockServer:
        """Start the server and return a context-managed instance.

        The server runs in a daemon thread — it stops automatically when
        the owning process exits or the context manager is exited.
        """
        server = cls(port=port, directory=directory)
        server._start()
        return server

    def _start(self) -> None:
        """Start the server in a background daemon thread."""
        if self._httpd is not None:
            return  # already running

        os.chdir(self.directory)
        self._httpd = _ThreadingServer(("0.0.0.0", self.port), _RobustRequestHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Mock server started on http://localhost:%d (dir=%s)", self.port, self.directory)

    def stop(self) -> None:
        """Shut down the server."""
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None
        logger.info("Mock server stopped")

    @property
    def url(self) -> str:
        """Return the base URL for the mock site."""
        return f"http://localhost:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def __enter__(self) -> MockServer:
        self._start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start a robust mock HTTP server")
    parser.add_argument("--port", type=int, default=8781, help="Port to listen on (default: 8781)")
    parser.add_argument("--directory", type=str, default=".", help="Root directory to serve (default: .)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    server = MockServer.start(port=args.port, directory=args.directory)
    logger.info("Serving %s on http://localhost:%d", args.directory, args.port)
    logger.info("Press Ctrl+C to stop")

    try:
        # Keep the main thread alive
        while True:
            server._thread.join(timeout=1)  # type: ignore[union-attr]
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.stop()
