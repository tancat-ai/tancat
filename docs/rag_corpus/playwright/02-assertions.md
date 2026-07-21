# Playwright Assertions — Reference

Curated from Playwright documentation. Assertions verify that the page or
an element is in the expected state. Playwright auto-waits for the condition
to be met before proceeding (up to the timeout).

---

## Auto-Retrying Assertions

All Playwright assertions are async and auto-retry until the condition is
met or the timeout expires. This eliminates the need for explicit `sleep()`
or `wait_for()` calls before assertions.

```python
# Auto-waits for the element to become visible, then checks text
expect(page.get_by_text("Order confirmed")).to_be_visible()

# Auto-waits for the URL to match
expect(page).to_have_url("https://example.com/success")
```

## Visibility Assertions

```python
expect(locator).to_be_visible()
expect(locator).to_be_hidden()
expect(locator).to_be_attached()  # in DOM, may be hidden
expect(locator).to_be_in_viewport()
```

Use `to_be_visible()` for elements that should be displayed on the page.
Use `to_be_hidden()` for confirmation that an element has disappeared
(e.g. loading spinner, modal dismissal).

## Text Content Assertions

```python
expect(locator).to_have_text("Expected text")  # exact match
expect(locator).to_contain_text("partial")     # substring match
expect(locator).to_have_value("input value")   # for <input> elements
```

For checkout/order confirmation pages, verify the summary text:
```python
expect(page.get_by_text("Thank you for your order")).to_be_visible()
expect(page.locator(".summary_total")).to_contain_text("$29.99")
```

## Count Assertions

```python
expect(locator).to_have_count(3)
expect(locator).to_have_count(0)  # useful for empty cart verification
```

## Page-Level Assertions

```python
expect(page).to_have_title("Products")
expect(page).to_have_url("https://example.com/cart")
expect(page).to_have_url(re.compile(r".*/checkout"))
```

Use `to_have_url()` for page-state assertions — it is the only precise
way to verify the user is on the correct page. DOM element assertions
(headings, titles) are unreliable because the same heading may appear
on multiple pages.

## Negating Assertions

```python
expect(locator).not_to_be_visible()
expect(locator).not_to_have_text("Error")
expect(page).not_to_have_url(re.compile(r".*/login"))
```

## Soft Assertions

Soft assertions do not stop the test on failure — they collect failures
and report all of them at once. Useful for multi-condition verification
without early exits.

```python
expect.soft(locator).to_be_visible()
expect.soft(locator).to_have_text("Expected")
# Test continues even if first assertion fails
```
