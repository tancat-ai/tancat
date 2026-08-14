"""GitHub platform adapter tests (Phase 7b) — hermetic against a local mock
API server so posting behaviour is verified without a real PR or token."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ci.platform.github import GitHubClient, GitHubError


class MockGitHubAPI:
    """In-memory issue-comment store behind a real HTTP server."""

    def __init__(self) -> None:
        self.comments: list[dict[str, object]] = []
        self.requests: list[dict[str, object]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_factory())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _handler_factory(self) -> type[BaseHTTPRequestHandler]:
        store = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silence
                pass

            def _record(self, body: bytes | None = None) -> None:
                store.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "body": json.loads(body.decode("utf-8")) if body else None,
                        "authorization": self.headers.get("Authorization", ""),
                    }
                )

            def _send(self, payload: list | dict, code: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                self._record()
                if "/issues/42/comments" in self.path:
                    self._send(store.comments)
                elif "/issues/comments/" in self.path:
                    cid = int(self.path.rsplit("/", 1)[-1])
                    found = next((c for c in store.comments if c["id"] == cid), None)
                    if found is None:
                        self._send({"message": "Not Found"}, 404)
                    else:
                        self._send(found)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                if "/issues/42/comments" in self.path:
                    payload = json.loads(body or b"{}")
                    comment = {"id": len(store.comments) + 1, "body": payload.get("body", "")}
                    store.comments.append(comment)
                    self._send(comment, 201)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_PATCH(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                cid = int(self.path.rsplit("/", 1)[-1])
                found = next((c for c in store.comments if c["id"] == cid), None)
                if found is None:
                    self._send({"message": "Not Found"}, 404)
                    return
                payload = json.loads(body or b"{}")
                found["body"] = payload.get("body", "")
                self._send(found)

        return Handler

    def __enter__(self) -> MockGitHubAPI:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


def _client(api: MockGitHubAPI, token: str = "t0ken") -> GitHubClient:
    return GitHubClient(
        token=token,
        base_url=f"http://127.0.0.1:{api.port}",
        repo="org/repo",
        pr_number=42,
    )


MARKER = "## 🤖 AI Test Generator"


def test_create_then_idempotent_update_single_comment() -> None:
    with MockGitHubAPI() as api:
        client = _client(api)
        body1 = f"{MARKER}\n\nrun 1"
        body2 = f"{MARKER}\n\nrun 2"
        client.post_comment(body1, marker=MARKER)
        client.post_comment(body2, marker=MARKER)
        # One comment, edited — never duplicated.
        assert len(api.comments) == 1
        assert api.comments[0]["body"] == body2


def test_find_comment_by_marker() -> None:
    with MockGitHubAPI() as api:
        client = _client(api)
        client.create_comment(f"{MARKER}\nresults")
        client.create_comment("unrelated")
        found = client.find_comment_by_marker(MARKER)
        assert found is not None and "results" in found["body"]
        assert client.find_comment_by_marker("## 🤖 Nope") is None


def test_extract_url_from_comment() -> None:
    body = f"{MARKER}\n\n**Mode:** generate-and-run · **Site:** https://staging.example.com · **Model:** gpt-4o"
    assert GitHubClient.extract_url_from_comment(body) == "https://staging.example.com"
    assert GitHubClient.extract_url_from_comment("no url here") is None


def test_no_token_raises() -> None:
    with MockGitHubAPI() as api:
        client = _client(api, token="")
        with pytest.raises(GitHubError, match="GITHUB_TOKEN"):
            client.create_comment("hi")


def test_auth_header_sent() -> None:
    with MockGitHubAPI() as api:
        client = _client(api, token="sekret")
        client.create_comment("hi")
        assert api.requests[0]["authorization"] == "Bearer sekret"


def test_http_error_surfaces() -> None:
    with MockGitHubAPI() as api:
        client = _client(api)
        with pytest.raises(GitHubError, match="404"):
            client.edit_comment(999, "body")
