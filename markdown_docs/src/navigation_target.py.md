# `src/navigation_target.py`

## Purpose
Decides which element on the current page IS the destination of a navigation step, and
whether that destination is known at all. A navigation (a GOTO, or a step whose words mean
"go to page X") is only valid when its destination is KNOWN - a URL the human gave us, or
the real `href` of a hyperlink on the page the cursor is on. When it is unknown the step
is an honest unresolved: a guess would resolve the step against the stale page and move
the cursor to a page nobody ever saw (the "Checkout" click that lands on the burger menu).

## Metadata
- **Lines:** ~170
- **Imports:** typing.Any, urllib.parse.urljoin, urllib.parse.urlparse

## Classes
| Class | Description |
|-------|-------------|
| (none - module level functions only) | |

## Functions
| Function | Description |
|----------|-------------|
| `target_words(description)` | The identity words of a navigation description, with grammar words ("go to the ... page") removed |
| `is_anchor(element)` | True when the element is a hyperlink (an anchor, or an element with a link role) |
| `identity_words(element)` | The words that name an element - visible text, accessible name, aria-label, data attributes, href path |
| `find_navigation_anchor(description, elements)` | The hyperlink on this page that names the destination, or None |
| `names_start_page(description)` | True when the description names the entry page ("home", "start page") |
| `start_page_url(description, seed_url)` | The entry page when the description names it, else None |

## Matching Rules
1. **Only an anchor counts.** A button with the same words is a different action - "add to
   cart" is not "the cart page". The cart link on saucedemo is an `<a role="button">`, so
   the tag is what decides, not the role.
2. **Full coverage.** The anchor must cover EVERY identity word of the description. A
   partial overlap names a different thing, so it is refused.
3. **Grammar is not identity.** "go to the transfer page" names "transfer"; the rest is
   grammar. When a description is nothing but grammar the raw words are kept.
4. **Hidden elements are not click targets** (`is_visible is False`).
5. **Identity comes from every name a human can read**: visible text, accessible name,
   aria-label, title, alt, data attributes, class names, id, name, and the href's path.
   An icon link with no text is still named "cart" by its `data-test` and its href.

## How It Is Used
- `src/orchestrator.py` - a GOTO whose URL is not in the human's input becomes a journey
  step that clicks the matching hyperlink (`JourneyStep.prefer_link`), so the browser
  observes where the click really lands and the trail carries the real transition.
- `src/journey_scraper.py` - `_discover_link_selector` uses `find_navigation_anchor` to
  pick that hyperlink.
- `src/placeholder_orchestrator.py` - `start_page_url` decides whether a GOTO names the
  entry page the human gave us.

## Related
- `src/placeholder_orchestrator.py` - the page cursor that consumes the observed trail.
- `src/journey_models.py` - `JourneyStep.prefer_link`.
