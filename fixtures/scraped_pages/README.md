# Mock-page captures: the evidence the target pages rest on

Eight frozen DOM captures of the **banking mock this repository serves itself**
(`mock_sites/banking/`), taken from `http://localhost:8781` on 2026-10-07 by the eval scraper.

They are committed because the tests and the revalidator need them and they are **ours**:

- `test_dataset_page_targets.py` decides each CLICK row's `target_page` against them - a locator
  unique to one captured page settles the target; a locator on several pages is settled by the
  trail; anything else is uncheckable and counted.
- `revalidate_goldens.py` checks a state-dependent row (a page that only exists behind the mock's
  login) against its capture instead of skipping it.

## What is deliberately NOT here

The `scraped_pages/` working directory also holds captures of **third-party** pages
(saucedemo.com, automationexercise.com, demoqa.com, the-internet.herokuapp.com). Those are other
people's content, are not ours to republish, and stay out - which is why
`scripts/eval/scraped_pages/` is gitignored and this directory exists. A capture of a foreign page
is never required to make a test here pass; a row that needs one is counted as *outside the
committed evidence*, not silently skipped.

## The rule a missing file must follow

A capture that is missing is a **failure that names the file**, never a skip. A check that finds
nothing must say so: `tests/test_dataset_page_targets.py` asserts these five pages are present
(`index`, `dashboard`, `transfer`, `payments`, `transfer_success`) and fails with the missing names,
and `revalidate_goldens.load_captures()` raises when the directory itself is absent.

## Re-taking them

The files are the scraper's own JSON (`{"url": ..., "elements": [...]}`). To re-take one, start the
mock (`bash launch_dev.sh` serves `mock_sites/banking/` on :8781) and run the eval scraper against
that page; the file name is the URL with `http_` and the separators flattened, as the existing
names show. Re-taking is only needed when the mock's HTML changes - and a capture that disagrees
with a golden is a finding, not a fixture to nudge.
