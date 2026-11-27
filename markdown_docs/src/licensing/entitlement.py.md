---
purpose: >
  The licence this deployment runs under: the stored key, its update window, and the
  two decisions built on them - may this build start (cache only), and may this
  upgrade be installed (the store's answer, then the window).
lines: ~230
created: "2026-11-26"
updated: "2026-11-26"
---

# `src/licensing/entitlement.py`

## High-Level Purpose

One source, and it is the cache on this machine. Three moments, no others: activate
once, check at update, read the cache in between.

## The two decisions

| Function | Reads | Refuses when |
|---|---|---|
| `startup_check(build_date, installed_version)` | the cache only - **no network** | the build was released after `window_end` |
| `upgrade_check(build_date, installed_version)` | the store (once), then the cache | the store says the key is dead, or the window has closed |

`upgrade_check` is the **only** place a disabled key surfaces. If the relay cannot be
reached the upgrade proceeds on the cached licence and the message says the check
could not be made - our network never blocks a buyer.

A refusal names the window end and the version that keeps working, and never asks
for money.

## `LicenceState`

`source` (`"activated"` / `"none"`), `tier`, `window_end`, `activation`, `problem`,
`path`.

- `activated_on` - the key's `created_at` date, i.e. the purchase date.
- `allows_build(date)` - `window_end is None or build <= window_end`.

## Where the window comes from

`created_at` + 12 months (`src/licensing/window.py`). The store creates the key
seconds after the order on the same UTC date, so this is the purchase date. A key
created at 23:59 on 31 December gets the next year's 31 December.

## Last-run record

`last_run.json` holds the version that last started inside its window, so a refusal
can name a version that actually works (t-1470).

## Related

- `src/licensing/activation.py` - the calls and the cache.
- `src/licensing/window.py` - the arithmetic and the copy.
- `src/cli/main.py` `_startup_backstop` / `_update_command` - the two callers.
