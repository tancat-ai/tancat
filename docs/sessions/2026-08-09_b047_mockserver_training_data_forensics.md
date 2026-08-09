# B-047 Deep-Dive: Training-Data Contamination & RAG Learning Lock Contention

**Date:** 2026-08-09
**Session context:** Fixing B-047 (mock-site `site_hash` collision) escalated into a
forensics investigation of the fine-tuning dataset and the RAG self-learning loop.
This document is the evidence-backed write-up — **self-contained, for feeding back
into the previous session's conversation.**

---

## 1. What was being investigated

The user's question: *"The old rows in the RAG store learned under the old
`hash("localhost")` scheme are now inert — should we re-run the mock cases? The aim
is to train/finetune on this data."*

That question required checking whether the training dataset and RAG store were
actually trustworthy. They were not — for two independent reasons.

---

## 2. Root cause #1 — MockServer class-attribute leak (the real contamination source)

**File:** `scripts/mock_server.py`

`MockServer._start()` set **base-class attributes**:

```python
_RobustRequestHandler.SERVE_DIRECTORY = self.directory   # class attr!
_RouteAwareHandler.ROUTES = routes                       # class attr!
```

When `resolve_and_learn` starts 3 mock servers in one process (root on 8781,
banking on 8782, ecommerce on 8783), each `start()` **overwrites the shared class
attribute**. Handlers read `SERVE_DIRECTORY` at request time, so after all three
start, **every port serves the last-started directory**.

### Empirical proof (run 2026-08-08)

```python
dirs = sorted([root, root/"mock_sites"/"banking", root/"mock_sites"/"ecommerce"])
# start order: root→8781, banking→8782, ecommerce→8783
for p in (8781, 8782, 8783):
    body = GET(f"http://localhost:{p}/index.html")
    # RESULT: ALL THREE ports returned ecommerce HTML ("Stylish Dress" present,
    # banking text absent, identical length 2978)
```

Confirmed: `:8781`, `:8782`, `:8783` **all served the ecommerce directory**.

### Consequences

- Banking stories resolved against **ecommerce DOM** — `#user-name`/`#login-button`
  never found (→ `pytest.skip("unresolved placeholders")`), while ecommerce
  selectors (`#name`, `a[href="/products.html"]`, `main:has-text("Featured Items...
  Stylish Dress...")`, `[data-product-id="1"]`, `p:has-text("Stylish Dress")`) were
  emitted for banking criteria.
- URL assertions still passed (they only check the URL string `localhost:8782`),
  so "banking 18/18 passed" in the previous session was **not evidence of correct
  resolution** — it was testing the wrong site's content.
- Leak appeared in **RAG-off files too** (untagged/ragoff variants), which the
  B-047 site_hash theory could not explain — that is what exposed this bug.

### Fix (committed in `0565271`)

Per-server handler subclass — each server gets its own `SERVE_DIRECTORY`/`ROUTES`:

```python
handler_class = type(
    "MockServerHandler",
    (_RouteAwareHandler if routes else _RobustRequestHandler,),
    {"SERVE_DIRECTORY": self.directory, "ROUTES": routes or {}},
)
self._httpd = _ThreadingServer(("0.0.0.0", self.port), handler_class)
```

Verified: 8781→lv_insurance, 8782→banking, 8783→ecommerce, each serving its own
content. Regression test added: `test_multi_mock_servers_serve_own_directories`.

---

## 3. Root cause #2 — B-047 `site_hash` collision (the documented one)

**File:** `src/rag_learn.py`

`domain_from_url()` stripped the port: `urlparse(url).netloc.split(":")[0]` →
banking:8782 / ecommerce:8783 / lv_insurance:8781 all → `"localhost"` → one hash.
Learned patterns from one mock earned `SAME_SITE_LEARNED_BONUS` on the others.

**Fix (committed in `0565271`):** `domain_from_url()` returns the full `netloc`
(`host[:port]`, lowercase, userinfo stripped). Both learn and resolve paths route
through it, so per-origin scoping is automatic; real sites (no port) unchanged.
Regression tests: `test_concurrent_mocks_scope_independently`,
`test_mock_ports_hash_distinctly`.

**Assessment:** real, correct to fix, but **not** the dominant contamination vector
— the MockServer bug (§2) was.

---

## 4. Training-data contamination (quantified)

`training_data/playwright_resolved_alpaca.jsonl` rows are captured **regardless of
pass/fail** ("the resolution itself is the training signal", `scripts/synthesize_stories.py`
`resolve_and_learn`). Pre-fix scan of the 112 rows:

| Site | Rows | Finding |
|---|---|---|
| banking_mock | 25 | **23/25 contained ecommerce-only selectors** (`products.html`, `Stylish Dress`, `data-product-id`, `#name`…) |
| lv_insurance | 17 | 4 with heavy ecommerce leaks (6–24 markers); the rest skip-heavy garbage (7–8 `pytest.skip` per file) |
| ecommerce_mock | 27 | clean (8783 happened to be the last-started server, so it served the correct content) |
| live sites | 43 | unaffected (distinct domains, never collided) |

