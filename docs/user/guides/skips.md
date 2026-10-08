# Placeholders, resolution and skips

This is the feature that makes TanCat's output trustworthy: when the resolver is
not confident, the test **skips**. It never turns a guess into a green pass.

## What a placeholder is

In the skeleton phase, the LLM writes the test steps but leaves a typed
placeholder where a selector belongs:

```python
@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_confirm_modal(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://example.com/")
    evidence_tracker.click("{{CLICK:Open the confirm modal}}")
    evidence_tracker.assert_visible("{{ASSERT:Confirm modal is shown}}")
```

`{{CLICK:...}}` and `{{ASSERT:...}}` are the two you will see most; the action
name is always a real step type, never invented.

## Resolution is score-gated

For every placeholder, TanCat scrapes the page and scores the real elements
against the description. A match must clear the score gate to be accepted. The
result is a real selector:

```python
evidence_tracker.click('#open-modal', label='Open the confirm modal', ...)
evidence_tracker.assert_visible('.modal-dialog', label='Confirm modal is shown', ...)
```

## An unresolved placeholder becomes a skip

If nothing clears the gate, the placeholder is not replaced with a best guess.
It is removed and a single `pytest.skip(...)` is inserted at the top of the test
function, naming what could not be resolved:

```python
@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_confirm_modal(page: Page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'Confirm modal is shown'. 1 of 2 placeholders resolved")
    evidence_tracker.navigate("https://example.com/")
    ...
```

The message has a fixed prefix - `Skipping: unresolved placeholders for:` - and,
when the counts are known, a suffix that says how many placeholders *did*
resolve. That suffix is deliberate: it shows the work that happened even though
the test skipped.

The UI surfaces the same fact before you run anything. In the Test Generator
screen you see:

> ⚠️ Some placeholders were unresolved and were converted into explicit pytest skips.

and the unresolved placeholder tokens are listed underneath.

## Reading the summary

Each package also carries `verification_strength.json`, which records, per test,
how each criterion was verified and why anything was left unresolved. An
unresolved entry names the count and the placeholders, for example:

```text
2 of 3 placeholders unresolved: 'Confirm modal is shown'; 'Cart badge count'
```

It never returns silence - if something was not verified, it says so.

## Why a skip is not a failure

| Outcome | Meaning |
|---|---|
| **Passed** | The step ran and the assertion held. |
| **Skipped** | The step could not be resolved confidently, so it was not run. |
| **Failed** | The step ran and the assertion did not hold. |

A skipped test is honest: the suite tells you which criteria it could not cover
instead of reporting a pass it did not earn. Fix the page or the story wording
and re-run; the resolver tries again.

## Next

- [Evidence and reports](evidence.md)
- [Licensing and tiers](../reference/licensing.md)
