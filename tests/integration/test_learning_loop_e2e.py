"""Learning-loop E2E test — AI-042 (BACKLOG 🆕, 2026-08-12).

Proves the product's learning loop end-to-end with REAL components, not
mocks-of-mocks:

    generated test package → REAL ``generated_tests/conftest.py`` teardown
    → FlowMemoryStore (real ``evidence/flow_memory.json``) → real
    ``PipelineRunService`` post-run suite chaining → orchestrator GOTO
    resolution from the learned flows.

The 2026-08 test-pack audit's core lesson: green units don't equal a
working product — the expensive bugs (B-029..B-035) lived at integration
seams, and conftest → store → resolver is exactly such a seam. Today the
loop is covered piecewise with mocks; this is the single test that runs the
REAL conftest against a REAL local mock site and asserts the whole chain.

How it works:

1. **Mock site is brought up as part of the automation** — a module-scoped
   ``MockServer`` on port 8784 serves ``mock_sites/ecommerce`` (the same
   deterministic localhost mock the eval harness uses, and the file's own
   port: contract layer binds 8781, adversarial 8782, heatmap 8783 — CI
   xdist workers must never share a port).
2. A tiny 4-test generated package is written to
   ``generated_tests/learning_loop_e2e/``. It runs under the REAL
   ``generated_tests/conftest.py`` (parent-directory discovery), so its
   teardown learning hooks execute for real. Each test mirrors the shipped
   eval capture format (``evidence_tracker.navigate/click/fill`` + Playwright
   ``expect``), and the package is shaped to emit a known set of flows:
   - within-test: home→products, cart→checkout, products→cart,
     checkout→checkout_success (passed click steps that changed page)
   - suite chains (AI-042-F3): products→cart, checkout→products,
     cart→checkout (terminal of test N → entry of test N+1)
3. ``PipelineRunService.run_saved_test(persist=True)`` executes the package
   against the live mock. The conftest learns within-test flows per test;
   the post-run hook chains suite flows. A second run must dedup (no new
   patterns) and bump hit counts.
4. A follow-up resolution drives the orchestrator's GOTO/URL step 2.5
   (``flow_resolved_url``) with the learned store and asserts it resolves
   "view cart" from the products page to the cart URL — proving the loop
   closes: learned flows feed future generation.

Hermeticity:

- The real ``evidence/flow_memory.json`` is snapshotted before the module
  runs and restored after (the store must be real for this test to mean
  anything; it is wiped so the assertions are deterministic — no
  pre-existing patterns to merge with). The run service's suite-chain hook
  sweeps the package's OWN ``evidence/`` dir for a directory target (the
  2026-08-16 ``Path(saved_path).parent`` fix), so nothing stale is chained —
  no legacy-dir parking is needed.
- Do not run the product app (Streamlit/CLI) concurrently with this module —
  it snapshots the real flow-memory store for the ~2 minutes it runs
  (restored at teardown).
- The package ships a local ``conftest.py`` that neutralises ONLY the real
  conftest's RAG-learning leg (``src.rag_learn.learn_from_evidence`` — a
  sibling loop, B-036 Phase 3) so the run never writes the machine-local
  ``evidence/rag_store.db`` or triggers the ~80 MB embedder download on a
  fresh CI box. The flow-memory leg under test is untouched: the real
  conftest's ``FlowMemoryStore().learn_from_evidence(...)`` still runs for
  real (the real conftest imports the symbol lazily inside its teardown, so
  the patch is picked up).
- Marked ``slow`` + ``integration`` + ``subprocess`` — excluded from the
  default suite (pytest.ini addopts) exactly like the other live-mock tests.

Run explicitly:
    pytest tests/integration/test_learning_loop_e2e.py -v
"""

from __future__ import annotations

import asyncio
import json
import shutil
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_DIR = ROOT / "mock_sites" / "ecommerce"
PACKAGE_DIR = ROOT / "generated_tests" / "learning_loop_e2e"
STORE_FILE = ROOT / "evidence" / "flow_memory.json"

#: File-unique port — see docstring for the per-file convention.
PORT = 8784
BASE_URL = f"http://localhost:{PORT}"
#: The exact flows this package is designed to produce.
#: (from_route, action, description.lower(), to_route)
EXPECTED_WITHIN_TEST: set[tuple[str, str, str, str]] = {
    ("home", "CLICK", "products link", "products"),
    ("cart", "CLICK", "proceed to checkout", "checkout"),
    ("products", "CLICK", "view cart link", "cart"),
    ("checkout", "CLICK", "place order", "checkout_success"),
}
EXPECTED_SUITE_CHAINS: set[tuple[str, str, str, str]] = {
    ("products", "GOTO", "cart", "cart"),
    ("checkout", "GOTO", "products", "products"),
    ("cart", "GOTO", "checkout", "checkout"),
}