### Cleanup performed

1. Purged all 25 banking_mock + 17 lv_insurance rows (backup kept in git history).
2. Re-ran `resolve_and_learn --rag-both` for the 3 mocks with both fixes:
   **52 new site-correct rows appended → 122 total, 0 cross-site leaks** (verified
   by selector-marker scan of every row).
3. New banking rows now resolve `#user-name`/`#password`/`#login-button`, 0 skips
   (previously skip-heavy + leaked). lv rows resolve real lv selectors
   (`#vehicleReg`, `#quoteSubmit`, `#mainLicenseNumber`, `#premiumPrice`).
4. Honest pass rates now: banking 4/18, ecommerce 21/24, lv 2/18 — **lower than the
   previous session's inflated numbers** because tests now run against real content.
5. Purged 26 inert `site_hash=sha256("localhost")` learned patterns from the RAG
   store (they could never match post-fix). Store now: 83 golden + 27 doc + 5 learned
   (4 × `localhost:8782` + 1 × `automationexercise.com`), all correct.

One-off rerun utility committed: `scripts/rerun_mock_resolve_learn.py`.

---

## 5. RAG learning lock contention — the "known follow-up", now evidence-backed

**Claim in the previous session:** "`learn_from_evidence` inside the pytest
subprocess silently no-ops while the parent process holds the Milvus store open
(file-lock contention)."

**This was initially a hypothesis. The user asked for evidence. Controlled
experiments were run — the mechanism is now proven, and one assumption was
corrected.**

### Experiment A — mechanism isolation (`scripts/_lock_ab_holder.py`)

| Setup | Result |
|---|---|
| **CONTROL:** fresh process, subprocess opens store + `learn_from_evidence` | `CHILD OK learn={'inserted': 1, 'exists': 0} found=1` ✅ |
| **EXPERIMENT:** parent opens store (mimics orchestrator retriever), keeps ref, subprocess tries to learn | `CHILD FAILED ConnectionConfigException: Open local milvus failed` — `milvus_lite.exceptions.DataDirLockedError: another process holds the lock on '...evidence/rag_store.db': [Errno 13] Permission denied` ❌ |

### Experiment A2 — does `del` + `gc.collect()` release the lock?

| Setup | Result |
|---|---|
| T0: fresh process, nothing opened | `CHILD: store opened OK, learned: 5` |
| T1: parent opens store → `del store` → `gc.collect()` → subprocess | `CHILD FAILED: ConnectionConfigException: Open local milvus failed` |

**Key finding:** the Milvus-lite lock survives `del` + GC — it is held for the
**parent's entire process lifetime** once opened. Therefore, in a
`resolve_and_learn` run, the first RAG-on pass (orchestrator retriever → retrieve →
opens store) **permanently blocks every subsequent pytest-subprocess hook**, RAG-off
passes included.

### Experiment B — the real pipeline path

- The 3-mock re-run: **27 tests passed, learned count stayed 27** (measured
  before/after via `counts_by_type()`).
- **Self-correction during the experiment:** an initial "control" (parent queries
  counts, `del`, then runs pytest) also showed delta 0 — the control's *own*
  count-query process held the lock. Lesson: any process that touches the store
  blocks subprocess learning.
- Instrumented `generated_tests/conftest.py` (temporary `print` in the hook's
  except/else): single isolated test run → `[LEARN-DIAG] status=passed steps=2
  learn OK` → existing `username` pattern **hit-bumped** (hits 1→2). The hook and
  learning code work; the blocker is purely the lock.

### Experiment C — what happened previously (17→27 growth)

- **Proven:** the 26 `hash("localhost")` patterns existed at session start
  (`Cart link`, `Transfer Money`, `from account`, `to account`, `amount`,
  `transfer success message`, `username`, `account balances`, …) — so learning
  *did* accumulate from localhost mock executions at some point. The `1`
  `automationexercise.com` pattern is also real.
- **Not provable:** which run(s) produced them, or how many pre-dated the last
  session. The patterns were purged before hit counts were recorded, and
  `evidence/rag_store.db` is gitignored (`.gitignore` line 135).
- **Corrected inference:** given the process-lifetime lock, the 17→27 growth most
  plausibly came from **uncontended execution phases** — UAT (`--run`), eval
  `--run`, or `verify_production` — which run pytest with no concurrent
  store-holding parent. The previous session's "grew 17→27 from real executed
  tests" is consistent with this but **not attributable to resolve-and-learn's
  subprocess hooks specifically**.

### Fix candidate (NOT implemented — deferred by user request)

Parent-side sidecar sweep in `scripts/synthesize_stories.py` `resolve_and_learn`:
after each site's executions, the parent reads the on-disk
`evidence/*.evidence.json` sidecars (already written by every test regardless of
learning) and calls `learn_from_evidence` itself — no subprocess, no lock
contention, same dedup/site-scoping. ~30 lines + a test.

---

## 6. What was completed this session (2026-08-08/09)

