# How the pipeline works

The pipeline turns a story into a runnable test file in six stages. Two of them
use the LLM; the middle ones work on the real page.

## 1. Story analysis and the living test plan

The story is split into acceptance criteria. TanCat builds a plan - one row per
criterion - and asks you to review and sign it off before any test is written.
This is the last cheap place to fix an ambiguous story.

## 2. Skeleton generation (LLM)

For each criterion the LLM writes a pytest function with a typed placeholder
where a locator belongs:

```python
@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_confirmation_message(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://automationexercise.com/")
    evidence_tracker.click("{{CLICK:Products link in the header navigation}}")
    evidence_tracker.click("{{CLICK:Add to cart button for Blue Top}}")
    evidence_tracker.assert_visible("{{ASSERT:confirmation that the product was added to cart}}")
```

The model decides the *steps*; it does not guess selectors. That is the whole
point of the split.

## 3. DOM scraping

TanCat opens each page the story touches and captures its structure with three
layers:

- BeautifulSoup over the HTML,
- the Chrome DevTools Protocol accessibility tree,
- an ARIA snapshot.

Together these give computed accessible names, placeholder text and container
elements that a CSS-only scraper misses. The scrape is written to
`scrape_manifest.json` in the package.

## 4. Placeholder resolution

Each placeholder is scored against the scraped elements - by intent (what the
step is trying to do) and by semantics (what the element says). The best match
above the score gate becomes the selector:

```python
evidence_tracker.click('a[href="/products"]', label='Products', ...)
evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', ...)
evidence_tracker.assert_visible('#cartModal', label='product added to cart', ...)
```

A placeholder that does not clear the gate is **not** forced into a guess. It
becomes an explicit `pytest.skip`. See
[Placeholders, resolution and skips](skips.md).

## 5. Post-processing

The resolved steps are normalised into the sync pytest format TanCat ships:
no `async def`, no bare `asyncio.run`, imports at module level. The evidence
markers (`condition_ref`, `story_ref`) are attached to each function.

## 6. Persistence and reporting

The finished package is written under `generated_tests/`:

```
generated_tests/test_<timestamp>_<slug>/
├── test_<slug>.py              # the generated pytest suite
├── scrape_manifest.json        # what was scraped
├── coverage_summary.json       # criteria coverage
├── verification_strength.json  # how strongly each criterion was verified
├── package_manifest.json       # package metadata
├── pages/                      # per-page scrape data
└── evidence/                   # sidecars + per-step screenshots (after a run)
```

Run history and the local learning store live in `<root>/evidence/`:
`run_results.sqlite` and `rag_store.db`. See
[Evidence and reports](evidence.md).

## Why two phases

| One prompt | Two phases |
|---|---|
| The model invents selectors it cannot see. | The model writes structure; the page supplies selectors. |
| A wrong selector looks like a confident answer. | A weak match becomes a skip, not a guess. |
| Re-running needs the model again. | Resolution is deterministic given the same page. |

## Next

- [Placeholders, resolution and skips](skips.md)
- [Evidence and reports](evidence.md)
