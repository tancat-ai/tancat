#!/usr/bin/env python3
"""Fake OpenAI-compatible LLM server for hermetic pipeline testing (Phase 7).

Serves ``POST /v1/chat/completions`` with canned responses so the FULL
generation pipeline (spec analysis -> skeleton -> resolution) runs offline
with zero external services — no LM Studio, no API key, no internet. Same
philosophy as the mock-site family: deterministic localhost, never decays.

Routing (by request content, so the fake knows *which* pipeline call it is):
  - SpecAnalyzer system prompt ("QA Test Analyst")      -> conditions JSON
  - skeleton prompt ("Playwright Python test engineer") -> canned skeleton,
    target URL substituted from the prompt's known-URLs block
  - anything else (semantic resolution, etc.)           -> safe fallback
    (``{"assertion_type": "toBeVisible"}`` — the ranker's safe default)

Usage::

    from scripts.fake_llm import FakeLLMServer
    with FakeLLMServer() as server:          # binds an OS-assigned free port
        ...  # pipeline with provider=openai-local, base_url=server.url
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_TARGET_URL_RE = re.compile(r"https?://[^\s\"'\\]+")

# Canned conditions for the ecommerce-mock story (mirrors eval-006).
ECOMMERCE_CONDITIONS: list[dict[str, str]] = [
    {
        "id": "TC-01",
        "text": "Navigate to the store home page",
        "expected": "The store home page loads",
        "type": "happy_path",
    },
    {
        "id": "TC-02",
        "text": "On the home page, click the Add to cart button next to a product (e.g. Blue Top)",
        "expected": "The product is added to the cart",
        "type": "happy_path",
    },
    {
        "id": "TC-03",
        "text": "Verify a confirmation message appears indicating the product was added to cart",
        "expected": "An add-to-cart confirmation is visible",
        "type": "happy_path",
    },
    {
        "id": "TC-04",
        "text": "Click the Cart link in the header navigation to go to the cart page",
        "expected": "The cart page loads",
        "type": "happy_path",
    },
    {
        "id": "TC-05",
        "text": "Verify the cart page displays the added product with its name and price",
        "expected": "The product name and price are visible on the cart page",
        "type": "happy_path",
    },
    {
        "id": "TC-06",
        "text": "Click the Proceed To Checkout button",
        "expected": "The checkout page loads",
        "type": "happy_path",
    },
    {
        "id": "TC-07",
        "text": "Fill in the checkout form (name, email, address, city, zip, card details) and place the order",
        "expected": "The order is placed",
        "type": "happy_path",
    },
    {
        "id": "TC-08",
        "text": "Verify the order success message appears",
        "expected": "An order success message is visible",
        "type": "happy_path",
    },
]

# Generic fallback conditions for unknown stories (3 criteria).
GENERIC_CONDITIONS: list[dict[str, str]] = [
    {"id": "TC-01", "text": "Navigate to the home page", "expected": "The home page loads", "type": "happy_path"},
    {"id": "TC-02", "text": "Perform a key interaction", "expected": "The interaction completes", "type": "happy_path"},
    {"id": "TC-03", "text": "Verify the result", "expected": "The result is visible", "type": "happy_path"},
]

# Canned skeleton for the ecommerce-mock story (mirrors the eval-006 capture
# in placeholder form). ``{TARGET_URL}`` is substituted from the request.
ECOMMERCE_SKELETON = """import pytest
from playwright.sync_api import Page, expect


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_store_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{ASSERT:home page loaded}}


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_product_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_added_confirmation(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{ASSERT:add to cart confirmation}}


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_go_to_cart_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{CLICK:Cart link}}
    {{ASSERT:cart page loaded}}


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_cart_product_details(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{CLICK:Cart link}}
    {{ASSERT:product name and price}}


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_to_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{CLICK:Cart link}}
    {{CLICK:Proceed To Checkout}}
    {{ASSERT:checkout page loaded}}


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_fill_checkout_and_place_order(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{CLICK:Cart link}}
    {{CLICK:Proceed To Checkout}}
    {{FILL:Name:John Doe}}
    {{FILL:Email:john@example.com}}
    {{FILL:Address:123 Main St}}
    {{FILL:City:New York}}
    {{FILL:Zip:10001}}
    {{FILL:Card Number:4111111111111111}}
    {{FILL:Expiry:12/25}}
    {{FILL:CVV:123}}
    {{CLICK:Place Order}}


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_order_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:Add to cart}}
    {{CLICK:Cart link}}
    {{CLICK:Proceed To Checkout}}
    {{FILL:Name:John Doe}}
    {{FILL:Email:john@example.com}}
    {{FILL:Address:123 Main St}}
    {{FILL:City:New York}}
    {{FILL:Zip:10001}}
    {{FILL:Card Number:4111111111111111}}
    {{FILL:Expiry:12/25}}
    {{FILL:CVV:123}}
    {{CLICK:Place Order}}
    {{ASSERT:order success message}}
