# `src/link_scoping.py` — Link-Criterion Scoping

## Purpose
Keeps a link-resolution criterion inside the anchor candidate set, and rejects a
resolution whose element does not match the link the criterion names.

A criterion such as *"Security Policy link resolves"* is about an `<a>` and
its `href`. Without scoping, the resolver's fast text pass can return a
`<span>` or container that merely *mentions* the link text — Session 7 measured
exactly that (the emitted `assert_attribute(…, 'href')` failed on a span that
has no href). If the named link does not exist at all, the resolver used to
fall back to an unrelated anchor (the nav logo, `href="#"`) instead of skipping
honestly.

Part of **B-088** (the page-level / section-scoped residue left after B-086
closed the `<head>` class). Consumed by `src/element_matcher.py`.

## Related
- `src/element_matcher.py` — calls `scope_pages_to_links()` before the passes and
  `link_name_matches()` as the post-resolution guard
- `src/placeholder_scorers.py` — the scoring path the narrowed candidate set feeds
- `src/code_postprocessor.py` — the page-level count/document/section classifiers
  that intercept page-scoped criteria before resolution

## Public API

### `is_link_criterion(description: str) -> bool`
True when an ASSERT description is a link-resolution check. Requires a link
noun (`link` / `anchor`) **and** a resolution signal (`resolv`, `404`, `href`,
`url`, `valid`, `mailto`). Returns False for page-level scans
(`no TBD in hrefs`, `all anchor links valid`) — those belong to the count
classifier.

### `is_anchor(element: dict[str, Any] | None) -> bool`
True when the element is an anchor or carries an `href` (tag `a`, role
`a`/`link`, a non-empty `href`/`raw_href`, or an `href` in the selector).

### `link_name_tokens(description: str) -> tuple[str, ...]`
The distinctive tokens of the link name in a criterion.
`"Watch 3-Min Walkthrough link resolves"` → `("watch", "3-min", "walkthrough")`.
Generic resolution words (`link`, `resolves`, `404`, `url`, `section`, …) are
dropped.

### `link_name_matches(description: str, element: dict[str, Any] | None) -> bool`
True when the element's text / aria-label / id / href / selector contains at
least one link-name token. A criterion with no distinctive tokens passes
(nothing to verify). Used as the honest-skip guard.

### `scope_pages_to_links(action, description, pages_data)`
Narrows a link criterion's candidate set to anchor elements only. Returns the
input unchanged for non-link criteria, or when no page has any anchor (a hard
filter to an empty set would hide a genuinely absent link).

## Design Notes
- **Never a hard rejection of the whole resolution path**: when the anchor set
  is empty the original pages are returned, so a missing link still produces the
  normal "not found" path rather than a silent misresolution.
- **Skip, don't guess**: when the named link is absent, the guard returns
  `None`, and the orchestrator emits the honest unresolved-placeholder skip.