**Bugs found & fixed:**
- **B-047 port-aware `site_hash`** — `src/rag_learn.py` `domain_from_url()` now returns
  `host[:port]` (userinfo stripped); learn + resolve paths both route through it.
  Real sites (no port) unchanged. Regression tests:
  `test_concurrent_mocks_scope_independently`, `test_mock_ports_hash_distinctly`,
  `test_keeps_port_for_mock_sites`, `test_plain_explicit_port_kept`, `test_strips_userinfo`.
- **MockServer class-attribute leak** — `scripts/mock_server.py` per-server handler
  subclass (own `SERVE_DIRECTORY`/`ROUTES`). Regression test:
  `test_multi_mock_servers_serve_own_directories`.
- **Empirical proof of both** — 3-port server isolation test (pre-fix: all ports served
  ecommerce; post-fix: 8781→lv, 8782→banking, 8783→ecommerce).

**Training-data cleanup & regeneration (the user's original question):**
- Purged 42 contaminated resolved rows (banking_mock 25 + lv_insurance 17) from
  `training_data/playwright_resolved_alpaca.jsonl` (backup preserved in git history).
- Re-ran `resolve_and_learn --rag-both` for the 3 mocks with both fixes
  (~2.5 h background run): **52 new site-correct rows appended → 122 total,
  0 cross-site leaks** (verified by selector-marker scan of every row).
- New banking rows: `#user-name`/`#password`/`#login-button`, 0 skips. lv rows: real
  lv selectors. Honest pass rates (banking 4/18, ecommerce 21/24, lv 2/18) — lower
  than the previous session's inflated numbers because tests now run against real content.
- RAG store: purged 26 inert `sha256("localhost")` learned patterns; added correct
  `localhost:8782` patterns. Final: 83 golden + 27 doc + 5 learned.
- One-off rerun utility committed: `scripts/rerun_mock_resolve_learn.py`.

**Verification gates (all green):**
- `smoke.py` 35/35 · `ruff` clean · `mypy src/ cli/` clean
- Full `pytest`: **2334 passed, 1 skipped**
- `eval_harness.py run --mode static`: **97.9% resolution accuracy** (baseline match)
- Pre-commit: ruff, ruff-format, mypy, Eval Accuracy Gate, Kanban Freshness — all passed
- **CI: 9/9 jobs green on `0565271`** (Smoke, Ruff, MyPy, PyTest+Coverage, Eval Static,
  Kanban, Graph, Docs, Sanitizer)

**Evidence experiments (the RAG lock question):**
- Controlled A/B: subprocess learning works uncontended; fails with
  `DataDirLockedError` while a parent holds the store — and `del` + `gc.collect()`
  do NOT release the process-lifetime lock (§5).
- Instrumented conftest proved the hook works when uncontended (hit-bump 1→2).
- Corrected the 17→27 attribution in BACKLOG (uncontended phases, not resolve-and-learn hooks).

**Deferred (by user request):** the parent-side evidence-sidecar sweep fix
(§5 fix candidate) — documented, not implemented.

## 7. Current repo state

- `0565271` — `fix(rag): port-aware site_hash + MockServer multi-server isolation (B-047)` (code + data cleanup + rerun utility)
- `9865b03` — `docs(backlog): evidence-backed diagnosis of RAG learning lock contention (B-047)`
- `1dcc198` — `docs: B-047 forensics report — training-data contamination + RAG lock contention evidence` (this document)
- CI: 9/9 green on `0565271` (incl. Eval Static 97.9% — baseline match).
- Working tree clean.
- `training_data/playwright_resolved_alpaca.jsonl`: **122 rows, 0 cross-site leaks** — ready for the Unsloth training run.
- RAG store: 83 golden + 27 doc + 5 learned (correct).

## 8. Reproduction cheatsheet (for the follow-up conversation)

```bash
# 1. Prove the MockServer leak (fixed — expect correct isolation):
uv run python -c "
from scripts.mock_server import MockServer; from pathlib import Path
import urllib.request
root = Path('.').resolve()
dirs = sorted([root, root/'mock_sites'/'banking', root/'mock_sites'/'ecommerce'])
servers = [MockServer.start(port=8781+i, directory=str(d)) for i, d in enumerate(dirs)]
import time; time.sleep(0.5)
for p, path in [(8781,'/generated_tests/mock_insurance_site.html'), (8782,'/index.html'), (8783,'/index.html')]:
    body = urllib.request.urlopen(f'http://localhost:{p}{path}', timeout=3).read().decode('utf-8','ignore')
    print(p, 'ecom=', 'Stylish Dress' in body, 'bank=', 'login-button' in body, 'lv=', 'mainLicense' in body)
[s.stop() for s in servers]"

# 2. Prove the learning lock (parent opens store → subprocess fails):
#    (scripts were removed after use; re-create from §5 Experiment A if needed)

# 3. Re-run the 3-mock resolve-and-learn (dataset regeneration):
uv run python scripts/rerun_mock_resolve_learn.py   # ~2-3 h, needs LM Studio for resolution LLM calls
```