"""

GENERIC_SKELETON = """import pytest
from playwright.sync_api import Page, expect


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_home_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{ASSERT:home page loaded}}


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_key_interaction(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{CLICK:first interactive element}}


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_result(page: Page, evidence_tracker):
    evidence_tracker.navigate('{TARGET_URL}')
    {{ASSERT:result visible}}
"""


def _find_target_url(body_text: str, default: str = "http://localhost:8781/index.html") -> str:
    """Extract the first http(s) URL from the request body (the prompt's
    known-URLs block), falling back to *default*."""
    match = _TARGET_URL_RE.search(body_text)
    return match.group(0) if match else default


_FRAGMENT_MARKER = "Generate EXACTLY ONE pytest test function"
_FULL_SKELETON_MARKER = "test functions. One per criterion"
_CONDITION_REF_RE = re.compile(r"ID:\s*(TC-\d+)")


def _split_skeleton_fragments(skeleton: str) -> dict[str, str]:
    """Split a canned skeleton into per-condition test blocks keyed by ref.

    Returns ``{"TC-01": "@pytest.mark.evidence(...)\ndef test_01..."}`` —
    the production path requests ONE test function per condition
    (``_generate_combined_skeleton_for_conditions``), so the fake must serve
    one fragment per request, not the whole module.
    """
    parts = skeleton.split("@pytest.mark.evidence")
    fragments: dict[str, str] = {}
    for part in parts[1:]:
        block = "@pytest.mark.evidence" + part
        ref_match = re.search(r'condition_ref="(TC-\d+)"', block)
        if ref_match:
            fragments[ref_match.group(1)] = block
    return fragments


_ECOMMERCE_FRAGMENTS: dict[str, str] = _split_skeleton_fragments(ECOMMERCE_SKELETON)
_GENERIC_FRAGMENTS: dict[str, str] = _split_skeleton_fragments(GENERIC_SKELETON)


class FakeLLMHandler(BaseHTTPRequestHandler):
    """Serve OpenAI-compatible completions from canned responses.

    Path-agnostic: accepts both ``/v1/chat/completions`` (OpenAI cloud
    convention) and ``/chat/completions`` (LM Studio / openai-local
    convention) so the fake works with any provider URL layout.
    """

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path in ("/v1/models", "/models"):
            self._send_json({"object": "list", "data": [{"id": "fake-model", "object": "model"}]})
            return
        self._send_json({"error": {"message": f"not found: {self.path}"}}, status=404)

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json({"error": {"message": f"not found: {self.path}"}}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body_text = self.rfile.read(length).decode("utf-8", errors="replace")
        content = self._select_response(body_text)
        self._send_json(
            {
                "id": "fake-llm-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "fake-model",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
            }
        )

    def _select_response(self, body_text: str) -> str:
        """Pick the canned response for the pipeline call being made."""
        is_ecommerce = "ecommerce" in body_text or "add them to my cart" in body_text or "cart" in body_text.lower()
        if "QA Test Analyst" in body_text:
            return json.dumps(ECOMMERCE_CONDITIONS if is_ecommerce else GENERIC_CONDITIONS)
        target = _find_target_url(body_text)
        if _FRAGMENT_MARKER in body_text:
            # Per-condition fragment: serve exactly ONE test for the target ref.
            ref_match = _CONDITION_REF_RE.search(body_text)
            fragments = _ECOMMERCE_FRAGMENTS if is_ecommerce else _GENERIC_FRAGMENTS
            ref = ref_match.group(1) if ref_match else None
            block = fragments.get(ref) if ref else None
            if block is None:
                block = next(iter(fragments.values()))
            return block.replace("{TARGET_URL}", target)
        if _FULL_SKELETON_MARKER in body_text:
            skeleton = ECOMMERCE_SKELETON if is_ecommerce else GENERIC_SKELETON
            return skeleton.replace("{TARGET_URL}", target)
        # Semantic resolution / anything else — the ranker's safe default.
        return json.dumps({"assertion_type": "toBeVisible"})

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # keep test output quiet


class FakeLLMServer:
    """Threading HTTP server that fakes an OpenAI-compatible LLM endpoint."""

    def __init__(self, port: int = 0) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), FakeLLMHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        # We always bind "127.0.0.1" explicitly — no need to unpack server_address.
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __enter__(self) -> FakeLLMServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


if __name__ == "__main__":
    server = FakeLLMServer(port=9977)
    server.start()
    print(f"Fake LLM serving OpenAI-compatible completions at {server.url}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.stop()
