"""Robust HTTP server for mock sites.

Replaces ``python -m http.server 8781`` with a ``ThreadingHTTPServer``
that handles concurrent Playwright requests and gracefully ignores
client disconnects (``BrokenPipeError``, ``ConnectionResetError``).

Optional per-mock route aliases: if the served directory contains a
``mock_routes.json`` mapping URL paths to files, requests for those paths
are served from the mapped file. This lets mocks speak the pipeline's
keyword-route vocabulary (``/view_cart``, ``/products``, ``/checkout``)
so journey discovery and cart-seeding can reach cart/checkout pages.

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
import json
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
        except BrokenPipeError, ConnectionResetError, ConnectionAbortedError:
            # Client disconnected — normal behaviour for Playwright browsers
            pass

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except BrokenPipeError, ConnectionResetError, ConnectionAbortedError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Reduce log noise from successful requests (HTTP 200-399)."""
        # args[1] is the status code for format '"%s" %s %s'
        try:
            status = int(args[1]) if len(args) > 1 else None
        except ValueError, IndexError:
            status = None
        if status is not None and status < 400:
            return  # silence successful requests
        super().log_message(format, *args)


class _RouteAwareHandler(_RobustRequestHandler):
    """Serves mock_routes.json aliases before the default static translation.

    ``ROUTES`` maps a URL path (no query string) to a file relative to the
    served directory. Populated per server from the mock's ``mock_routes.json``.
    """

    ROUTES: dict[str, str] = {}

    def do_GET(self) -> None:
        """Serve the request; alias paths 302-redirect to the canonical file.

        A redirect (not in-place serving) keeps page URLs canonical
        (``/checkout`` → ``checkout.html``), so ``to_have_url`` assertions and
        golden keys reference the real files the scraper records.
        """
        path_only = self.path.split("?", 1)[0]
        mapped = type(self).ROUTES.get(path_only)
        if mapped and path_only != mapped:
            self.send_response(302)
            target = mapped
            if "?" in self.path:
                target += "?" + self.path.split("?", 1)[1]
            self.send_header("Location", target)
            self.end_headers()
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        path_only = path.split("?", 1)[0]
        mapped = type(self).ROUTES.get(path_only)
        if mapped:
            return super().translate_path(mapped)
        return super().translate_path(path)


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
        # Per-mock route aliases (mock_routes.json in the served directory)
        # so the pipeline's keyword-route vocabulary resolves to real files.
        routes = self._load_routes()
        if routes:
            _RouteAwareHandler.ROUTES = routes
            handler_class: type[http.server.SimpleHTTPRequestHandler] = _RouteAwareHandler
        else:
            handler_class = _RobustRequestHandler
        self._httpd = _ThreadingServer(("0.0.0.0", self.port), handler_class)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Mock server started on http://localhost:%d (dir=%s)", self.port, self.directory)

    def _load_routes(self) -> dict[str, str]:
        """Load the optional ``mock_routes.json`` alias map from the served dir."""
        routes_file = Path(self.directory) / "mock_routes.json"
        if not routes_file.exists():
            return {}
        try:
            data = json.loads(routes_file.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

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
