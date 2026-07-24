"""Tests for ARIA snapshot parser."""

from __future__ import annotations

import pytest

from src.aria_parser import _is_child_property, _parse_aria_line, parse_aria_snapshot

# ── Child property detection ────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("- /placeholder: your@email.com", True),
        ("- /url: /products", True),
        ("- /checked:", True),
        ("- /selected:", True),
        ("- text: John", False),  # handled separately, not as child property
        ("  - /placeholder: value", True),
        ("- button", False),
        ("- textbox", False),
        ("- heading", False),
        ("- radio", False),
        ("- checkbox", False),
    ],
)
def test_is_child_property(line: str, expected: bool) -> None:
    assert _is_child_property(line) == expected


# ── Line parsing ────────────────────────────────────────────────


def test_parse_heading() -> None:
    result = _parse_aria_line('- heading "Create Your Account" [level=2] [box=240,-212,800,28]')
    assert result is not None
    assert result["role"] == "heading"
    assert result["accessible_name"] == "Create Your Account"
    assert result["_aria_level"] == "2"
    assert result["_bbox"] == {"x": 240.0, "y": -212.0, "width": 800.0, "height": 28.0}


def test_parse_textbox_with_children() -> None:
    result = _parse_aria_line('- textbox "Email Address *" [box=240,-143,800,38]:')
    assert result is not None
    assert result["role"] == "textbox"
    assert result["accessible_name"] == "Email Address *"
    assert result["_has_children"] is True


def test_parse_button() -> None:
    result = _parse_aria_line('- button "Login" [box=494,298,292,46]')
    assert result is not None
    assert result["role"] == "button"
    assert result["accessible_name"] == "Login"
    assert result["_bbox"] == {"x": 494.0, "y": 298.0, "width": 292.0, "height": 46.0}


def test_parse_radio() -> None:
    result = _parse_aria_line('- radio "Male" [box=417,351,16,16]')
    assert result is not None
    assert result["role"] == "radio"
    assert result["accessible_name"] == "Male"


def test_parse_checkbox() -> None:
    result = _parse_aria_line('- checkbox "Sports" [box=417,526,16,16]')
    assert result is not None
    assert result["role"] == "checkbox"
    assert result["accessible_name"] == "Sports"


def test_parse_combobox_with_options() -> None:
    result = _parse_aria_line('- combobox "Title *" [box=261,46,758,40]:')
    assert result is not None
    assert result["role"] == "combobox"
    assert result["accessible_name"] == "Title *"
    assert result["_has_children"] is True


def test_parse_option() -> None:
    result = _parse_aria_line('- option "Select..." [selected] [box=0,0,0,0]')
    assert result is not None
    assert result["role"] == "option"
    assert result["accessible_name"] == "Select..."


def test_parse_link_with_url() -> None:
    result = _parse_aria_line('- link "Home" [box=480,30,57,20]:')
    assert result is not None
    assert result["role"] == "link"
    assert result["accessible_name"] == "Home"


def test_parse_paragraph_with_text() -> None:
    result = _parse_aria_line("- paragraph [box=185,394,490,69]: All QA engineers can use this website")
    assert result is not None
    assert result["role"] == "paragraph"
    assert result["text"] == "All QA engineers can use this website"


def test_parse_group_container() -> None:
    result = _parse_aria_line('- group "Account Holder" [box=242,-10,796,290]:')
    assert result is not None
    assert result["role"] == "group"
    assert result["accessible_name"] == "Account Holder"


def test_parse_child_property_returns_none() -> None:
    # /placeholder, /url, /checked, /selected return None
    assert _parse_aria_line("- /placeholder: value") is None
    assert _parse_aria_line("- /url: /home") is None
    # text: is no longer a child property — it returns a text element
    text_elem = _parse_aria_line("- text: John")
    assert text_elem is not None
    assert text_elem["role"] == "text"
    assert text_elem["text"] == "John"


def test_parse_listitem() -> None:
    result = _parse_aria_line("- listitem [box=465,20,87,30]:")
    assert result is not None
    assert result["role"] == "listitem"


def test_parse_text_only_returns_none_for_short() -> None:
    result = _parse_aria_line("- text: A")
    assert result is None


def test_parse_text_only_returns_element_for_long() -> None:
    # "text: value" lines with a role before them are child properties,
    # not standalone text elements. Standalone text is like "- text: Some text".
    result = _parse_aria_line("- text: Some longer text")
    assert result is not None
    assert result["role"] == "text"
    assert result["text"] == "Some longer text"


# ── Full snapshot parsing ────────────────────────────────────────


