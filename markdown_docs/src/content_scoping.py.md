# `src/content_scoping.py` — Image / Heading Criterion Scoping

## Purpose
Keeps a content criterion that names an **image** or a **heading** inside the
right candidate set, and rejects a resolution whose element kind contradicts
the criterion.

Session 7 measured the defect: *"hero headline visible"* resolved to a hero
paragraph, and *"Noir Art image"* resolved to the tab button. The emitted
`assert_visible` then checked the wrong node — a false green. An image
criterion must resolve to an `<img>`; a headline criterion to a heading.

Part of **B-092** (the content / wrong-element half of gate 2). Consumed by
`src/element_matcher.py` and `src/placeholder_scorers.py`.

## Related
- `src/element_matcher.py` — calls the `scope_pages_to_*()` helpers before the
  passes and `kind_matches()` as the post-resolution guard
- `src/placeholder_scorers.py` — the `_kind_bonus` / visibility waiver that let
  the narrowed candidate set clear the match threshold
- `src/scraper.py` — extracts `<img>` elements with their `alt` so images are in
  the pool at all
- `src/code_postprocessor.py` — the page-fact/content classifiers that intercept
  page-scoped criteria before resolution

## Public API

### `is_image_criterion(description: str) -> bool`
True when an ASSERT description checks an image. Matches image nouns
(`image`, `screenshot`, `artwork`, `photo`, `picture`, `thumbnail`, `logo`) and
the natural-width / broken-image phrases. Returns False for page-level scans
(`all images have alt`, `no broken images`) — those belong to the classifier.

### `is_heading_criterion(description: str) -> bool`
True when the description names a heading (`headline`, `heading`, `title`).

### `is_image_element(element) -> bool` / `is_heading_element(element) -> bool`
True when the scraped element is an `<img>` / an `h1`–`h6`.

### `kind_matches(description, element) -> bool`
True when the element's kind is compatible with the criterion. A description
naming neither kind always passes. Used as the honest-skip guard.

### `scope_pages_to_images(action, description, pages_data)`
Narrows an image criterion's candidate set to `<img>` elements. Returns the
input unchanged for non-image criteria, or when no page has any image.

### `scope_pages_to_headings(action, description, pages_data)`
Narrows a heading criterion's candidate set to headings. A `headline` criterion
is scoped to `h1` specifically (the hero headline); a generic `heading`
criterion to `h1`–`h6`.

## Design Notes
- **Never a hard rejection of the whole resolution path**: when the kind set is
  empty the original pages are returned, so a genuinely absent image still
  produces the normal "not found" path rather than a silent misresolution.
- **Skip, don't guess**: when no image/heading matches, the guard returns
  `None`, and the orchestrator emits the honest unresolved-placeholder skip.