# ---------------------------------------------------------------------------
# The tiny generated package
# ---------------------------------------------------------------------------

#: Package-local conftest — neutralises the RAG learning leg only (see
#: module docstring). The REAL generated_tests/conftest.py still runs for
#: everything else, including the flow-memory learning under test.
PACKAGE_CONFTEST = '''\
"""Test-harness conftest for the learning-loop E2E package.

Neutralises ONLY the real conftest's RAG-learning leg
(src.rag_learn.learn_from_evidence): a sibling loop (B-036 Phase 3) that
would embed and write the machine-local evidence/rag_store.db (and trigger
an ~80 MB embedder download on a fresh CI box). The flow-memory learning
leg under test is untouched — the real conftest's
FlowMemoryStore().learn_from_evidence(tracker.steps) still runs for real
for every passing test. Patched at import time; the real conftest imports
the symbol lazily inside its teardown hook, so the patch is picked up.
"""

from typing import Any


def _noop_learn_from_evidence(steps: list[dict[str, Any]], *, store: Any = None) -> dict[str, int]:
    return {"inserted": 0, "exists": 0}


import src.rag_learn as _rag_learn  # noqa: E402

_rag_learn.learn_from_evidence = _noop_learn_from_evidence
'''

#: One test per flow segment — mirrors the shipped eval capture format.
#: Canonical .html paths only (no aliases → no 302 redirects → clean URLs).
TINY_TESTS: dict[str, str] = {
    "test_01_browse_products.py": f'''\
import pytest
from playwright.sync_api import Page, expect

BASE = "{BASE_URL}"


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_browse_products(page: Page, evidence_tracker):
    evidence_tracker.navigate(BASE + "/index.html")
    evidence_tracker.click('a[href="/products.html"]', label="Products link")
    expect(page).to_have_url(BASE + "/products.html")
''',
    "test_02_view_cart.py": f'''\
import pytest
from playwright.sync_api import Page, expect

BASE = "{BASE_URL}"


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_view_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate(BASE + "/cart.html")
    evidence_tracker.click('a[href="/checkout.html"]', label="Proceed to Checkout")
    expect(page).to_have_url(BASE + "/checkout.html")
''',
    "test_03_add_to_cart.py": f'''\
import pytest
from playwright.sync_api import Page, expect

BASE = "{BASE_URL}"


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate(BASE + "/products.html")
    evidence_tracker.click('.add-to-cart[data-product-id="1"]', label="Add to cart")
    evidence_tracker.click('a[href="/cart.html"]', label="View cart link")
    expect(page).to_have_url(BASE + "/cart.html")
''',
    "test_04_checkout.py": f'''\
import pytest
from playwright.sync_api import Page, expect

BASE = "{BASE_URL}"


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate(BASE + "/checkout.html")
    evidence_tracker.fill("#name", "John Doe", label="Name")
    evidence_tracker.fill("#email", "john@example.com", label="Email")
    evidence_tracker.fill("#address", "123 Main St", label="Address")
    evidence_tracker.fill("#city", "New York", label="City")
    evidence_tracker.fill("#zip", "10001", label="Zip Code")
    evidence_tracker.fill("#card-name", "Jane Doe", label="Cardholder Name")
    evidence_tracker.fill("#card-number", "4111111111111111", label="Card Number")
    evidence_tracker.fill("#expiry", "12/25", label="Expiry")
    evidence_tracker.fill("#cvv", "123", label="CVV")
    evidence_tracker.click("#place-order", label="Place Order")
    expect(page).to_have_url(BASE + "/checkout_success.html")
''',
}


# ---------------------------------------------------------------------------
# Module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def mock_site() -> Iterator[None]:
    """Bring the mock site up as part of the automation.

    Deterministic localhost e-commerce mock — the same site the eval harness
    (eval-006) and heatmap-alignment tests use. A urllib probe fails fast
    with a clear message if the port is unavailable.
    """
    from scripts.mock_server import MockServer

    with MockServer.start(port=PORT, directory=str(MOCK_DIR)):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/index.html", timeout=5) as resp:
                assert resp.status == 200, f"mock server not serving {BASE_URL}: {resp.status}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            raise AssertionError(f"Mock site did not come up on {BASE_URL} (port {PORT} in use?): {exc}") from exc
        yield


