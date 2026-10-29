"""t-1049: a generated "go to the page" step states the page it expects.

Owner's decision, 2026-10-29: "It may be that the redirect is on purpose, but that
should be for the user to decide. And if the user is just given the address and
the address redirects, then they need to be made aware of that."

Before this, the tracker could take an ``expected_page`` but no emitter passed
one, so generated code called ``navigate(url)`` with a single argument: a site
that quietly redirected to ``/login`` was recorded and still passed.

Three emitters now name the page, and nothing else changes:

- ``replace_token_in_line`` (GOTO/URL placeholders) - the address the pipeline
  just chose is also the page it expects.
- ``normalise_generated_code`` - a raw ``page.goto("...")`` the model wrote.
- ``ensure_test_navigation`` - the injected entry navigation.

The comparison itself stays in the tracker and uses the product's page-identity
rule (scheme + host + path), never a whole-string compare. No ``to_have_url``
assert is added: the arrival rule from j-0214 is untouched, so a step whose
arrival is already asserted by the trail gate is not checked twice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from src.code_normalizer import ensure_test_navigation
from src.code_postprocessor import (
    normalise_generated_code,
    replace_token_in_line,
    strip_evidence_from_test_code,
)
from src.evidence_tracker import EvidenceTracker

# ---------------------------------------------------------------------------
# The emitters name the page
# ---------------------------------------------------------------------------


def test_a_goto_placeholder_emits_the_page_it_expects() -> None:
    emitted = replace_token_in_line(
        line='    evidence_tracker.navigate("{{GOTO:products page}}")',
        action="GOTO",
        token="{{GOTO:products page}}",
        resolved_value="'https://example.com/products'",
        duplicate_selectors=set(),
        description="products page",
    )

    assert emitted.strip() == (
        "evidence_tracker.navigate('https://example.com/products', expected_page='https://example.com/products')"
    )


def test_a_bare_goto_placeholder_emits_the_page_it_expects() -> None:
    emitted = replace_token_in_line(
        line="    {{GOTO:products page}}",
        action="GOTO",
        token="{{GOTO:products page}}",
        resolved_value="'https://example.com/products'",
        duplicate_selectors=set(),
        description="products page",
    )

    assert emitted.strip() == (
        "evidence_tracker.navigate('https://example.com/products', expected_page='https://example.com/products')"
    )


def _normalised_body(goto_line: str) -> str:
    """Run the normaliser on a test whose body is one raw goto line."""
    code = "\n".join(
        [
            "from playwright.sync_api import Page",
            "",
            "def test_goto(page: Page, evidence_tracker) -> None:",
            f"    {goto_line}",
            "",
        ]
    )
    fixed = normalise_generated_code(code)
    assert "def test_goto" in fixed  # the module-level strip did not eat the test
    return fixed


def test_a_raw_page_goto_is_rewritten_with_the_expected_page() -> None:
    fixed = _normalised_body('page.goto("https://example.com/cart.html")')

    assert 'evidence_tracker.navigate("https://example.com/cart.html"' in fixed
    assert 'expected_page="https://example.com/cart.html"' in fixed


def test_a_raw_page_goto_of_a_variable_names_that_variable() -> None:
    fixed = _normalised_body("page.goto(target_url)")

    assert "evidence_tracker.navigate(target_url, expected_page=target_url)" in fixed


def test_a_raw_page_goto_built_by_a_call_is_left_without_an_expected_page() -> None:
    """Splitting a call argument would guess; better no check than a wrong one."""
    fixed = _normalised_body('page.goto(build_url("cart", item))')

    assert "evidence_tracker.navigate(build_url(" in fixed
    assert "expected_page" not in fixed


def test_the_injected_entry_navigation_names_the_page() -> None:
    code = """def test_foo(page: Page, evidence_tracker) -> None:
    evidence_tracker.click("#btn", label="click")
