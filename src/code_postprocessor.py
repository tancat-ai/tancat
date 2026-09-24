"""Pure code-string transformation helpers extracted from TestOrchestrator.

Orchestrates normalization by delegating to specialised sub-modules:
- :mod:`src.llm_reasoning_filter` — detects and strips LLM reasoning text
- :mod:`src.code_normalizer` — deterministic normalization transforms
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .code_normalizer import (
    convert_standalone_placeholders,
    dedent_indented_test_blocks,
    deduplicate_skip_calls,
    ensure_test_navigation,
    fix_indentation,
    fix_module_scope_indentation,
    normalize_whitespace,
    replace_bare_ellipsis,
    replace_remaining_placeholders,
    strip_pages_needed_block,
)
from .llm_reasoning_filter import strip_llm_reasoning


def normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str:
    """Apply small deterministic fixes to common skeleton-generation mistakes."""
    fixed_code = code

    # Sanitise test function names: replace dots and other invalid characters with underscores.
    # LLMs sometimes generate names like 'def test_TC01.02_click_dress(...)' where dots
    # are taken from criterion IDs (TC01.02) and produce 'invalid decimal literal' syntax errors.
    fixed_code = re.sub(
        r"(def\s+test_)([A-Za-z_][A-Za-z0-9_.]*)",
        lambda m: m.group(1) + m.group(2).replace(".", "_"),
        fixed_code,
    )

    # Normalise test function names to include their condition_ref number.
    # LLMs generate inconsistent names: 'test_view_cart_link_shows_cart_table' vs 'test_tc01_05'.
    # This ensures every test function name starts with the numbered ref from its decorator.
    fixed_code = _normalize_test_function_names(fixed_code)

    # First: normalize whitespace (tabs → spaces, \r\n → \n) to ensure consistent
    # indentation before any other transforms are applied.
    fixed_code = normalize_whitespace(fixed_code)

    # Second: strip LLM reasoning text that may have leaked into the code block
    fixed_code = strip_llm_reasoning(fixed_code)

    # Convert standalone placeholder lines and unwrap evidence_tracker-wrapped placeholders.
    fixed_code = convert_standalone_placeholders(fixed_code)

    # Strip stray module-level executable statements (LLM leaks).
    # LLMs sometimes emit bare calls like ``home_page.click('Categories')`` or
    # ``evidence_tracker.assert_visible('h2')`` OUTSIDE any test function.
    # They reference fixtures that don't exist at module scope and crash pytest
    # at COLLECTION time — before any test runs. Imports, constants, decorators
    # and def/class blocks are preserved.
    fixed_code = _strip_module_level_statements(fixed_code)

    # Clean up malformed decorators if the LLM added spaces
    fixed_code = re.sub(r"@\s*pytest\s*\.\s*mark\s*\.\s*evidence", "@pytest.mark.evidence", fixed_code)

    # Always inject pytest at module level when the code uses any pytest constructs.
    if "pytest.skip(" in fixed_code or "pytest.mark." in fixed_code:
        fixed_code = inject_import(fixed_code, "import pytest")
    if re.search(r"\bPage\b", fixed_code) or "expect(" in fixed_code:
        fixed_code = inject_import(fixed_code, "from playwright.sync_api import Page, expect")

    # The tool ships an `evidence_tracker` fixture for generated tests.
    # Some LLMs hallucinate a non-existent `evidence_launcher` fixture name.
    fixed_code = re.sub(r"\bevidence_launcher\b", "evidence_tracker", fixed_code)
    fixed_code = _ensure_evidence_tracker_fixture(fixed_code)

    # Ensure evidence_tracker is used for common methods even if LLM forgot
    fixed_code = re.sub(r"page\.goto\(", "evidence_tracker.navigate(", fixed_code)
    fixed_code = re.sub(r"self\.page\.goto\(", "evidence_tracker.navigate(", fixed_code)

    # Some models hallucinate a slash between `pytest.mark` and the marker name.
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\s*/\s*([A-Za-z_][A-Za-z0-9_]*)", r"@pytest.mark.\1", fixed_code)

    # Some models hallucinate special constructor names (e.g. `__larry`)
    fixed_code = re.sub(
        r"(?m)(^\s*)def\s+__larry\s*\(\s*self\s*,\s*page\s*:\s*Page\s*\)\s*:\s*$",
        r"\1def __init__(self, page: Page) -> None:",
        fixed_code,
    )

    # Some models emit invalid keyword arguments when instantiating page objects.
    fixed_code = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*Page)\(\s*project\s*=\s*page\s*\)",
        r"\1(page)",
        fixed_code,
    )

    # Guardrail: strip invalid decorator assignment lines
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\w*\s*=\s*.*\n?", "", fixed_code)

    fixed_code = re.sub(r"(def __init__\(self,\s*page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(def test_[A-Za-z0-9_]*\(page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(?<=:\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
    fixed_code = re.sub(r"(?<=->\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)

    if consent_mode == "auto-dismiss":
        fixed_code = _inject_consent_helper(fixed_code)

    fixed_code = rewrite_page_references_in_class_methods(fixed_code)

    # Hallucination guard: record_condition(...) -> strip
    fixed_code = re.sub(r"(?m)^\s*evidence_tracker\.record_condition\(.*?\)\s*$", "", fixed_code)

    # Fix misplaced closing parenthesis in evidence_tracker method calls.
    fixed_code = re.sub(
        r"(evidence_tracker\.\w+\([^)]*)\)'\)(\s*,\s*\w+=)",
        r"\1)'\2",
        fixed_code,
    )

    # Ensure every test starts with a navigation if none present.
    fixed_code = ensure_test_navigation(fixed_code, target_url=target_url or None)

    # Dedent module-level constructs that the LLM accidentally indented
    fixed_code = fix_module_scope_indentation(fixed_code)

    # Safety net: replace any remaining unresolved placeholders with pytest.skip()
    fixed_code = replace_remaining_placeholders(fixed_code)
    fixed_code = strip_pages_needed_block(fixed_code)

    # Some models indent entire top-level test blocks after helper functions
    fixed_code = dedent_indented_test_blocks(fixed_code)

    # Fix inconsistent indentation inside test functions and class methods
    fixed_code = fix_indentation(fixed_code)

    # Deduplicate consecutive pytest.skip() calls in the same test block
    fixed_code = deduplicate_skip_calls(fixed_code)

    # Replace bare `...` (ellipsis) in test functions with pytest.skip()
    fixed_code = replace_bare_ellipsis(fixed_code)

    # FINAL safety net: run fix_indentation one more time after all transformations
    # This catches any indentation issues introduced by later steps
    fixed_code = fix_indentation(fixed_code)

    return fixed_code


# B-020: Map assertion types to evidence_tracker method names.
_ASSERTION_TO_ET_METHOD: dict[str, str] = {
    "toBeVisible": "assert_visible",
    "toHaveText": "assert_text",
    "toContainText": "assert_text_contains",
    "toBeDisabled": "assert_disabled",
    "toBeEnabled": "assert_enabled",
    "toBeChecked": "assert_checked",
    "toBeEmpty": "assert_empty",
    "toHaveValue": "assert_value",
    "toHaveCount": "assert_count",
    "toHaveClass": "assert_visible",  # no dedicated method yet, fall back
    "toHaveAttribute": "assert_attribute",  # B-069: read attribute, not visibility
    "toBeHidden": "assert_hidden",  # polarity: "popup closed" / "item removed"
}


# B-069 part b — attribute predicates and page-level count assertions.
# A green test must have actually checked the condition: "href does not
# contain TBD" checked by assert_visible() is a false green; the emitted
# check must read the attribute and test the predicate in the description.

#: Placeholder tokens that must never appear in a "live" attribute value.
_PLACEHOLDER_FORBIDDEN: tuple[str, ...] = ("tbd", "your_", "lorem", "placeholder", "todo")

#: Words that cannot be the forbidden word of a "no <word> in ..." check.
_NOT_FORBIDDEN_WORDS: frozenset[str] = frozenset({"longer", "more", "less", "horizontal", "visible", "broken", "long"})

#: Element-kind vocabulary for page-level count checks (singular key →
#: (css selector, attribute to inspect — None means text content)).
_COUNT_ELEMENT_KINDS: dict[str, tuple[str, str | None]] = {
    "link": ("a", "href"),
    "image": ("img", "alt"),
    "button": ("button", None),
    "heading": ("h1, h2, h3, h4, h5, h6", None),
}


@dataclass(frozen=True)
class CountAssertion:
    """A page-level assertion that needs no element resolution (B-069 part b).

    "no TBD in links" → no ``<a>`` href may contain "tbd".
    "all images have alt" → every ``<img>`` has a non-empty alt.
    "all anchor links valid" → every ``<a>`` href is non-empty and not a
    placeholder.

    B-088: ``tokens`` carries a multi-token forbidden set ("no link, button or
    heading anywhere contains placeholder text"), and ``also_text`` widens a
    single-attribute scan to the element's text too ("in no href and in no
    visible copy").
    """

    method: str  # "assert_no_forbidden" or "assert_attribute_all"
    selector: str  # CSS selector for the element class
    argument: str  # forbidden word (no_forbidden) or attribute name (attribute_all)
    attribute: str | None = None  # attribute to inspect (None = text content)
    forbidden: tuple[str, ...] = ()  # additional placeholder substrings to reject
    must_be_url: bool = False
    tokens: tuple[str, ...] = ()  # B-088: multi-token forbidden set
    also_text: bool = False  # B-088: inspect text in addition to the attribute


#: Words that ask for a non-http scheme, so ``must_be_url`` must not apply.
#: B-087: a criterion naming a ``mailto:`` link failed a correct page because
#: the emitter asserted http(s).
_SCHEME_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("mailto",), "mailto:"),
    (("tel:", "telephone link", "phone link"), "tel:"),
)


def attribute_scheme(description: str) -> str | None:
    """Return the URL scheme a criterion names (``mailto:``/``tel:``), else None.

    B-087: when a criterion asks for a specific scheme, the predicate is
    "starts with that scheme", not "is an http(s) URL".
    """
    lowered = description.lower()
    for keywords, scheme in _SCHEME_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return scheme
    return None


def attribute_predicate(description: str, attribute: str) -> tuple[bool, tuple[str, ...]]:
    """Derive ``(must_be_url, forbidden)`` for a per-element attribute assertion.

    - ``must_be_url``: the value must be an http(s) URL — when the attribute
      is href and the description says live/valid/url/resolves.
    - ``forbidden``: lowercase substrings that must NOT appear in the value —
      taken from the description ("does not contain TBD") and, when the value
      must be live, from the placeholder vocabulary.
    """
    lowered = description.lower()
    forbidden: list[str] = []
    m = re.search(r"\b(?:does not contain|without|no)\s+([a-z0-9_\-\.]+)", lowered)
    if m:
        word = m.group(1)
        if word not in _NOT_FORBIDDEN_WORDS:
            forbidden.append(word)
    if any(term in lowered for term in ("live", "valid", "resolv")):
        for token in _PLACEHOLDER_FORBIDDEN:
            if token not in forbidden:
                forbidden.append(token)
    # B-087: a scheme-naming criterion (mailto/tel) is not an http(s) check.
    scheme_keywords = any(keyword in lowered for keywords, _scheme in _SCHEME_KEYWORDS for keyword in keywords)
    must_be_url = (
        attribute == "href"
        and not scheme_keywords
        and any(term in lowered for term in ("url", "live", "valid", "resolv"))
    )
    return must_be_url, tuple(forbidden)


def count_assertion_from_description(description: str) -> CountAssertion | None:
    """Classify page-level count assertions that need no element resolution.

    - "no TBD in links" → every ``<a>`` href must not contain "tbd".
    - "no lorem ipsum in buttons" → no button text may contain "lorem".
    - "all images have alt" → every ``<img>`` has a non-empty alt.
    - "all anchor links valid" → every ``<a>`` href is non-empty and not a
      placeholder.

    Returns ``None`` when the description is not a page-level count check —
    the normal element-resolution path applies.
    """
    lowered = description.lower()
    m = re.search(
        r"\bno\s+([a-z0-9_\-\.]+(?:\s+[a-z0-9_\-\.]+)?)\s+in\s+"
        r"(links?|images?|buttons?|headings?|hrefs?)\b",
        lowered,
    )
    if m:
        word = m.group(1).split()[0]  # "lorem ipsum" → "lorem" (substring check)
        kind = m.group(2).rstrip("s")
        if word in _NOT_FORBIDDEN_WORDS:
            return None
        if kind == "href":
            # B-088: "no TBD in hrefs" — every element carrying an href
            # attribute, not just anchors (a preview image can carry one too).
            return CountAssertion("assert_no_forbidden", "[href]", word, "href")
        selector, attribute = _COUNT_ELEMENT_KINDS[kind]
        return CountAssertion("assert_no_forbidden", selector, word, attribute)
    # B-088: "no TBD in visible copy" / "... in the page text" — a page-level
    # text scan. The resolver cannot check this (it resolves one element), so
    # without the classifier it emitted a weakened assert_attribute on whatever
    # element ranked first (Session 7: the hero paragraph).
    m = re.search(
        r"\bno\s+([a-z0-9_\-\.]+(?:\s+[a-z0-9_\-\.]+)?)\s+in\s+"
        r"(?:the\s+)?(?:visible\s+|page\s+|body\s+)?(copy|text|copytext)\b",
        lowered,
    )
    if m:
        word = m.group(1).split()[0]
        if word in _NOT_FORBIDDEN_WORDS:
            return None
        return CountAssertion("assert_no_forbidden", "body", word)
    # B-088: the combined criterion shape — "No link, button or heading anywhere
    # on the page contains placeholder text — the strings "TBD",
    # "YOUR_VIDEO_ID_HERE" and "lorem ipsum" appear in no href and in no visible
    # copy". Scan links, buttons and headings for every named placeholder token
    # in BOTH href and text.
    if "placeholder text" in lowered and re.search(
        r"\blinks?\b[^.]*\bbuttons?\b|\bbuttons?\b[^.]*\bheadings?\b|\blinks?\b[^.]*\bheadings?\b",
        lowered,
    ):
        quoted = tuple(dict.fromkeys(re.findall(r'"([^"]+)"', description)))
        tokens = quoted or _PLACEHOLDER_FORBIDDEN
        selector = "a, button, h1, h2, h3, h4, h5, h6"
        return CountAssertion(
            "assert_no_forbidden",
            selector,
            tokens[0],
            "href",
            tokens=tokens,
            also_text=True,
        )
    m = re.search(
        r"\b(?:all|every)\s+(?:anchor\s+|external\s+)?(links?|images?|buttons?|headings?)\s+(?:have|has)\s+(?:a\s+)?(?:non-?empty\s+)?([a-z_]+)",
        lowered,
    )
    if m:
        kind = m.group(1).rstrip("s")
        attr = m.group(2)
        if kind not in _COUNT_ELEMENT_KINDS or attr not in ("alt", "href", "src", "title", "value", "content"):
            return None
        selector, _ = _COUNT_ELEMENT_KINDS[kind]
        return CountAssertion("assert_attribute_all", selector, attr, attr)
    if re.search(r"\b(?:all|every)\s+(?:anchor\s+|external\s+)?(links?)\s+(?:are\s+|is\s+)?valid\b", lowered):
        return CountAssertion("assert_attribute_all", "a", "href", "href", forbidden=_PLACEHOLDER_FORBIDDEN)
    return None


def _emit_count_assertion(indent: str, check: CountAssertion, description: str) -> str:
    """Emit the page-level count-assertion tracker call (B-069 part b)."""
    label = repr(description)
    if check.method == "assert_no_forbidden":
        tokens = check.tokens or (check.argument,)
        argument = repr(tokens[0]) if len(tokens) == 1 else repr(tokens)
        call = f"{indent}evidence_tracker.assert_no_forbidden({check.selector!r}, {argument}, label={label}"
        if check.attribute:
            call += f", attribute={check.attribute!r}"
        if check.also_text:
            call += ", also_text=True"
        return call + ")"
    call = f"{indent}evidence_tracker.assert_attribute_all({check.selector!r}, {check.argument!r}, label={label}"
    if check.forbidden:
        call += f", forbidden={check.forbidden!r}"
    if check.must_be_url:
        call += ", must_be_url=True"
    return call + ")"


# ---------------------------------------------------------------------------
# B-086 — document-level (`<head>`) assertions.
#
# The scraper collects only interactive and display tags plus elements with an
# id (src/scraper.py), so <meta>/<link>/<title> are NEVER in the candidate
# pool. A criterion about them therefore resolves to the nearest *visible*
# element and the assertion is weakened to something that element can satisfy —
# a green that checked nothing (measured 2026-09-24: the canonical-URL test
# "passed" by asserting visibility of a styled div).
#
# The fix: these targets have stable, well-known selectors, so no resolution is
# needed. Emit the attribute read against the real element. assert_attribute
# waits for state="attached", so a <meta> in <head> works and a MISSING tag
# fails honestly instead of passing.
#
# Scope note (deliberate): the href check validates that the tag exists and the
# attribute is non-empty. It does NOT HTTP-probe the destination's status — the
# same boundary B-072 drew for the resolve/404 criteria.
# ---------------------------------------------------------------------------

#: (keywords that identify the criterion, CSS selector, attribute to read).
#: First match wins, so put more specific phrases before more general ones.
_DOCUMENT_TARGETS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("open graph title", "og:title", "og title"), 'meta[property="og:title"]', "content"),
    (("open graph image", "og:image", "og image"), 'meta[property="og:image"]', "content"),
    (("open graph description", "og:description"), 'meta[property="og:description"]', "content"),
    (("open graph type", "og:type"), 'meta[property="og:type"]', "content"),
    (("open graph url", "og:url"), 'meta[property="og:url"]', "content"),
    (("twitter card",), 'meta[name="twitter:card"]', "content"),
    (("meta description", "meta tag description", "description meta tag"), 'meta[name="description"]', "content"),
    (("canonical",), 'link[rel="canonical"]', "href"),
    (("favicon", "fav icon", "site icon"), 'link[rel="icon"]', "href"),
    (("viewport meta", "meta viewport", "viewport tag"), 'meta[name="viewport"]', "content"),
    (("lang attribute", "html lang", "document language"), "html", "lang"),
)


@dataclass(frozen=True)
class DocumentAssertion:
    """A criterion about a `<head>`/document-level element (B-086).

    Carries the deterministic selector and attribute, so the emitter never has
    to resolve — and therefore can never resolve to a visible wrong element.
    """

    selector: str
    attribute: str


def document_assertion_from_description(description: str) -> DocumentAssertion | None:
    """Classify a criterion about a document-level (`<head>`) element.

    Returns the fixed selector + attribute to read, or ``None`` when the
    criterion is about an ordinary page element.
    """
    lowered = description.lower()
    for keywords, selector, attribute in _DOCUMENT_TARGETS:
        if any(keyword in lowered for keyword in keywords):
            return DocumentAssertion(selector=selector, attribute=attribute)
    return None


def _emit_document_assertion(indent: str, check: DocumentAssertion, description: str) -> str:
    """Emit the tracker call for a document-level assertion (B-086)."""
    return f"{indent}evidence_tracker.assert_attribute({check.selector!r}, {check.attribute!r}, label={description!r})"


# ---------------------------------------------------------------------------
# B-088 — section-containment assertions.
#
# A criterion the shape "the <section> tier tells the buyer how to start a
# conversation — a contact link or the email address appears inside that tier"
# is about a section CONTAINING a child, not about the visibility of two
# headings. Session 7 emitted two ``assert_visible`` calls (the tier heading and
# the "Contact us" heading) — a green that checked neither. When the skeleton
# keeps that shape (prompt rule: "X inside Y" is ONE assert), this classifier
# emits a scoped check with teeth: the child must exist inside the section.
# ---------------------------------------------------------------------------

#: Child kind → CSS selector for the element that must be inside the section.
_SECTION_CHILD_SELECTORS: dict[str, str] = {
    "contact link": 'a[href^="mailto:"], a[href*="contact"]',
    "email address": 'a[href^="mailto:"]',
    "email": 'a[href^="mailto:"]',
    "link": "a[href]",
    "button": "button",
    "image": "img",
}

_SECTION_WORDS = r"(?:tier|section|card|panel|area|region|banner|block)"

#: Section references that name no real heading — reject them so the emitted
#: check cannot fail on an unresolvable pronoun ("email inside that tier").
_SECTION_PRONOUNS: frozenset[str] = frozenset({"that", "this", "the", "it", "a", "an", "same", "above"})


@dataclass(frozen=True)
class SectionContainsAssertion:
    """A criterion about a child element appearing inside a named section (B-088)."""

    section: str  # heading text of the section, e.g. "Air-Gap / Defense"
    child: str  # CSS selector the section must contain


def section_contains_from_description(description: str) -> SectionContainsAssertion | None:
    """Classify a section-containment criterion.

    Recognises "<child> inside <section> [tier|section]" and
    "<section> [tier|section] contains|has|shows a <child>".
    """
    lowered = description.strip().lower()
    child_kinds = "|".join(re.escape(kind) for kind in _SECTION_CHILD_SELECTORS)
    m = re.search(
        rf"^(?P<child>{child_kinds})\s+(?:appears\s+|is\s+)?inside\s+(?:the\s+)?"
        rf"(?P<section>.+?)(?:\s+{_SECTION_WORDS})?[.!]?$",
        lowered,
    )
    if m is None:
        m = re.search(
            rf"^(?P<section>.+?)\s+{_SECTION_WORDS}\s+(?:contains|has|shows|displays)\s+(?:a\s+|an\s+)?"
            rf"(?P<child>{child_kinds})[.!]?$",
            lowered,
        )
    if m is None:
        return None
    section = m.group("section").strip().strip("'\"")
    child = _SECTION_CHILD_SELECTORS.get(m.group("child"))
    if not section or section in _SECTION_PRONOUNS or child is None:
        return None
    return SectionContainsAssertion(section=section, child=child)


def _emit_section_contains(indent: str, check: SectionContainsAssertion, description: str) -> str:
    """Emit the tracker call for a section-containment assertion (B-088)."""
    return f"{indent}evidence_tracker.assert_contains({check.section!r}, {check.child!r}, label={description!r})"


def _strip_module_level_statements(code: str) -> str:
    """Remove stray executable statements at module scope (LLM leaks).

    LLMs sometimes emit bare calls like ``home_page.click('Categories')`` or
    ``evidence_tracker.assert_visible('h2')`` outside any test function.
    They reference fixtures/variables that don't exist at module scope and
    crash pytest at COLLECTION time — before any test runs.

    Preserved: imports, comments, blank lines, module-level constants
    (``NAME = value``), decorators, and ``def``/``class`` blocks.
    """
    output_lines: list[str] = []
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            output_lines.append(line)
            continue
        if line[:1] in (" ", "	"):
            # Indented — inside a function/class body; leave untouched.
            output_lines.append(line)
            continue
        if stripped.startswith(("#", "def ", "class ", "from ", "import ", "@")):
            output_lines.append(line)
            continue
        # Module-level constant assignment (no call in the target): keep.
        lhs = stripped.split("=")[0].strip()
        if "=" in stripped and "(" not in lhs:
            output_lines.append(line)
            continue
        # Any remaining module-level line containing a call is a leak.
        if "(" in stripped and ")" in stripped:
            continue
        output_lines.append(line)
    return "\n".join(output_lines)


def _normalize_test_function_names(code: str) -> str:
    """Rename test functions to include their condition_ref number.

    The LLM generates inconsistent test names: some are numbered
    ('test_tc01_01'), others are purely descriptive
    ('test_view_cart_link_shows_cart_table'). This ensures every test
    function name is prefixed with the numbered ref from its decorator,
    preserving any descriptive suffix the LLM added.

    Example:
        @pytest.mark.evidence(condition_ref="TC01.05", ...)
        def test_view_cart_link_shows_cart_table(...):

    Becomes:
        @pytest.mark.evidence(condition_ref="TC01.05", ...)
        def test_tc01_05_view_cart_link_shows_cart_table(...):
    """
    # Match: @pytest.mark.evidence(condition_ref="TC01.05", ...) ... def test_some_name(
    pattern = re.compile(
        r"@pytest\.mark\.evidence\(condition_ref=[\"']([^\"']+)[\"'].*?\)"
        r"[\s\S]*?"
        r"def (test_\w+)\(",
        re.MULTILINE,
    )

    def _replacer(match: re.Match[str]) -> str:
        condition_ref = match.group(1).lower().replace(".", "_").replace("-", "_")
        original_name = match.group(2)

        # If the test name already starts with the condition_ref, preserve it as-is
        expected_prefix = f"test_{condition_ref}"
        if original_name == expected_prefix or original_name.startswith(expected_prefix + "_"):
            return match.group(0)  # Already correct — no change

        # If the test name already has a number (test_01_*, test_02_*, test_tc01_05_* etc.),
        # it's already numbered — keep the LLM's numbering to avoid breaking existing tests.
        # Only rename purely descriptive names like 'test_view_cart_link_shows_cart_table'.
        name_after_test = original_name[len("test_") :]
        has_number_prefix = bool(
            re.match(r"\d+", name_after_test.split("_")[0] if "_" in name_after_test else name_after_test)
        )
        has_tc_prefix = name_after_test.lower().startswith("tc")
        if has_number_prefix or has_tc_prefix:
            return match.group(0)  # Already numbered — leave as-is

        # Purely descriptive name — prepend the condition_ref
        pass_name = f"{expected_prefix}_{name_after_test}"

        # Reconstruct the full matched text with the new name
        return match.group(0).replace(original_name, pass_name)

    return pattern.sub(_replacer, code)


def _assertion_type_to_et_method(assertion_type: str) -> str:
    """Map a Playwright assertion type to the corresponding evidence_tracker method."""
    base_type = assertion_type.split(":", 1)[0]
    return _ASSERTION_TO_ET_METHOD.get(base_type, "assert_visible")


#: Tracker methods that accept ``expected_page``. The emitted call must match,
#: or the generated test raises TypeError at run time. Kept in step with
#: EvidenceTracker: click / fill / assert_visible / assert_hidden are the only
#: ones this pipeline emits (toHaveText is remapped to assert_visible).
_EXPECTED_PAGE_METHODS = frozenset({"click", "fill", "assert_visible", "assert_hidden"})


def replace_token_in_line(
    line: str,
    action: str,
    token: str,
    resolved_value: str,
    duplicate_selectors: set[str],
    description: str = "",
    fill_value: str = "",
    assertion_type: str = "toBeVisible",
    expected_page: str = "",
) -> str:
    """Replace a single placeholder token within a code line.

    Args:
        assertion_type: B-020 assertion type for ASSERT actions
            (e.g. "toBeVisible", "toHaveText", "toContainText").
            Default is "toBeVisible" for backward compatibility.
        expected_page: The page this placeholder was resolved against, emitted
            as ``expected_page=`` so the evidence sidecar can flag a step that
            runs somewhere else (AI-067). Empty means "do not check".
    """
    emitted = _replace_token_in_line_impl(
        line,
        action,
        token,
        resolved_value,
        duplicate_selectors,
        description,
        fill_value=fill_value,
        assertion_type=assertion_type,
    )
    return _annotate_expected_page(emitted, expected_page)


def _annotate_expected_page(emitted: str, expected_page: str) -> str:
    """Attach ``expected_page`` to an emitted tracker call when it is supported.

    Only tracker calls are annotated. ``pytest.skip(...)`` lines and plain
    locator lines are returned untouched, as are methods that do not accept the
    argument, so the emitted test can never fail on an unexpected keyword.
    """
    if not expected_page:
        return emitted
    stripped = emitted.strip()
    if not stripped.startswith("evidence_tracker.") or not stripped.endswith(")"):
        return emitted
    method = stripped[len("evidence_tracker.") :].split("(", 1)[0].strip()
    if method not in _EXPECTED_PAGE_METHODS:
        return emitted
    return f"{emitted.rstrip()[:-1]}, expected_page={expected_page!r})"


def _replace_token_in_line_impl(
    line: str,
    action: str,
    token: str,
    resolved_value: str,
    duplicate_selectors: set[str],
    description: str = "",
    fill_value: str = "",
    assertion_type: str = "toBeVisible",
) -> str:
    """Replace a single placeholder token within a code line.

    Args:
        assertion_type: B-020 assertion type for ASSERT actions
            (e.g. "toBeVisible", "toHaveText", "toContainText").
            Default is "toBeVisible" for backward compatibility.
    """
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]

    # B-069 part b: page-level count assertions ("no TBD in links",
    # "all images have alt") need no element — emit the structural check
    # directly, before the unverified-skip path can replace the line.
    if action == "ASSERT":
        count_check = count_assertion_from_description(description)
        if count_check is not None:
            return _emit_count_assertion(indent, count_check, description)

    # B-086: document-level (`<head>`) criteria have no scraped candidate —
    # emit the attribute read against the real element instead of letting the
    # resolver pick a visible lookalike and weaken the check to assert_visible.
    if action == "ASSERT":
        document_check = document_assertion_from_description(description)
        if document_check is not None:
            return _emit_document_assertion(indent, document_check, description)

    # B-088: a section-containment criterion ("contact link inside Air-Gap
    # tier") is a scoped structural check — emit it before element resolution
    # can weaken it to two unrelated visibility asserts.
    if action == "ASSERT":
        section_check = section_contains_from_description(description)
        if section_check is not None:
            return _emit_section_contains(indent, section_check, description)

    if "pytest.skip" in resolved_value:
        return f"{indent}{resolved_value}"

    # B-021: URL assertions are already complete Playwright expressions
    # (e.g., 'expect(page).to_have_url("...")') — return as-is.
    if resolved_value.strip().startswith("expect("):
        return f"{indent}{resolved_value}"

    step_label = description if description else token

    if "pytest.skip" in resolved_value and "label=" in stripped:
        return f"{indent}{resolved_value}"

    if action == "CLICK":
        selector_literal = resolved_value
        if not (resolved_value.startswith("'") or resolved_value.startswith('"')):
            selector_literal = repr(resolved_value)
        if stripped == token:
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        if stripped == f"{token}.click()":
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
            f"page.locator({token}).first",
            f"self.page.locator({token}).first",
        }
        locator_click_patterns = {
            f"page.locator({token}).click()",
            f"self.page.locator({token}).click()",
            f"page.locator({token}).first.click()",
            f"self.page.locator({token}).first.click()",
        }
        if stripped in locator_only_patterns or stripped in locator_click_patterns:
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"

    if action == "ASSERT":
        assert_value = resolved_value
        if not (resolved_value.startswith("'") or resolved_value.startswith('"')):
            assert_value = repr(resolved_value)

        # B-020: route to correct evidence_tracker method by assertion_type
        et_method = _assertion_type_to_et_method(assertion_type)
        # Guardrail: assert_text and assert_text_contains require (selector, expected, label)
        # but we only have (selector, label) from the resolver. Fall back to assert_visible.
        if et_method in ("assert_text", "assert_text_contains"):
            et_method = "assert_visible"
        # B-069 part b: attribute assertions (href/alt/meta) must pass the
        # attribute name + predicate to assert_attribute — extract the name
        # from assertion_type (e.g., "toHaveAttribute:href") or fall back to
        # parsing the description; the predicate (must_be_url / forbidden)
        # comes from the description so "does not contain TBD" cannot pass.
        attr_call = None
        if et_method == "assert_attribute":
            if ":" in assertion_type:
                attr_name = assertion_type.split(":", 1)[1]
            else:
                # Derive from description keywords as fallback
                lowered = description.lower()
                attr_name = (
                    "href"
                    if "href" in lowered
                    else ("alt" if "alt" in lowered else ("content" if "meta" in lowered else ""))
                )
            must_be_url, forbidden = attribute_predicate(description, attr_name)
            scheme = attribute_scheme(description)
            extra = ""
            if must_be_url:
                extra += ", must_be_url=True"
            if scheme:
                extra += f", required_scheme={scheme!r}"
            if forbidden:
                extra += f", forbidden={forbidden!r}"
            attr_call = (
                f"evidence_tracker.assert_attribute({assert_value}, {attr_name!r}, label={repr(step_label)}{extra})"
            )
        if stripped == token:
            if et_method == "assert_attribute":
                return f"{indent}{attr_call}"
            return f"{indent}evidence_tracker.{et_method}({assert_value}, label={repr(step_label)})"
        if re.search(r"expect\((?:self\.)?page\.locator\(.*?\)\)\.to_\w+\(.*\)", stripped):
            if et_method == "assert_attribute":
                return f"{indent}{attr_call}"
            return f"{indent}evidence_tracker.{et_method}({assert_value}, label={repr(step_label)})"
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
        }
        if stripped in locator_only_patterns:
            if et_method == "assert_attribute":
                return f"{indent}{attr_call}"
            return f"{indent}evidence_tracker.{et_method}({assert_value}, label={repr(step_label)})"
        return line.replace(token, resolved_value)

    if action == "FILL":
        if stripped == token:
            return f"{indent}evidence_tracker.fill({resolved_value}, {repr(fill_value)}, label={repr(step_label)})"
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
        }
        locator_fill_patterns = {
            f'page.locator({token}).fill("")',
            f'self.page.locator({token}).fill("")',
            f"page.locator({token}).fill('')",
            f"self.page.locator({token}).fill('')",
        }
        if stripped in locator_only_patterns or stripped in locator_fill_patterns:
            return f"{indent}evidence_tracker.fill({resolved_value}, {repr(fill_value)}, label={repr(step_label)})"
        fill_no_value = re.match(
            r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
            stripped,
        )
        if fill_no_value:
            return f"{indent}{fill_no_value.group(1)}{resolved_value}, {repr(fill_value)}{fill_no_value.group(3)}{repr(step_label)})"
        return line.replace(token, resolved_value)

    if action in {"GOTO", "URL"}:
        if stripped == token:
            return f"{indent}evidence_tracker.navigate({resolved_value})"
        goto_patterns = {
            f"page.goto({token})",
            f"self.page.goto({token})",
            f"evidence_tracker.navigate({token})",
            f'page.goto("{token}")',
            f"page.goto('{token}')",
            f'self.page.goto("{token}")',
            f"self.page.goto('{token}')",
            f'evidence_tracker.navigate("{token}")',
            f"evidence_tracker.navigate('{token}')",
        }
        if stripped in goto_patterns:
            return f"{indent}evidence_tracker.navigate({resolved_value})"
        if f'"{token}"' in line:
            return line.replace(f'"{token}"', resolved_value)
        if f"'{token}'" in line:
            return line.replace(f"'{token}'", resolved_value)
        return line.replace(token, resolved_value)

    return line.replace(token, resolved_value)


def _ensure_evidence_tracker_fixture(code: str) -> str:
    """Add the evidence_tracker and page pytest fixture arguments to tests that use evidence_tracker.

    The evidence_tracker fixture depends on the page fixture from Playwright,
    so both must be present in the function signature. Additionally, page is
    needed for dismiss_consent_overlays(page) and POM instantiation.

    CRITICAL: Any test that uses evidence_tracker OR references a POM class
    (e.g., HomePage(page, evidence_tracker)) MUST have both `page: Page` and
    `evidence_tracker` parameters, even if the body only uses the POM.
    """
    lines = code.splitlines()
    updated_lines: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)def\s+(test_\w+)\(([^)]*)\)(.*):\s*$", line)
        if not match:
            updated_lines.append(line)
            index += 1
            continue

        block_lines: list[str] = []
        lookahead = index + 1
        while lookahead < len(lines):
            next_line = lines[lookahead]
            if next_line and not next_line[0].isspace() and re.match(r"^(?:@|def |class |import |from )", next_line):
                break
            block_lines.append(next_line)
            lookahead += 1

        body = "\n".join(block_lines)

        # Detect evidence_tracker usage
        needs_evidence_tracker = "evidence_tracker." in body

        # Detect patterns that require the 'page' fixture:
        # - POM instantiation: HomePage(page, ...) or any *Page(page, ...)
        # - dismiss_consent_overlays(page) — injected AFTER this function, so always assume needed
        # - Any bare 'page.' reference that's not self.page.
        pom_pattern = re.search(r"=\s*\w+Page\(page", body)
        bare_page_reference = re.search(r"(?<!self\.)page\.(goto|locator|click|fill|wait_for|deselect|select)", body)
        dismiss_consent_usage = "dismiss_consent_overlays(" in body

        # CRITICAL FIX: If evidence_tracker is used, page is ALWAYS needed
        # because dismiss_consent_overlays(page) is injected after navigation steps,
        # and POM instantiation requires page.
        needs_page = bool(pom_pattern) or bool(bare_page_reference) or needs_evidence_tracker or dismiss_consent_usage

        # If a POM class is instantiated (e.g., HomePage(page, evidence_tracker)),
        # both page and evidence_tracker are needed regardless of body content
        pom_instantiation = re.search(r"=\s*\w+Page\(", body)
        if pom_instantiation:
            needs_page = True
            needs_evidence_tracker = True

        if not needs_evidence_tracker and not needs_page:
            updated_lines.append(line)
            index += 1
            continue

        params = [param.strip() for param in match.group(3).split(",") if param.strip()]
        param_names = [param.split(":", 1)[0].split("=", 1)[0].strip() for param in params]

        # 'page' must always be present when evidence_tracker is used (fixture dependency)
        # and when POM instantiation uses page
        if "page" not in param_names:
            params.insert(0, "page: Page")
        else:
            # Ensure page is first since evidence_tracker depends on it
            params = [p for p in params if p.split(":", 1)[0].split("=", 1)[0].strip() != "page"]
            params.insert(0, "page: Page")

        if needs_evidence_tracker and "evidence_tracker" not in param_names:
            params.append("evidence_tracker")

        line = f"{match.group(1)}def {match.group(2)}({', '.join(params)}){match.group(4)}:"

        updated_lines.append(line)
        index += 1

    return "\n".join(updated_lines)


def inject_import(code: str, import_line: str) -> str:
    """Inject an import line at the top of the file (after any docstring)."""
    lines = code.splitlines(keepends=True)
    insert_at = 0
    # Skip module docstring
    if lines and lines[0].strip().startswith('"""'):
        for i, line in enumerate(lines):
            insert_at = i + 1
            if '"""' in line and i > 0:
                break
    # Don't duplicate - check for exact import match (normalized whitespace)
    normalized_new = " ".join(import_line.split())
    if any(normalized_new in " ".join(line.split()) for line in lines):
        return code
    lines.insert(insert_at, import_line + "\n")
    return "".join(lines)


# B-031: EvidenceTracker assert methods added after the original strip was
# written (B-020 polarity/state family). Map each to its Playwright assertion.
_SINGLE_ARG_ASSERTS: dict[str, str] = {
    "assert_hidden": "to_be_hidden",
    "assert_disabled": "to_be_disabled",
    "assert_enabled": "to_be_enabled",
    "assert_checked": "to_be_checked",
    "assert_empty": "to_be_empty",
}

_DOUBLE_ARG_ASSERTS: dict[str, str] = {
    "assert_text": "to_have_text",
    "assert_text_contains": "to_contain_text",
    "assert_value": "to_have_value",
    "assert_count": "to_have_count",
}


def _strip_tracker_asserts(code: str, *, tracker: str, page_expr: str) -> str:
    """Convert ``tracker.assert_*`` calls to Playwright ``expect()`` assertions.

    Handles the one-arg (locator, label=...) and two-arg (locator, expected,
    label=...) forms used by the EvidenceTracker assert family that the
    original strip predates. ``assert_visible`` is handled separately by the
    callers.

    Args:
        tracker: callable prefix, e.g. ``"evidence_tracker"`` or
            ``"self.tracker"``.
        page_expr: locator receiver, e.g. ``"page"`` or ``"self.page"``.
    """
    for method, pw_assert in _SINGLE_ARG_ASSERTS.items():
        code = re.sub(
            rf"{re.escape(tracker)}\.{method}\(([^,]+),\s*label=[^\)]*\)",
            rf"expect({page_expr}.locator(\1)).{pw_assert}()",
            code,
        )
        code = re.sub(
            rf"{re.escape(tracker)}\.{method}\(([^,)]+)\s*\)",
            rf"expect({page_expr}.locator(\1)).{pw_assert}()",
            code,
        )
    for method, pw_assert in _DOUBLE_ARG_ASSERTS.items():
        # Quoted expected value: assert_text(sel, 'Welcome', label=...)
        code = re.sub(
            rf"{re.escape(tracker)}\.{method}\(([^,]+),\s*(['\"])(.*?)\2,\s*label=[^\)]*\)",
            rf"expect({page_expr}.locator(\1)).{pw_assert}(\2\3\2)",
            code,
        )
        # Bare expected value: assert_count(sel, 3, label=...)
        code = re.sub(
            rf"{re.escape(tracker)}\.{method}\(([^,]+),\s*([^,'\"]+),\s*label=[^\)]*\)",
            rf"expect({page_expr}.locator(\1)).{pw_assert}(\2)",
            code,
        )
    return code


def strip_evidence_from_test_code(code: str, *, preserve_pom_calls: bool = False) -> str:
    """Convert evidence-aware test code to clean Playwright test code.

    Before: evidence_tracker.click("#button", label="button")
    After:  page.locator("#button").click()

    Before: evidence_tracker.fill("#input", "value", label="input")
    After:  page.locator("#input").fill("value")

    Before: def test_x(page, evidence_tracker: EvidenceTracker):
    After:  def test_x(page):

    Args:
        preserve_pom_calls: When True (POM-mode export), keep page-object
            imports, instantiations and method calls intact (only the
            ``evidence_tracker`` argument is dropped from instantiations).
            When False (flat export), POM calls are inlined as direct
            Playwright locator calls (the POM methods carry the resolved
            selector).
    """
    result = code

    # evidence_tracker.click(selector, label=...) -> page.locator(selector).click()
    result = re.sub(
        r"evidence_tracker\.click\(([^,]+),\s*label=[^\)]*\)",
        r"page.locator(\1).click()",
        result,
    )

    # evidence_tracker.fill(selector, value, label=...) -> page.locator(selector).fill(value)
    result = re.sub(
        r"evidence_tracker\.fill\(([^,]+),\s*([^,]+),\s*label=[^\)]*\)",
        r"page.locator(\1).fill(\2)",
        result,
    )

    # evidence_tracker.navigate(url) or evidence_tracker.navigate(url, label=...) -> page.goto(url)
    result = re.sub(
        r"evidence_tracker\.navigate\(([^,]+)(?:,\s*label=[^\)]*)?\)",
        r"page.goto(\1)",
        result,
    )

    # evidence_tracker.assert_visible(selector, label=...) -> expect(page.locator(selector)).to_be_visible()
    result = re.sub(
        r"evidence_tracker\.assert_visible\(([^,]+),\s*label=[^\)]*\)",
        r"expect(page.locator(\1)).to_be_visible()",
        result,
    )

    # evidence_tracker.assert_visible(selector) without label= -> expect(page.locator(selector)).to_be_visible()
    result = re.sub(
        r"evidence_tracker\.assert_visible\(([^,)]+)\s*\)",
        r"expect(page.locator(\1)).to_be_visible()",
        result,
    )

    # Remaining evidence_tracker.assert_* family (B-020 polarity/state
    # methods added after the original strip was written — assert_hidden was
    # the live gap: it survived exports and NameError'd at runtime).
    result = _strip_tracker_asserts(result, tracker="evidence_tracker", page_expr="page")

    # evidence_tracker.select(selector, value, label=...) -> page.locator(selector).select_option(value)
    result = re.sub(
        r"evidence_tracker\.select\(([^,]+),\s*([^,]+),\s*label=[^\)]*\)",
        r"page.locator(\1).select_option(\2)",
        result,
    )

    # evidence_tracker.get_text(selector, label=...) -> page.locator(selector).text_content()
    result = re.sub(
        r"evidence_tracker\.get_text\(([^,]+),\s*label=[^\)]*\)",
        r"page.locator(\1).text_content()",
        result,
    )

    # --- Clean up test signatures: remove evidence_tracker parameter ---
    # Handle type-hinted parameter first: evidence_tracker: EvidenceTracker
    result = re.sub(
        r"(def\s+test_\w+)\(page,\s*evidence_tracker\s*:\s*EvidenceTracker\s*\):",
        r"\1(page):",
        result,
    )
    # Handle bare parameter: evidence_tracker
    result = re.sub(
        r"(def\s+test_\w+)\(page,\s*evidence_tracker\s*\):",
        r"\1(page):",
        result,
    )
    # Handle evidence_tracker in middle position (type-hinted)
    result = re.sub(
        r"(def\s+test_\w+\([^)]*?)\s*,\s*evidence_tracker\s*:\s*EvidenceTracker(.*?)\):",
        lambda m: f"{m.group(1)}{m.group(2)}):",
        result,
    )
    # Handle evidence_tracker in middle position (bare)
    result = re.sub(
        r"(def\s+test_\w+\([^)]*?)\s*,\s*evidence_tracker(.*?)\):",
        lambda m: f"{m.group(1)}{m.group(2)}):",
        result,
    )

    # --- Import cleanup ---
    # Remove EvidenceTracker import
    result = re.sub(
        r"^from src\.evidence_tracker import EvidenceTracker\s*$",
        "",
        result,
        flags=re.MULTILINE,
    )

    # Remove dismiss_consent_overlays import
    result = re.sub(
        r"^from src\.browser_utils import dismiss_consent_overlays\s*$",
        "",
        result,
        flags=re.MULTILINE,
    )

    # Remove @pytest.mark.evidence decorators (bare, arg-carrying, multi-line).
    # B-031: the old regex only matched the bare form, so generated tests'
    # `@pytest.mark.evidence(condition_ref="T01", story_ref="S01")` survived
    # into exports and produced PytestUnknownMarkWarning at collection.
    result = _strip_evidence_decorators(result)

    # Ensure playwright import includes expect
    if "expect(" in result:
        result = re.sub(
            r"from playwright\.sync_api import Page\b(?!, expect)",
            "from playwright.sync_api import Page, expect",
            result,
        )
        # Ensure the import exists
        if "from playwright.sync_api import Page" not in result:
            result = inject_import(result, "from playwright.sync_api import Page, expect")
    elif "page." in result:
        if "from playwright.sync_api import Page" not in result:
            result = inject_import(result, "from playwright.sync_api import Page, expect")

    # Remove dismiss_consent_overlays(page) calls
    result = re.sub(r"^\s*dismiss_consent_overlays\(page\)\s*$", "", result, flags=re.MULTILINE)
    result = re.sub(r"^\s*dismiss_consent_overlays\(self\.page\)\s*$", "", result, flags=re.MULTILINE)

    if preserve_pom_calls:
        # --- POM-mode export: keep POM structure, drop the tracker argument ---
        # home_page = HomePage(page, evidence_tracker) -> home_page = HomePage(page)
        result = re.sub(
            r"(\w+_page)\s*=\s*(\w+Page)\((?:self\.)?page,\s*evidence_tracker\s*\)",
            r"\1 = \2(page)",
            result,
        )
    else:
        # --- POM → flat conversion (export of POM-mode packages) ---
        # POM-mode tests reference page objects that a flat export does not
        # carry: imports, instantiations, and method calls must be converted to
        # direct Playwright calls (the POM methods carry the resolved selector).
        # Remove POM imports:  from pages.home_page import HomePage
        result = re.sub(r"^from pages\.[\w.]* import .*$", "", result, flags=re.MULTILINE)
        # Remove POM instantiations:  home_page = HomePage(page, evidence_tracker)
        result = re.sub(
            r"^\s*(\w+_page)\s*=\s*\w+\((?:self\.)?page,\s*evidence_tracker\s*\)\s*$",
            "",
            result,
            flags=re.MULTILINE,
        )
        # home_page.click('label', selector='sel') -> page.locator('sel').click()
        result = re.sub(
            r"\w+_page\.click\(\s*(['\"])([^'\"]*)\1\s*,\s*selector=\s*(['\"])(.*?)\3\s*\)",
            r"page.locator('\4').click()",
            result,
        )
        # home_page.click('label') -> page.get_by_text('label').first.click() (best effort)
        result = re.sub(
            r"\w+_page\.click\(\s*(['\"])([^'\"]*)\1\s*\)",
            r"page.get_by_text('\2').first.click()",
            result,
        )
        # home_page.fill('label', 'value', selector='sel') -> page.locator('sel').fill('value')
        result = re.sub(
            r"\w+_page\.fill\(\s*(['\"])([^'\"]*)\1\s*,\s*(['\"])(.*?)\3\s*,\s*selector=\s*(['\"])(.*?)\5\s*\)",
            r"page.locator('\6').fill('\4')",
            result,
        )
        # home_page.fill('label', 'value') -> page.get_by_label('label').fill('value') (best effort)
        result = re.sub(
            r"\w+_page\.fill\(\s*(['\"])([^'\"]*)\1\s*,\s*(['\"])(.*?)\3\s*\)",
            r"page.get_by_label('\2').fill('\4')",
            result,
        )

    # Remove blank lines that were left behind (collapse multiple blank lines to one)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def _strip_evidence_decorators(code: str) -> str:
    """Remove ``@pytest.mark.evidence`` decorators in all emitted forms.

    Generated tests carry arg-carrying decorators:

        @pytest.mark.evidence(condition_ref="T01", story_ref="S01")

    Older exports stripped only the bare form, so the arg-carrying form
    survived into exports and raised ``PytestUnknownMarkWarning`` at
    collection time. Handles bare, single-line-arg and multi-line-arg forms
    (a decorator whose argument list spans several lines is consumed whole).
    """
    output_lines: list[str] = []
    lines = code.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if re.match(r"^@\s*pytest\s*\.\s*mark\s*\.\s*evidence\s*(?:\(|$)", stripped):
            # Consume the decorator line(s) until parentheses balance.
            depth = 0
            while index < len(lines):
                depth += lines[index].count("(") - lines[index].count(")")
                index += 1
                if depth <= 0:
                    break
            continue
        output_lines.append(lines[index])
        index += 1
    return "".join(output_lines)


def strip_evidence_from_pom(code: str) -> str:
    """Convert evidence-aware POM to clean POM for export.

    Before: self.tracker.click("#button", label="button")
    After:  self.page.locator("#button").click()

    Before: def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
    After:  def __init__(self, page: Page) -> None:
    """
    result = code

    # Remove @pytest.mark.evidence decorators if any (bare / arg-carrying)
    result = _strip_evidence_decorators(result)

    # Remove EvidenceTracker import
    result = re.sub(r"^from src\.evidence_tracker import EvidenceTracker\s*$", "", result, flags=re.MULTILINE)

    # Replace __init__ signature: remove tracker parameter
    result = re.sub(
        r"def __init__\(self, page: Page, tracker: EvidenceTracker\) -> None:",
        "def __init__(self, page: Page) -> None:",
        result,
    )

    # Replace self.tracker = tracker with self.tracker = None (or remove)
    result = re.sub(r"^\s*self\.tracker = tracker\s*$", "", result, flags=re.MULTILINE)

    # self.tracker.click(selector, label=...) -> self.page.locator(selector).click()
    result = re.sub(
        r"self\.tracker\.click\(([^,]+),\s*label=[^\)]*\)",
        r"self.page.locator(\1).click()",
        result,
    )

    # self.tracker.fill(selector, value, label=...) -> self.page.locator(selector).fill(value)
    result = re.sub(
        r"self\.tracker\.fill\(([^,]+),\s*([^,]+),\s*label=[^\)]*\)",
        r"self.page.locator(\1).fill(\2)",
        result,
    )

    # self.tracker.assert_visible(selector, label=...) -> expect(self.page.locator(selector)).to_be_visible()
    result = re.sub(
        r"self\.tracker\.assert_visible\(([^,]+),\s*label=[^\)]*\)",
        r"expect(self.page.locator(\1)).to_be_visible()",
        result,
    )

    # Remaining self.tracker.assert_* family (same as the test-code strip).
    result = _strip_tracker_asserts(result, tracker="self.tracker", page_expr="self.page")

    # self.tracker.get_text(selector, label=...) -> self.page.locator(selector).text_content()
    result = re.sub(
        r"self\.tracker\.get_text\(([^,]+),\s*label=[^\)]*\)",
        r"self.page.locator(\1).text_content()",
        result,
    )

    # self.tracker.select(selector, value, label=...) -> self.page.locator(selector).select_option(value)
    result = re.sub(
        r"self\.tracker\.select\(([^,]+),\s*([^,]+),\s*label=[^\)]*\)",
        r"self.page.locator(\1).select_option(\2)",
        result,
    )

    # self.tracker.navigate(url) -> self.page.goto(url)
    result = re.sub(
        r"self\.tracker\.navigate\(([^,)]+)(?:,\s*label=[^\)]*)?\)",
        r"self.page.goto(\1)",
        result,
    )

    # Ensure expect import if needed
    if "expect(" in result:
        result = re.sub(
            r"from playwright\.sync_api import Page\b",
            "from playwright.sync_api import Page, expect",
            result,
        )
        if "from playwright.sync_api import Page" not in result:
            result = inject_import(result, "from playwright.sync_api import Page, expect")

    # Remove blank lines that were left behind
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result
    return result


def rewrite_page_references_in_class_methods(code: str) -> str:
    """Replace bare `page.` references with `self.page.` inside instance methods."""
    rewritten_lines: list[str] = []
    inside_class = False
    is_test_class = False
    class_indent = 0
    inside_instance_method = False
    method_indent = 0

    for line in code.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped.startswith("class "):
            inside_class = True
            class_indent = indent
            inside_instance_method = False
            class_name = stripped[6:].split(":", 1)[0].split("(", 1)[0].strip()
            is_test_class = class_name.startswith("Test") or class_name.endswith("Test")
        elif inside_class and stripped and indent <= class_indent and not stripped.startswith("#"):
            inside_class = False
            is_test_class = False
            inside_instance_method = False

        if inside_class and not is_test_class and stripped.startswith("def "):
            signature = stripped.split("(", maxsplit=1)[1] if "(" in stripped else ""
            inside_instance_method = signature.startswith("self,") or signature.startswith("self)")
            method_indent = indent
        elif inside_instance_method and stripped and indent <= method_indent and not stripped.startswith("#"):
            inside_instance_method = False

        if inside_instance_method and "page." in line and "self.page." not in line:
            line = re.sub(r"\bpage\.", "self.page.", line)

        if inside_instance_method:
            method_sig = ""
            if "(" in stripped and ")" in stripped:
                method_sig = stripped.split("(", 1)[1].split(")")[0]
            has_evidence_tracker_param = "evidence_tracker" in method_sig

            if not has_evidence_tracker_param:
                line = re.sub(r"\bevidence_tracker\.", "self.evidence_tracker.", line)

            line = re.sub(
                r"\bdismiss_consent_overlays\(\s*page\s*\)",
                "dismiss_consent_overlays(self.page)",
                line,
            )
            line = line.replace("(page)", "(self.page)")
            line = line.replace("Page(", "self.page(")

        rewritten_lines.append(line)

    return "\n".join(rewritten_lines)


def _inject_consent_helper(code: str) -> str:
    """Inject the dismiss_consent_overlays import and calls into the code.

    NOTE: evidence_tracker.navigate() already calls dismiss_consent_overlays()
    internally, so we only inject after bare page.goto() calls to avoid
    double-dismissal (which doubles the time spent on every test navigation).
    """
    helper_name = "dismiss_consent_overlays"
    import_line = "from src.browser_utils import dismiss_consent_overlays"

    # Inject import if dismiss_consent_overlays is used anywhere in the code.
    # (code_normalizer may inject the call alongside evidence_tracker.navigate(),
    #  so we need the import even without bare page.goto().)
    has_helper_call = f"{helper_name}(" in code
    has_bare_goto = "page.goto(" in code

    if not has_helper_call and not has_bare_goto:
        return code

    if import_line not in code:
        insert_after = "from playwright.sync_api import Page, expect"
        if insert_after in code:
            code = code.replace(insert_after, insert_after + "\n" + import_line, 1)
        else:
            code = import_line + "\n" + code

    lines = code.splitlines()
    updated_lines: list[str] = []
    for line in lines:
        updated_lines.append(line)
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if f"{helper_name}(" in stripped:
            continue

        # Only inject after bare page.goto() — NOT after evidence_tracker.navigate()
        # because evidence_tracker.navigate() already calls dismiss_consent_overlays()
        # internally, so injecting there would double the consent-dismissal work.
        if stripped.startswith("page.goto("):
            updated_lines.append(f"{indent}{helper_name}(page)")

    return "\n".join(updated_lines)