@pytest.fixture(scope="module", autouse=True)
def isolated_flow_store() -> Iterator[None]:
    """Snapshot the real evidence/flow_memory.json; wipe; restore at the end.

    The store MUST be real for this test to mean anything, and wiped so the
    assertions are deterministic (no pre-existing patterns to merge with).
    No other test in the suite writes the real store (unit tests are gated
    via FLOW_MEMORY_ENABLED=0 / explicit tmp paths), so restore is safe.
    """
    snapshot = STORE_FILE.read_bytes() if STORE_FILE.exists() else None
    if snapshot is not None:
        STORE_FILE.unlink()
    yield
    try:
        if snapshot is None:
            STORE_FILE.unlink(missing_ok=True)
        else:
            STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STORE_FILE.write_bytes(snapshot)
    except OSError:  # pragma: no cover - restore is best-effort
        pass


@pytest.fixture(scope="module", autouse=True)
def tiny_package(mock_site: None, isolated_flow_store: None) -> Iterator[Path]:
    """Write the tiny generated package under generated_tests/ so the REAL
    generated_tests/conftest.py applies via parent-directory discovery."""
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    (PACKAGE_DIR / "conftest.py").write_text(PACKAGE_CONFTEST, encoding="utf-8")
    for filename, code in TINY_TESTS.items():
        (PACKAGE_DIR / filename).write_text(code, encoding="utf-8")
    yield PACKAGE_DIR
    shutil.rmtree(PACKAGE_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_package() -> Any:
    """Run the whole tiny package through the REAL PipelineRunService.

    ``saved_path`` is the package directory, so one pytest invocation
    executes all four tests (the standard ``pytest <package>`` shape). The
    service's built-in suite-chain hook sweeps the package's OWN
    ``<PACKAGE_DIR>/evidence`` dir for a directory target (the 2026-08-16
    ``Path(saved_path).parent`` fix — before it landed here and chained stale
    sidecars, so the test had to park ``generated_tests/evidence/`` and chain
    manually). The hook now chains the right dir, so no manual
    ``learn_suite_flows`` call is needed (calling it too would double the
    hit counts — the very bug the assertion catches).
    Within-test learning happens inside each subprocess via the REAL conftest
    teardown.
    """
    from src.pipeline_run_service import PipelineRunService

    return PipelineRunService().run_saved_test(str(PACKAGE_DIR), persist=True)


def _store_snapshot() -> dict[tuple[str, str, str, str], Any]:
    """Parse the real flow_memory.json into {key: pattern} dicts."""
    from src.flow_memory import FlowMemoryStore

    store = FlowMemoryStore()
    return {p.key: p for p in store._patterns.values()}  # noqa: SLF001


def _sidecar_statuses() -> list[str]:
    """Test statuses from the package's evidence sidecars."""
    statuses: list[str] = []
    for sidecar in sorted((PACKAGE_DIR / "evidence").glob("*.evidence.json")):
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        statuses.append(str((data.get("test") or {}).get("status", "missing")))
    return statuses


# ---------------------------------------------------------------------------
# The loop, end to end
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.subprocess
def test_mock_site_brought_up_by_the_automation() -> None:
    """The mock site must be up as part of the automation — the loop cannot
    run at all without it. (The fixture already probes it; this asserts the
    site actually serves the journey's pages.)"""
    for path in ("/index.html", "/products.html", "/cart.html", "/checkout.html"):
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as resp:
            assert resp.status == 200, f"{path} -> {resp.status}"


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.subprocess
def test_first_run_learns_flows_from_real_conftest_and_run_service() -> None:
    """Run 1: tests pass → real conftest teardown learns within-test flows →
    post-run hook chains suite flows → evidence/flow_memory.json gains the
    patterns (dedup + site hash)."""
    result = _run_package()

    # 1. The package passed (a failing test would leave no learning — and
    #    would fail the loop before it starts).
    assert result.run_result.passed == 4, (
        f"expected 4/4 passed, got {result.run_result.passed}/{result.run_result.total}\n{result.display_output}"
    )
    assert result.run_result.failed == 0

    # 2. The REAL conftest wrote one passed sidecar per test (the raw
    #    material the learners consume).
    statuses = _sidecar_statuses()
    assert len(statuses) == 4, f"expected 4 sidecars, found {len(statuses)}"
    assert statuses == ["passed"] * 4, f"sidecar statuses: {statuses}"

    # 3. evidence/flow_memory.json gained exactly the designed patterns.
    assert STORE_FILE.exists(), "flow_memory.json was not written"
    raw = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    assert len(raw["patterns"]) == 7, (
        f"expected 7 patterns, got {len(raw['patterns'])}: "
        f"{[(p['from_route'], p['action'], p['description'], p['to_route']) for p in raw['patterns']]}"
    )

    patterns = _store_snapshot()
    assert set(patterns) == EXPECTED_WITHIN_TEST | EXPECTED_SUITE_CHAINS, (
        f"pattern mismatch:\n  have {sorted(patterns)}\n  want {sorted(EXPECTED_WITHIN_TEST | EXPECTED_SUITE_CHAINS)}"
    )

    # 4. Every pattern is site-scoped to THIS mock (one-way hash) and
    #    learned exactly once so far.
    from src.rag_learn import site_hash

    expected_site = site_hash("localhost:8784")
    for key, pattern in patterns.items():
        assert pattern.site_hashes == {expected_site}, f"{key}: {pattern.site_hashes}"
        assert pattern.hit_count == 1, f"{key}: hit_count={pattern.hit_count}"

    # 5. Source split: within-test vs suite-chain (AI-042-F3).
    stats = _flow_store_stats()
    assert stats["within_test"] == 4, stats
    assert stats["suite_chains"] == 3, stats


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.subprocess
def test_second_run_dedups_and_bumps_hits() -> None:
    """Run 2: the same package re-runs — learning must dedup (no new
    patterns) and bump hit counts, never grow the store unboundedly."""
    _run_package()

    patterns = _store_snapshot()
    assert set(patterns) == EXPECTED_WITHIN_TEST | EXPECTED_SUITE_CHAINS, f"store grew on re-run: {sorted(patterns)}"
    for key, pattern in patterns.items():
        assert pattern.hit_count == 2, f"{key}: hit_count={pattern.hit_count} (want 2 — dedup bump)"


@pytest.mark.slow
@pytest.mark.integration
def test_followup_resolution_uses_learned_flows() -> None:
    """The loop closes: a follow-up GOTO resolution (orchestrator step 2.5)
    resolves 'view cart' from the products page via the flows learned by the
    REAL conftest + run service — no hand-inserted patterns, no site-specific
    UrlResolver knowledge."""
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    store = _real_flow_store()
    products_url = f"{BASE_URL}/products.html"
    cart_url = f"{BASE_URL}/cart.html"
    skeleton = "page.goto('{{GOTO:view cart}}')\n"
    scraped_data = {
        products_url: [{"selector": "h1", "tag": "h1", "text": "All Products"}],
        cart_url: [{"selector": "h1", "tag": "h1", "text": "Shopping Cart"}],
    }
    journey = TestJourney(
        test_name="test_followup_goto",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=1,
                raw_line=skeleton.strip(),
                placeholders=[
                    PlaceholderUse(
                        action="GOTO",
                        description="view cart",
                        token="{{GOTO:view cart}}",
                        line_number=1,
                        raw_line=skeleton.strip(),
                    )
                ],
            )
        ],
    )

    orch = PlaceholderOrchestrator(starting_url=products_url, flow_store=store)
    orch.url_resolver = _NullUrlResolver()  # type: ignore[assignment]
    orch.resolver = _NullResolver()  # type: ignore[assignment]

    async def resolve() -> str:
        return await orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="products")],
            seed_urls=[products_url],
            scraped_data=scraped_data,
            scraped_errors={},
        )

    result = asyncio.run(resolve())
    assert cart_url in result, f"flow memory did not resolve 'view cart':\n{result}"
    assert "pytest.skip" not in result


# ---------------------------------------------------------------------------
# Test-local stubs (mirror tests/test_flow_memory.py)
# ---------------------------------------------------------------------------


class _NullUrlResolver:
    """Stub: no site-specific keyword→URL knowledge (forces flow fallback)."""

    def resolve(self, description: str) -> str | None:  # noqa: ARG002
        return None

    def get_seed_url(self) -> str | None:
        return None


class _NullResolver:
    """Stub: no DOM/text resolution (forces flow fallback)."""

    def resolve_url(self, *args: Any, **kwargs: Any) -> str | None:  # noqa: ARG002
        return None


def _real_flow_store() -> Any:
    """The REAL FlowMemoryStore loaded from evidence/flow_memory.json."""
    from src.flow_memory import FlowMemoryStore

    return FlowMemoryStore()


def _flow_store_stats() -> dict[str, Any]:
    """Stats of the real store (patterns / sites / cross-site / suite chains)."""
    from src.flow_memory import FlowMemoryStore

    return FlowMemoryStore().stats()
