"""GitLab platform adapter tests (Phase 7c) — hermetic against a local mock
API server so MR-note posting behaviour is verified without a real MR or
token. Mirrors tests/test_ci_github_adapter.py; the GitLab REST shapes that
differ are asserted explicitly (notes endpoint, PRIVATE-TOKEN, PUT edits,
URL-encoded project paths)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ci.platform.gitlab import GitLabClient, GitLabError, client_from_env


class MockGitLabAPI:
    """In-memory MR-note store behind a real HTTP server."""

    def __init__(self) -> None:
        self.notes: list[dict[str, object]] = []
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
                        "private-token": self.headers.get("PRIVATE-TOKEN", ""),
                    }
                )

            def _send(self, payload: list | dict, code: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _note_id(self) -> int | None:
                m = re_search_notes_id(self.path)
                return int(m) if m is not None else None

            def do_GET(self) -> None:  # noqa: N802
                self._record()
                if "/merge_requests/42/notes" in self.path and "?per_page=" in self.path:
                    self._send(store.notes)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                if "/merge_requests/42/notes" in self.path:
                    payload = json.loads(body or b"{}")
                    note = {"id": len(store.notes) + 1, "body": payload.get("body", "")}
                    store.notes.append(note)
                    self._send(note, 201)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_PUT(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                nid = self._note_id()
                found = next((n for n in store.notes if n["id"] == nid), None) if nid else None
                if found is None:
                    self._send({"message": "Not Found"}, 404)
                    return
                payload = json.loads(body or b"{}")
                found["body"] = payload.get("body", "")
                self._send(found)

        return Handler

    def __enter__(self) -> MockGitLabAPI:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


def re_search_notes_id(path: str) -> str | None:
    """Pull the trailing note id from ``.../merge_requests/42/notes/7``."""
    import re

    m = re.search(r"/merge_requests/\d+/notes/(\d+)$", path)
    return m.group(1) if m else None


def _client(api: MockGitLabAPI, token: str = "t0ken", project: str = "org/project") -> GitLabClient:
    return GitLabClient(
        token=token,
        base_url=f"http://127.0.0.1:{api.port}",
        project=project,
        mr_iid=42,
    )


MARKER = "## 🤖 AI Test Generator"


def test_create_then_idempotent_update_single_note() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        body1 = f"{MARKER}\n\nrun 1"
        body2 = f"{MARKER}\n\nrun 2"
        client.post_note(body1, marker=MARKER)
        client.post_note(body2, marker=MARKER)
        # One note, edited — never duplicated.
        assert len(api.notes) == 1
        assert api.notes[0]["body"] == body2


def test_edit_uses_put_not_patch() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        client.post_note(f"{MARKER}\nrun 1", marker=MARKER)
        client.post_note(f"{MARKER}\nrun 2", marker=MARKER)
        methods = [r["method"] for r in api.requests]
        assert "PUT" in methods
        assert "PATCH" not in methods


def test_find_note_by_marker() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        client.create_note(f"{MARKER}\nresults")
        client.create_note("unrelated")
        found = client.find_note_by_marker(MARKER)
        assert found is not None and "results" in found["body"]
        assert client.find_note_by_marker("## 🤖 Nope") is None


def test_extract_url_from_comment() -> None:
    body = f"{MARKER}\n\n**Mode:** generate-and-run · **Site:** https://staging.example.com · **Model:** gpt-4o"
    assert GitLabClient.extract_url_from_comment(body) == "https://staging.example.com"
    assert GitLabClient.extract_url_from_comment("no url here") is None


def test_no_token_raises() -> None:
    with MockGitLabAPI() as api:
        client = _client(api, token="")
        with pytest.raises(GitLabError, match="GITLAB_TOKEN"):
            client.create_note("hi")


def test_private_token_header_sent() -> None:
    with MockGitLabAPI() as api:
        client = _client(api, token="sekret")
        client.create_note("hi")
        assert api.requests[0]["private-token"] == "sekret"


def test_http_error_surfaces() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        with pytest.raises(GitLabError, match="404"):
            client.edit_note(999, "body")


def test_project_path_url_encoded_in_notes_path() -> None:
    with MockGitLabAPI() as api:
        client = _client(api, project="group/my/project")
        client.create_note("hi")
        path = str(api.requests[0]["path"])
        assert "/projects/group%2Fmy%2Fproject/merge_requests/42/notes" in path


def test_numeric_project_id_not_encoded() -> None:
    with MockGitLabAPI() as api:
        client = _client(api, project="12345")
        client.create_note("hi")
        path = str(api.requests[0]["path"])
        assert "/projects/12345/merge_requests/42/notes" in path


def test_client_from_env_mapping() -> None:
    env = {
        "GITLAB_TOKEN": "pat",
        "CI_API_V4_URL": "https://gitlab.example.com/api/v4",
        "CI_PROJECT_PATH": "group/proj",
        "CI_MERGE_REQUEST_IID": "7",
    }
    client = client_from_env(env)
    assert client.token == "pat"
    assert client.base_url == "https://gitlab.example.com/api/v4"
    assert client.project == "group/proj"
    assert client.mr_iid == 7


def test_client_from_env_defaults() -> None:
    client = client_from_env({})
    assert client.base_url == "https://gitlab.com/api/v4"
    assert client.project == ""
    assert client.mr_iid == 0


def test_latest_slash_command_most_recent() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        client.create_note("unrelated note")
        client.create_note("/ignore test_05_verify_cart_product_details")
        client.create_note("more discussion")
        client.create_note("/adapt test_04_go_to_cart_page")
        assert client.latest_slash_command_body() == "/adapt test_04_go_to_cart_page"


def test_latest_slash_command_none() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        client.create_note("no commands here")
        assert client.latest_slash_command_body() is None


def test_latest_slash_command_within_body() -> None:
    with MockGitLabAPI() as api:
        client = _client(api)
        client.create_note(f"{MARKER}\n\nresults table\n\n/ignore test_03_review_cart_contents")
        assert client.latest_slash_command_body() is not None
        assert "test_03_review_cart_contents" in str(client.latest_slash_command_body())
