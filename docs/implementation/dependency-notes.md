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

**The difference is whether the bundled Node LINKS libatomic, not whether
`install-deps` lists it.** At 1.63.0 the driver's Node has no atomic dependency and
starts on a bare base; at 1.65.2 it does, so it cannot start:

```
$ ldd .../playwright/driver/node        # 1.63.0: no libatomic line
$ ldd .../playwright/driver/node        # 1.65.2: libatomic.so.1 => not found
```

**Both versions list `libatomic1`** in `install-deps --dry-run chromium` once apt is
updated and the library is present, and a 1.63 image with the stanza removed still
ends up with `libatomic1` installed by its own `install-deps`. The listing is therefore
not the cause and not the fix.

**The ordering is what matters.** `install-deps` starts the bundled Node before it
installs anything, so at 1.65.2 on a base without the library the command exits 127
having installed nothing - it can never reach the package that would let its own Node
run. Both images install `libatomic1` explicitly *before* `install-deps` -
`Dockerfile` and `Dockerfile.action`.

Measured on 2026-11-28, `python:3.14.7-slim` (linkage checked with `ldd` on the
driver's `node`; the reviewer reproduced both rows independently):

| playwright | bundled Node links `libatomic` | `install-deps chromium` |
|---|---|---|
| 1.63.0 | no | succeeds (`libatomic1` is in its list either way) |
| 1.65.2, bare base | yes - `=> not found` | **fails, exit 127**, nothing installed |
| 1.65.2, `libatomic1` installed first | yes - resolved | succeeds; bundled Node v26.13.1 runs |

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
