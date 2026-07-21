# Playwright Actionability — Reference

Curated from Playwright documentation. Playwright performs a range of
actionability checks before executing most actions (click, fill, etc.).
Understanding these checks helps the resolver generate correct wait
strategies and timeout handling.

---

## Actionability Checks

Before performing an action, Playwright verifies the element is:
1. **Attached** — present in the DOM
2. **Visible** — not hidden by CSS (display:none, visibility:hidden)
3. **Stable** — not animating (position stable for at least one frame)
4. **Receives events** — not obscured by another element
5. **Enabled** — not disabled

If any check fails within the timeout, the action throws an error.

## Click

```python
page.get_by_role("button", name="Submit").click()
page.locator("#checkout-btn").click()
```

Auto-waits for the element to be actionable. If the element is covered by
a modal or overlay, the click will fail with a "is not visible" or
"intercepts pointer events" error.

### Click Options

```python
page.get_by_text("Details").click(button="right")  # right-click
page.get_by_text("Expand").click(position={"x": 10, "y": 10})
page.locator("button").click(force=True)  # skip actionability checks
```

## Fill (Text Input)

```python
page.get_by_label("Username").fill("admin")
page.get_by_placeholder("Search").fill("laptop")
```

Auto-clears the existing value before filling. Use `type()` or
`press_sequentially()` for character-by-character input (useful for
autocomplete fields).

```python
page.get_by_label("Search").press_sequentially("lap", delay=100)
```

## Select (Dropdown)

```python
page.get_by_label("Country").select_option("USA")
page.get_by_label("Size").select_option(value="large")
page.get_by_role("combobox").select_option(index=1)

# Multi-select
page.get_by_label("Colors").select_option(["Red", "Blue"])
```

## Check / Uncheck

```python
page.get_by_label("I agree").check()
page.get_by_role("checkbox").uncheck()
```

## Hover

```python
page.get_by_text("Menu").hover()
```

Useful for revealing dropdown menus and tooltips before clicking.

## Navigation

```python
page.goto("https://example.com/products")
page.go_back()
page.go_forward()
page.reload()
```

Navigation actions are not subject to actionability checks — they operate
on the page, not on elements.

## Modal and Overlay Handling

When a modal or overlay blocks pointer events, dismiss it first:

```python
# Wait for the modal to appear, then dismiss it
page.locator("#cartModal").wait_for(state="visible")
page.get_by_text("Continue Shopping").click()

# Wait for the modal to disappear before proceeding
page.locator("#cartModal").wait_for(state="hidden")
```

## Wait Strategies

```python
# Wait for element to be visible
page.get_by_text("Loading...").wait_for(state="visible")

# Wait for element to disappear
page.get_by_text("Loading...").wait_for(state="hidden")

# Wait for URL
page.wait_for_url("**/success")

# Wait for network idle (all requests complete)
page.wait_for_load_state("networkidle")
```

Prefer `wait_for(state=...)` over hardcoded `page.wait_for_timeout()`.
Time-based waits are fragile and make tests slow.
