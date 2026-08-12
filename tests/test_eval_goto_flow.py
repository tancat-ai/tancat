"""eval-008 GOTO goldens resolve via flow memory (AI-042-F1).

The resolver harness (``scripts/eval/eval_resolver.py``) now resolves URL-class
placeholders (GOTO / URL-assertion) through cross-site flow memory, using the
golden's ``expected_page`` as the from-context. These tests are hermetic: they
build their own flow store from synthetic banking-style evidence (no dependence
on the machine-local seeded store), then verify every GOTO golden in eval-008
resolves to its expected URL.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.eval_resolver import _resolve_placeholder
from src.flow_memory import FlowMemoryStore

DATASET = Path(__file__).resolve().parent.parent / "scripts" / "eval" / "dataset" / "eval-008_goto_navigation.json"
BASE = "http://localhost:8781"
DUMMY_ELEMENTS = [{"selector": "body", "tag": "div"}]


def _banking_flow_steps() -> list[dict[str, object]]:
    """Synthetic passing evidence: dashboard → transfer and dashboard → payments."""
    return [
        {
            "type": "navigate",
            "value": f"{BASE}/dashboard.html",
            "url": f"{BASE}/dashboard.html",
            "result": {"status": "passed"},
        },
        {
            "type": "click",
            "label": "Click: Transfer Money link",
            "url": f"{BASE}/transfer.html",
            "locator": "#transfer-link",
            "result": {"status": "passed"},
        },
        {
            "type": "navigate",
            "value": f"{BASE}/dashboard.html",
            "url": f"{BASE}/dashboard.html",
            "result": {"status": "passed"},
        },
        {
            "type": "click",
            "label": "Click: Pay Bills link",
            "url": f"{BASE}/payments.html",
            "locator": "#pay-bill-link",
            "result": {"status": "passed"},
        },
    ]


def _goldens() -> list[dict[str, str]]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    return [{**ph, "site": data["site"]} for crit in data["golden_resolutions"] for ph in crit["placeholders"]]


class _NullElementMatcher:
    """Element matching never resolves navigation intent — the baseline."""

    def pass0_exact_text_match(self, *args: object, **kwargs: object) -> None:  # noqa: ARG002
        return None

    def pass1_text_match(self, *args: object, **kwargs: object) -> None:  # noqa: ARG002
        return None


def _make_store(tmp_path: Path) -> FlowMemoryStore:
    store = FlowMemoryStore(tmp_path / "flow_memory.json")
    store.learn_from_evidence(_banking_flow_steps())
    return store


def test_goto_goldens_resolve_via_flow_memory(tmp_path: Path) -> None:
    """Every GOTO golden in eval-008 resolves to its expected URL."""
    store = _make_store(tmp_path)
    goto_goldens = [ph for ph in _goldens() if ph["action"] in ("GOTO", "URL")]
    assert len(goto_goldens) == 2, [ph["description"] for ph in goto_goldens]

    # pages_data: flow resolution only needs the URL keys (which are the
    # banking mock's real pages — expected_pages across the dataset)
    all_pages = {ph["expected_page"] for ph in _goldens() if ph["expected_page"]}
    pages_data = {url: list(DUMMY_ELEMENTS) for url in sorted(all_pages)}

    for ph in goto_goldens:
        resolved = _resolve_placeholder(
            action=ph["action"],
            description=ph["description"],
            pages_data=pages_data,
            expected_page=ph["expected_page"],
            element_matcher=_NullElementMatcher(),
            flow_store=store,
            expected_type=ph.get("expected_type"),
        )
        assert resolved == ph["expected_locator"], (
            f"GOTO '{ph['description']}' resolved to {resolved!r}, expected {ph['expected_locator']!r}"
        )


def test_goto_goldens_fail_without_flow_store(tmp_path: Path) -> None:
    """Baseline: without flow memory the GOTO goldens cannot resolve (no DOM
    element matches navigation intent) — the gap F1 measures."""
    goto_goldens = [ph for ph in _goldens() if ph["action"] in ("GOTO", "URL")]
    pages_data = {ph["expected_page"]: list(DUMMY_ELEMENTS) for ph in _goldens() if ph["expected_page"]}
    for ph in goto_goldens:
        resolved = _resolve_placeholder(
            action=ph["action"],
            description=ph["description"],
            pages_data=pages_data,
            expected_page=ph["expected_page"],
            element_matcher=_NullElementMatcher(),
            flow_store=None,  # baseline
            expected_type=ph.get("expected_type"),
        )
        # baseline: navigation intent never resolves to the expected URL (it
        # either fails or falls back to a DOM element — both are wrong)
        assert resolved != ph["expected_locator"], f"baseline accidentally resolved {ph['description']} to {resolved!r}"


def test_goto_resolution_honors_from_context(tmp_path: Path) -> None:
    """The from-context matters: from the transfer page the flow says nothing
    about 'bill payments', so that GOTO must NOT resolve there (wrong context)."""
    store = _make_store(tmp_path)
    pages_data = {ph["expected_page"]: list(DUMMY_ELEMENTS) for ph in _goldens() if ph["expected_page"]}
    # 'navigate to bill payments' with the WRONG from-context (transfer page)
    resolved = _resolve_placeholder(
        action="GOTO",
        description="navigate to bill payments",
        pages_data=pages_data,
        expected_page=f"{BASE}/transfer.html",  # wrong from-context
        element_matcher=_NullElementMatcher(),
        flow_store=store,
        expected_type="url",
    )
    assert resolved != f"{BASE}/payments.html"
    # with the right from-context (dashboard) it resolves
    resolved_ok = _resolve_placeholder(
        action="GOTO",
        description="navigate to bill payments",
        pages_data=pages_data,
        expected_page=f"{BASE}/dashboard.html",
        element_matcher=_NullElementMatcher(),
        flow_store=store,
        expected_type="url",
    )
    assert resolved_ok == f"{BASE}/payments.html"
