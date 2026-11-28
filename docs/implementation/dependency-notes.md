# Dependency notes

What a dependency bump changes, written before the bump lands so the reviewer knows
what to look for.

## Playwright 1.65 (the Dependabot PR `python-minor-patch-b642c073e1`)

### The image needs `libatomic1` before `playwright install-deps`

From 1.65 the driver's bundled Node is linked against `libatomic.so.1`. On a bare
`python:3.14-slim` the failure is:

```
/app/.venv/lib/python3.14/site-packages/playwright/driver/node: error while loading
shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
```

**`install-deps` lists `libatomic1` from 1.65 onward, but it cannot install it in time**:
the command starts the bundled Node first, and that Node is what needs the library.
Playwright 1.63's list does not mention it at all (checked with
`playwright install-deps --dry-run chromium` on both versions), so nothing ever pulled
it before. Both images therefore install `libatomic1` explicitly *before*
`install-deps` - `Dockerfile` and `Dockerfile.action`.

Measured on 2026-11-28, `python:3.14.7-slim`:

| playwright | `install-deps --dry-run chromium` | `install-deps chromium` |
|---|---|---|
| 1.63.0 | no `libatomic` | succeeds |
| 1.65.2, bare base | lists `libatomic` | **fails, exit 127** |
| 1.65.2, `libatomic1` installed first | - | succeeds; bundled Node v26.13.1 runs |

### What 1.65 adds

- `locator.normalize()` - turns a locator into Python source code, so a picked element
  can be pasted into a test.
- `page.get_by_ref()` - takes an element the page reports through
  `page.aria_snapshot("ai")` and returns a locator for it: an element picked from the
  accessibility snapshot becomes a test step.
- `cdp_session.send(..., timeout=...)` - a per-call timeout on the CDP session.

### What 1.65 breaks

- **Actions wait for an element to be non-inert before acting.** This is the one to
  watch: a generated test that clicks or fills an element which the page keeps `inert`
  (a disabled form, a modal behind another) now waits and times out where it used to
  act. If a generated test starts timing out after this bump, check for `inert` on an
  ancestor before blaming the locator.
- Cookie matching follows **RFC 6265** - domain and path matching is stricter, so a
  stored cookie may no longer be sent to a path that matched by accident before.
- Proxy credentials are **no longer sent to sites** - an authenticated proxy keeps
  working, but the credentials are not forwarded to the site itself.