def test_parse_lv_insurance_snapshot() -> None:
    yaml_text = """- heading "LV Insurance" [level=1] [box=240,71,800,50]
- text: Account section title
- heading "Create Your Account" [level=2] [box=240,217,800,28]
- textbox "Email Address *" [box=240,286,800,38]:
  - /placeholder: your@email.com
- textbox "Password *" [box=240,363,800,38]:
  - /placeholder: Min 8 characters
- button "Next" [box=932,691,108,41]"""

    elements = parse_aria_snapshot(yaml_text)
    # 2 headings, 1 text, 2 textboxes, 1 button = 6
    # Standalone "- text: " lines are now parsed as text elements
    assert len(elements) == 6

    # Textboxes should have placeholder from child property
    email = next(e for e in elements if e["accessible_name"] == "Email Address *")
    assert email["placeholder"] == "your@email.com"

    password = next(e for e in elements if e["accessible_name"] == "Password *")
    assert password["placeholder"] == "Min 8 characters"


def test_parse_saucedemo_snapshot() -> None:
    yaml_text = """- textbox "Username" [box=494,154,292,37]
- textbox "Password" [box=494,206,292,37]
- button "Login" [box=494,298,292,46]"""

    elements = parse_aria_snapshot(yaml_text)
    assert len(elements) == 3

    usernames = [e for e in elements if e["role"] == "textbox"]
    assert len(usernames) == 2
    assert usernames[0]["accessible_name"] == "Username"
    assert usernames[1]["accessible_name"] == "Password"


def test_parse_radio_checkbox_snapshot() -> None:
    yaml_text = """- radio "Male" [box=417,351,16,16]
- radio "Female" [box=492,351,16,16]
- radio "Other" [box=582,351,16,16]
- checkbox "Sports" [box=417,526,16,16]
- checkbox "Reading" [box=502,526,16,16]"""

    elements = parse_aria_snapshot(yaml_text)
    assert len(elements) == 5

    radios = [e for e in elements if e["role"] == "radio"]
    assert len(radios) == 3
    assert all(r["accessible_name"] for r in radios)

    checkboxes = [e for e in elements if e["role"] == "checkbox"]
    assert len(checkboxes) == 2
    assert all(c["accessible_name"] for c in checkboxes)


def test_parse_link_with_url_child() -> None:
    yaml_text = """- link "Products" [box=567,30,79,22]:
  - /url: /products
- link "Cart" [box=676,30,46,20]:
  - /url: /view_cart"""

    elements = parse_aria_snapshot(yaml_text)
    assert len(elements) == 2

    products = next(e for e in elements if e["accessible_name"] == "Products")
    assert products["href"] == "/products"

    cart = next(e for e in elements if e["accessible_name"] == "Cart")
    assert cart["href"] == "/view_cart"


def test_parse_input_value_from_text_child() -> None:
    yaml_text = """- textbox "Email" [box=240,286,800,38]:
  - /placeholder: your@email.com
  - text: test@test.com"""

    elements = parse_aria_snapshot(yaml_text)
    email = elements[0]
    assert email["placeholder"] == "your@email.com"
    assert email["value"] == "test@test.com"


def test_parse_nested_group() -> None:
    yaml_text = """- group "Account" [box=242,-10,796,290]:
  - textbox "First Name" [box=261,125,372,38]:
    - /placeholder: First name
  - textbox "Last Name" [box=648,125,372,38]:
    - /placeholder: Last name"""

    elements = parse_aria_snapshot(yaml_text)
    assert len(elements) == 3  # group + 2 textboxes
    assert elements[0]["role"] == "group"
    assert elements[0]["accessible_name"] == "Account"


def test_empty_snapshot() -> None:
    assert parse_aria_snapshot("") == []
    assert parse_aria_snapshot("   \n  \n") == []


def test_all_form_controls_have_accessible_name() -> None:
    """Sanity check: all form controls must have accessible name."""
    yaml_text = """- textbox "Username" [box=1,2,3,4]
- radio "Male" [box=1,2,3,4]
- checkbox "Agree" [box=1,2,3,4]
- combobox "Country" [box=1,2,3,4]:
  - option "UK" [box=0,0,0,0]
- button "Submit" [box=1,2,3,4]"""

    elements = parse_aria_snapshot(yaml_text)
    form_controls = [e for e in elements if e["role"] in {"textbox", "radio", "checkbox", "combobox", "button"}]
    assert len(form_controls) == 5
    for fc in form_controls:
        assert fc["accessible_name"], f"{fc['role']} should have accessible_name"
