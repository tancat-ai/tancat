# Playwright Locators — Best Practices

Curated from Playwright documentation for RAG retrieval at resolution time.
These chunks help the resolver prefer robust, user-facing locators over
fragile CSS selectors.

---

## Overview

Playwright provides multiple ways to locate elements. The recommended order
of preference is: getByRole, getByLabel, getByPlaceholder, getByText,
getByTestId, and only then CSS/XPath selectors.

## getByRole

`page.get_by_role(role, name=...)` locates elements by their ARIA role,
accessible name, and accessible state. This is the most resilient locator
strategy because it mirrors how assistive technology perceives the page.

Example:
```python
page.get_by_role("button", name="Submit")
page.get_by_role("link", name="Home")
page.get_by_role("textbox", name="Email")
```

Roles include: button, link, textbox, checkbox, radio, combobox, listbox,
option, heading, img, alert, dialog, status, navigation, region, article,
table, row, cell, columnheader, rowheader, menu, menuitem, tab, tabpanel.

Use `name=` to match by accessible name (text content, aria-label, or
aria-labelledby). Use `exact=True` for exact string matching instead of
substring.

## getByLabel

`page.get_by_label(text)` locates form controls by their associated label
text. Ideal for input fields, checkboxes, and radio buttons.

Example:
```python
page.get_by_label("Email address").fill("user@example.com")
page.get_by_label("I agree to the terms").check()
```

## getByPlaceholder

`page.get_by_placeholder(text)` locates inputs by their placeholder
attribute value. Useful when labels are not present.

Example:
```python
page.get_by_placeholder("Search...").fill("query")
```

## getByText

`page.get_by_text(text)` locates elements containing the given text string.
Matches text content, not markup. Supports substring and exact matching.

Example:
```python
page.get_by_text("Welcome back")
page.get_by_text("Order #", exact=False)  # partial match
```

## getByTestId

`page.get_by_test_id(id)` locates elements by their `data-testid` attribute.
This is the most stable approach when the application under test supports
test IDs. It decouples tests from visual structure and CSS.

Example:
```python
page.get_by_test_id("submit-button")
page.get_by_test_id("cart-count")
```

## CSS and XPath

CSS and XPath selectors are tied to the DOM structure and CSS classes,
which change frequently. Prefer the user-facing locator methods above.
Use CSS/XPath only when no other locator strategy works.

```python
# Fragile — depends on CSS class naming
page.locator(".btn-primary-large")
page.locator("//button[contains(@class, 'submit')]")

# Better — structural attributes
page.locator("[data-test='login-button']")
```

## Chaining and Filtering

Locators can be chained and filtered for precision:

```python
# Chain: find a row, then find a button inside it
row = page.get_by_role("row", name="Product A")
row.get_by_role("button", name="Add to cart").click()

# Filter by text
page.get_by_role("listitem").filter(has_text="completed")

# Filter by child
page.get_by_role("article").filter(has=page.get_by_test_id("badge"))
```
