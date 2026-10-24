Source: emitted test_eval_002.py from the 2026-10-24 rag_on_bundled leg on commit
ad489aa (the PRE-fix baseline, one leg before this directory's own emitted/).
Only test_06 is reproduced - it is the quote the record needs, and that leg is
not the run being re-scored. Extracted with: sed -n '44,50p' <that file>

CITATION CONVENTION: the left gutter is the ORIGINAL line number in the source
log; this file's own line numbers are 1..N over the whole file (header included).
The entries that cite this file give both numbers: the original log line, and this file's line.

  44  @pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
  45  def test_06_verify_cart_contents(page: Page, evidence_tracker):
  46      evidence_tracker.navigate('https://automationexercise.com/')
  47      pytest.skip("Skipping: unresolved placeholders for: 'Blue Top in cart'. 4 of 5 placeholders resolved")
  48      evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
  49      evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
  50      evidence_tracker.click('a[href="/view_cart"]', label='Cart', expected_page='https://automationexercise.com/products')
