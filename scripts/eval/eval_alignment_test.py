"""Tests for eval_alignment.py - the step/expected-result alignment metric (B-101).

A report/warn figure, never a pass/fail gate. The fixture deliberately
contains the three cases the scout named: one OPEN+DIRECT mismatch, one
FIXED+PROPERTY mismatch, and one aligned pair.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval_alignment import (
    classify_assertion,
    classify_criterion,
    compute_alignment,
)
from eval_metrics import HarnessReport

# One test function per criterion, in criterion order (the skeleton's contract).
EMITTED = """
from playwright.sync_api import Page

def test_01_add_item(page: Page, evidence_tracker):
    # criterion 0: OPEN ("add at least one item (e.g. Backpack)"),
    # emitted a DIRECT instance id -> OPEN+DIRECT mismatch.
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack')
    evidence_tracker.assert_visible('#remove-sauce-labs-backpack')

def test_02_page_loaded(page: Page, evidence_tracker):
    # criterion 1: FIXED ("Navigate to the cart page"),
    # emitted a loose property (#content) -> FIXED+PROPERTY mismatch.
    evidence_tracker.assert_visible('#content')

def test_03_count_rows(page: Page, evidence_tracker):
    # criterion 2: OPEN ("an item is in the cart"),
    # emitted a property emitter (assert_count_at_least) -> aligned.
    evidence_tracker.assert_count_at_least('[data-test="inventory-item"]', 1)

def test_04_fixed_url(page: Page, evidence_tracker):
    # criterion 3: FIXED ("Navigate to checkout"),
    # emitted a URL assertion (DIRECT) -> aligned.
    expect(page).to_have_url("http://example/checkout.html")
"""


def _dataset(tmp_path: Path) -> Path:
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "eval-x.json").write_text(
        json.dumps(
            {
                "id": "eval-x",
                "site": "example",
                "conditions": [
                    "Add at least one item (e.g. Backpack) to the cart",
                    "Navigate to the cart page",
                    "an item is in the cart",
                    "Navigate to the checkout page",
                ],
                "golden_resolutions": [],
            }
        ),
        encoding="utf-8",
    )
    return d


def test_classify_criterion_open_and_fixed() -> None:
    assert classify_criterion("Add at least one item (e.g. Backpack) to the cart") == "OPEN"
    assert classify_criterion("Select a radio button option (e.g. Male)") == "OPEN"
    assert classify_criterion("Navigate to the cart page") == "FIXED"
    assert classify_criterion("Select the Male radio") == "FIXED"


def test_classify_assertion_property_and_direct() -> None:
    # Property emitters are PROPERTY.
    assert classify_assertion("assert_count_at_least", '[data-test="inventory-item"]') == "PROPERTY"
    # A single-element check on a concrete instance id is DIRECT.
    assert classify_assertion("assert_visible", "#remove-sauce-labs-backpack") == "DIRECT"
    assert classify_assertion("assert_checked", "#gender-radio-1") == "DIRECT"
    # A loose / bare target is PROPERTY.
    assert classify_assertion("assert_visible", "#content") == "PROPERTY"
    assert classify_assertion("assert_visible", ".text") == "PROPERTY"
    # A URL assertion pins one page -> DIRECT.
    assert classify_assertion("to_have_url", 'expect(page).to_have_url("http://x")') == "DIRECT"


def test_compute_alignment_counts_the_three_cases(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    report = compute_alignment(dataset, {"eval-x": EMITTED})

    # Four ASSERT steps: criterion 0, 1, 2, 3.
    assert report.assert_steps == 4
    # Misaligned: OPEN+DIRECT (c0) and FIXED+PROPERTY (c1). c2 and c3 aligned.
    assert report.mismatched == 2
    assert report.open_direct == 1
    assert report.fixed_property == 1
    assert report.per_story["eval-x"]["mismatched"] == 2


def test_rate_line_is_the_reported_figure(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    report = compute_alignment(dataset, {"eval-x": EMITTED})
    assert report.rate_line() == "2 of 4 ASSERT steps are specificity-misaligned"
    assert report.rate_pct == 50.0


def test_rate_reported_in_harness_summary(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    report = compute_alignment(dataset, {"eval-x": EMITTED})
    harness = HarnessReport(stories=[], alignment=report.to_dict())
    summary = harness.to_summary()
    assert "2 of 4 ASSERT steps are specificity-misaligned" in summary
    # It is a report line, not a verdict - no FAIL/PASS wording.
    assert "specificity-misaligned" in summary
    assert "FAIL" not in summary