"""
    result = ensure_test_navigation(code, target_url="https://example.com")

    assert 'evidence_tracker.navigate("https://example.com", expected_page="https://example.com")' in result


def test_an_existing_single_argument_navigate_is_not_rewritten() -> None:
    """A step whose expected page was never emitted behaves as it does today."""
    code = """def test_foo(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://example.com")
    evidence_tracker.click("#btn", label="click")
"""
    result = ensure_test_navigation(code, target_url="https://example.com")

    assert result.count("navigate(") == 1
    assert "expected_page" not in result


# ---------------------------------------------------------------------------
# The seam: run the emitted call through a real tracker
# ---------------------------------------------------------------------------


def _page(url: str, status: int = 200, *, redirect_from: str = "") -> MagicMock:
    """A page double whose goto returns *status* and moves it to *url*."""
    page = MagicMock()
    page.url = "about:blank"
    response = MagicMock()
    response.status = status
    if redirect_from:
        hop = MagicMock()
        hop.url = redirect_from
        hop.redirected_from = None
        response.request.redirected_from = hop

    def _goto(target: str) -> Any:
        page.url = url  # WHERE this double lands (its configured final address)
        return response

    page.goto.side_effect = _goto
    return page


def _tracker(page: Any, tmp_path: Path) -> EvidenceTracker:
    tracker = EvidenceTracker(page, "test_goto", "C01", "S01", evidence_root=Path(tmp_path))
    tracker.journey_hooked = True  # the conftest's hand-shake (t-1066)
    return tracker


def _emitted_goto(url: str) -> str:
    """The exact line the emitter writes for a GOTO placeholder."""
    return replace_token_in_line(
        line='    evidence_tracker.navigate("{{GOTO:page}}")',
        action="GOTO",
        token="{{GOTO:page}}",
        resolved_value=repr(url),
        duplicate_selectors=set(),
        description="page",
    ).strip()


def test_a_200_on_the_expected_page_passes(tmp_path: Path) -> None:
    url = "https://shop.example.com/cart.html"
    page = _page(url)
    tracker = _tracker(page, tmp_path)

    eval(_emitted_goto(url), {"evidence_tracker": tracker})  # noqa: S307 - generated-step text under test

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    assert step["result"]["navigation"]["requested"] == url
    assert step["result"]["navigation"]["final"] == url


def test_a_redirect_to_another_page_fails_and_names_both_addresses(tmp_path: Path) -> None:
    asked_for = "https://shop.example.com/inventory.html"
    landed = "https://shop.example.com/login"
    page = _page(landed)
    tracker = _tracker(page, tmp_path)

    eval(_emitted_goto(asked_for), {"evidence_tracker": tracker})  # noqa: S307

    # t-1057: recorded, not raised at the step; the test fails once at its end.
    message = tracker.journey_summary()
    assert asked_for in message
    assert landed in message

    step = tracker.steps[-1]
    assert step["result"]["status"] == "failed"
    assert step["result"]["page_mismatch"] == {"expected": asked_for, "actual": landed}
    assert step["result"]["navigation"]["requested"] == asked_for
    assert step["result"]["navigation"]["final"] == landed


def test_a_redirect_that_lands_on_the_expected_page_passes_and_is_recorded(tmp_path: Path) -> None:
    asked_for = "https://shop.example.com/cart"
    landed = "https://shop.example.com/cart/"
    page = _page(landed)
    tracker = _tracker(page, tmp_path)

    eval(_emitted_goto(asked_for), {"evidence_tracker": tracker})  # noqa: S307

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    nav = step["result"]["navigation"]
    assert nav["redirected"] is True
    assert nav["requested"] == asked_for
    assert nav["final"] == landed
    assert "both name the same page" in nav["note"]


def test_a_step_without_an_expected_page_behaves_as_before(tmp_path: Path) -> None:
    asked_for = "https://shop.example.com/inventory.html"
    landed = "https://shop.example.com/login"
    page = _page(landed)
    tracker = _tracker(page, tmp_path)

    # The single-argument call older generated tests carry.
    tracker.navigate(asked_for)

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    nav = step["result"]["navigation"]
    assert nav["redirected"] is True
    assert "recorded, not judged" in nav["note"]


def test_a_redirect_back_to_the_same_address_is_still_recorded(tmp_path: Path) -> None:
    """A session bounce that returns to the same address leaves no URL trace.

    The redirect chain is the only evidence of it, so it is recorded - and the
    identity matches, so the step still passes.
    """
    url = "https://shop.example.com/checkout"
    page = _page(url, redirect_from="https://shop.example.com/login")
    tracker = _tracker(page, tmp_path)

    eval(_emitted_goto(url), {"evidence_tracker": tracker})  # noqa: S307

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    nav = step["result"]["navigation"]
    assert nav["redirected"] is True
    assert nav["redirect_chain"] == ["https://shop.example.com/login"]
    assert "both name the same page" in nav["note"]


def test_a_relative_address_never_fabricates_a_redirect(tmp_path: Path) -> None:
    """The browser resolves a relative address; that is not a redirect."""
    page = _page("https://shop.example.com/cart")
    tracker = _tracker(page, tmp_path)

    tracker.navigate("/cart")

    nav = tracker.steps[-1]["result"]["navigation"]
    assert "redirected" not in nav


def test_the_flat_export_drops_the_expected_page_keyword(tmp_path: Path) -> None:
    """A stripped tracker call must not keep a keyword whose fixture is gone.

    ``strip_evidence_from_test_code`` turns ``evidence_tracker.navigate(...)``
    into ``page.goto(...)`` for the flat export. Every keyword is dropped, or
    the exported test would call ``page.goto(url, expected_page=...)``.
    """
    code = "\n".join(
        [
            "def test_goto(page, evidence_tracker) -> None:",
            "    evidence_tracker.navigate('https://example.com/cart', expected_page='https://example.com/cart')",
            "    evidence_tracker.click('#buy', label='buy')",
            "",
        ]
    )

    stripped = strip_evidence_from_test_code(code)

    assert "page.goto('https://example.com/cart')" in stripped
    assert "expected_page" not in stripped


# ---------------------------------------------------------------------------
# t-1051 (j-0226 review, t-1050): four shapes the first cut got wrong.
# All four FAIL on a663aab: the keyword-form goto and the two-level nested call
# are asserted below, the strip case is asserted below, and the foreign keyword
# case is asserted below (it was a TypeError at run time, not a compile error).
# ---------------------------------------------------------------------------


def _generated_goto(goto_line: str) -> str:
    """The test body the normaliser writes for one raw goto line."""
    return _normalised_body(goto_line)


def _goto_line(code: str) -> str:
    lines = [
        line.strip()
        for line in code.splitlines()
        if ("navigate(" in line or "goto(" in line) and not line.lstrip().startswith("def ")
    ]
    assert len(lines) == 1, lines
    return lines[0]


def test_a_keyword_form_goto_compiles_and_keeps_the_expected_page() -> None:
    """BLOCKER on a663aab: ``page.goto(url=\"...\")`` became
    ``navigate(url=..., expected_page=url=...)`` - an invalid-syntax file."""
    generated = _generated_goto('page.goto(url="https://x/cart")')

    compile(generated, "<generated>", "exec")
    line = _goto_line(generated)
    assert line.startswith('evidence_tracker.navigate(url="https://x/cart"')
    assert line.count("expected_page") == 1
    assert 'expected_page="https://x/cart"' in line


def test_a_two_level_nested_goto_still_keeps_its_navigation_evidence() -> None:
    """BEHAVIOUR LOSS on a663aab: it stayed a raw ``page.goto``, so the step
    recorded no navigation evidence at all."""
    generated = _generated_goto("page.goto(os.path.join(base, urlparse(u).path))")

    compile(generated, "<generated>", "exec")
    line = _goto_line(generated)
    assert line == "evidence_tracker.navigate(os.path.join(base, urlparse(u).path))"
    assert "expected_page" not in line  # recorded, not judged


def test_the_flat_export_leaves_a_nested_call_intact() -> None:
    """BEHAVIOUR LOSS on a663aab: the strip truncated it to
    ``page.goto(get_url(a)`` and dropped an argument."""
    code = "\n".join(
        [
            "def test_goto(page, evidence_tracker) -> None:",
            "    evidence_tracker.navigate(get_url(a, b))",
            "",
        ]
    )

    stripped = strip_evidence_from_test_code(code)

    compile(stripped, "<stripped>", "exec")
    assert "evidence_tracker.navigate(get_url(a, b))" in stripped


def test_a_foreign_keyword_is_dropped_not_forwarded() -> None:
    """PRE-EXISTING on a663aab: ``timeout=5000`` was forwarded to a navigate()
    that does not take it - a TypeError at run time, not a compile error."""
    generated = _generated_goto('page.goto("https://x/cart", timeout=5000)')

    compile(generated, "<generated>", "exec")
    line = _goto_line(generated)
    assert line == 'evidence_tracker.navigate("https://x/cart", expected_page="https://x/cart")'
    assert "timeout" not in line


def test_the_tracker_call_the_emitter_writes_is_callable() -> None:
    """The emitted keyword set must be one navigate() actually accepts."""
    import inspect

    from src.evidence_tracker import EvidenceTracker

    signature = inspect.signature(EvidenceTracker.navigate)
    for keyword in ("url", "label", "expected_page"):
        assert keyword in signature.parameters, keyword


def test_an_unusable_goto_does_not_stop_the_next_one_being_rewritten() -> None:
    """One odd line must not leave the rest of the file unconverted."""
    code = "\n".join(
        [
            "def test_goto(page, evidence_tracker) -> None:",
            "    page.goto(timeout=5000)",
            "    page.goto('https://x/cart')",
            "",
        ]
    )

    generated = normalise_generated_code(code)

    compile(generated, "<generated>", "exec")
    assert "page.goto(timeout=5000)" in generated  # kept verbatim
    assert "evidence_tracker.navigate('https://x/cart', expected_page='https://x/cart')" in generated
