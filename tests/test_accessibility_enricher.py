"""Tests for the accessibility tree enricher."""

from src.accessibility_enricher import AccessibilityEnricher

# -- Fixtures ----------------------------------------------------------------


def _sample_a11y_tree() -> dict:
    """Return a minimal but realistic a11y snapshot tree."""
    return {
        "role": "WebPage",
        "name": "",
        "properties": [],
        "childProperties": [],
        "children": [
            {
                "role": "button",
                "name": "View Cart",
                "properties": [{"name": "controls", "value": "cart-dropdown"}],
                "children": [],
            },
            {
                "role": "link",
                "name": "",
                "properties": [{"name": "url", "value": "https://example.com/products"}],
                "childProperties": [{"name": "alt", "value": "Shop Products"}],
                "children": [],
            },
            {
                "role": "textbox",
                "name": "Search products",
                "properties": [
                    {"name": "labelledby", "value": "search-label"},
                    {"name": "describedby", "value": "Type to search our catalog"},
                ],
                "children": [],
            },
        ],
    }


def _scraped_element(selector: str, text: str = "", role: str = "button", href: str = "") -> dict:
    """Build a minimal scraped element dict."""
    return {
        "selector": selector,
        "text": text,
        "role": role,
        "href": href,
        "title": "",
        "aria_label": "",
        "name": "",
        "id": "",
        "classes": "",
        "value": "",
        "placeholder": "",
    }


# -- Tests -------------------------------------------------------------------


class TestEnrichAddsAccessibleName:
    def test_enrich_adds_accessible_name_when_present(self) -> None:
        elements = [_scraped_element("#cart-btn", text="View Cart", role="button")]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        assert result[0].get("accessible_name") == "View Cart"
        assert result[0].get("computed_role") == "button"

    def test_enrich_preserves_element_without_a11y_match(self) -> None:
        elements = [_scraped_element("#unknown", text="No Match Here", role="div")]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        # Element is unchanged (no accessible_name added since nothing matched)
        assert "accessible_name" not in result[0] or not result[0].get("accessible_name")

    def test_enrich_matches_by_role_and_name(self) -> None:
        elements = [_scraped_element("#search", text="Search products", role="textbox")]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        assert result[0].get("accessible_name") == "Search products"
        assert result[0].get("computed_role") == "textbox"

    def test_enrich_handles_empty_a11y_tree(self) -> None:
        elements = [_scraped_element("#btn", text="Click me")]
        tree = {"role": "WebPage", "name": "", "properties": [], "childProperties": [], "children": []}

        result = AccessibilityEnricher.enrich(elements, tree)

        # No enrichment applied — tree has no interactive nodes
        assert "accessible_name" not in result[0] or not result[0].get("accessible_name")

    def test_enrich_resolves_aria_labelledby_text(self) -> None:
        elements = [_scraped_element("#search", text="Search products", role="textbox")]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        assert result[0].get("aria_describedby") == "Type to search our catalog"

    def test_enrich_does_not_overwrite_existing_aria_label(self) -> None:
        # Element already has an accessible_name set (simulating pre-enrichment)
        element = _scraped_element("#btn", text="View Cart", role="button")
        element["accessible_name"] = "Pre-existing name"
        elements = [element]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        # Should NOT overwrite the pre-existing value
        assert result[0]["accessible_name"] == "Pre-existing name"


class TestEnrichEdgeCases:
    def test_enrich_with_none_tree(self) -> None:
        elements = [_scraped_element("#btn", text="Click me")]

        result = AccessibilityEnricher.enrich(elements, {})

        assert result[0].get("accessible_name") is None or not result[0].get("accessible_name")

    def test_enrich_with_empty_elements_list(self) -> None:
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich([], tree)

        assert result == []

    def test_enrich_matches_by_href(self) -> None:
        elements = [
            _scraped_element('a[href="/products"]', text="Shop", role="link", href="https://example.com/products")
        ]
        tree = _sample_a11y_tree()

        result = AccessibilityEnricher.enrich(elements, tree)

        # The link node in the a11y tree has no name but does have a matching URL property
        assert "computed_role" in result[0] or "accessible_name" in result[0]


class TestFlattenA11yTree:
    def test_flatten_returns_interactive_nodes(self) -> None:
        tree = _sample_a11y_tree()

        nodes = AccessibilityEnricher._flatten_a11y_tree(tree)

        # Should find the button, link, and textbox nodes
        roles = [n.get("role", "") for n in nodes]
        assert "button" in roles
        assert "link" in roles
        assert "textbox" in roles

    def test_flatten_nested_tree(self) -> None:
        tree = {
            "role": "WebPage",
            "name": "",
            "properties": [],
            "childProperties": [],
            "children": [
                {
                    "role": "group",
                    "name": "Navigation",
                    "properties": [],
                    "children": [
                        {"role": "link", "name": "Home", "properties": [], "children": []},
                        {"role": "link", "name": "About", "properties": [], "children": []},
                    ],
                }
            ],
        }

        nodes = AccessibilityEnricher._flatten_a11y_tree(tree)

        names = [n.get("name", "") for n in nodes]
        assert "Home" in names
        assert "About" in names
