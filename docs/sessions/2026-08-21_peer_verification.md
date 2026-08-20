# Session — 2026-08-21 — Peer Verification & Benchmark Evidence Versioning

This session documents the peer-verification of a prior agent's ("Pi Agent")
decision-making failures around `generated_tests/` and benchmark artifacts, and
the subsequent versioning of those artifacts. All facts below were verified
against live `git ls-tree`, `git log --all`, `git check-ignore -v`, and
`ls -la` output.

## Context

Prior agent initialization: user = 'L_A_C', focus = 'A/B test cleanup', warnings
= "I have been deviating from standard procedures in file management —
particularly with deleting generated_tests and benchmark artifacts".

The prior agent's own log recorded these decision failures:

1. Asserted non-existent Git status from the root directory, misdiagnosing
   repository state.
2. Incorrectly declared independent folders nonexistent (`compare/`, `configs/`).
3. Requested deletion of critical test artifacts in `generated_tests/` without
   verifying commit status.
4. Falsified a session-log example with improper quote syntax (`\n` instead of
   proper newlines).

Its stated recommendations were: halt all destructive operations, run a full
recovery audit of `generated_tests/test_*`, re-verify `.gitignore` rules, and
add `--checksum` verification to file operations.

---

## 1 — Peer verification of the prior agent's claims

### 1.1 Git status misinspection — REPRODUCED and CORRECTED
The repo `AI-Playwright-Test-Generator` is a valid git repo, branch `main`,
HEAD `b22b086a83ec0b5092d407701b0261da4957e02a`. The prior misinspection ran
`git status` from `/c/Users/l_a_c/code` (a parent directory). Verified: 8 files
modified, 7 untracked `test_*.py` in `generated_tests/`, none deleted or staged.

### 1.2 False "vanishing" claim for `compare/` / `configs/` — not true
`llm-benchmarks/` is NOT inside this repo; it is the sibling directory
`/c/Users/l_a_c/code/llm-benchmarks/`. Both folders exist there:
- `configs/` → `gemma-4-31b.yaml`, `qwen36-27b-eval.yaml`,
  `qwen38-27b-eval.yaml`, `qwen38-27b-pi.yaml`, `qwen38-27b-q6.yaml`
- `compare/` → `compare.html`
- Plus 28 `bench_*.json` evidence files.

Nothing was lost and nothing needed rebuilding. The alleged
"gemma4-31b-baseline" JSONs are actually named
`bench_gemma4-31b-baseline_20260608_114632.json` etc. This claim was false —
those folders never vanished.

### 1.3 The `rm -rf generated_tests/` suggestion was correctly blocked
Audit confirmed:
- TRACKED (committed, must survive any cleanup): `generated_tests/conftest.py`,
  `generated_tests/mock_insurance_site.html`
- UNTRACKED + UNIGNORED (deletion = data loss, no git history):
  `test_automationexercise.py`, `test_banking_mock.py`, `test_demoqa.py`,
  `test_ecommerce_mock.py`, `test_lv_insurance.py`, `test_saucedemo.py`,
  `test_theinternet.py`
- IGNORED correctly: `generated_tests/evidence/`, `resolved/`, `verify_*`,
  `test_*/` packages, `test_report_*`.

The recovery audit script was created at `scripts/audit_generated_tests.sh`
(scripts live in `scripts/`, not `src/scripts/` per AGENTS.md). It prints the
git-depth check, `.gitignore` classification, sha256 evidence snapshot, and the
list of protected tracked files. Exit code 2 if untracked-unignored artifacts
exist (current verdict: DANGER, count 7 — informational only; no deletion was
executed).

**Bottom line: do NOT delete untracked `generated_tests/test_*.py` without first
preserving them (e.g. `git add -f` / commit / copy to evidence/). They are not
in git history and are not recoverable.**

---

## 2 — `llm-benchmarks/` now has its own git repo

Per user decision, `/c/Users/l_a_c/code/llm-benchmarks/` was initialized as a
standalone git repository (`git init -b main`), replacing its prior "completely
unversioned" state (confirmed: `fatal: not a git repository`).

- Commit `47eea56` — "chore: capture benchmark evidence under version control"
- 54 files tracked: `bench_*.json` (incl. Model A / Qwen3.6-27B baseline and
  Model B runs), `configs/*.yaml`, `compare/compare.html`, `evidence/` (A/B eval
  logs, manifests, lmeval gsm8k results), `llmctl.py`, `bench_new_model.sh`,
  `README.md`
- Payload ~3.5 MB (working dir was 29 MB)
- Excluded via `.gitignore` (regenerable runtime noise): top-level `*.log`
  (incl. ~25 MB `server_*.log`), `*.pid`, `__pycache__/`, `llmctl.db` (rebuild
  with `python llmctl.py init`)
- Remote configured & pushed (verified live): `https://github.com/lacattano/llm-benchmarks`
  — PRIVATE repo, `main` tracks `origin/main`, 54 files confirmed via
  `gh api repos/lacattano/llm-benchmarks/contents`.
---

## 3 — A/B analysis fully versioned (closed all untracked gaps)

Concern: "days of analysis of different weights/configs/RAG/MTP — don't want to
lose it." Audit found 13 untracked analysis files at risk.

- **Main repo commit `ce58b5c`** — "docs(benchmark): version-control A/B model
  analysis" — 13 files, 1,766 lines: `docs/benchmarks/README.md` (production
  config, precision table), 2 A/B session docs (08-19 thinking_on_ab,
  08-20 retest_handover), `scratch/` analysis (gguf confound, lmeval gsm8k,
  model_ab_all_conditions, thinkingon results) and all 8 leg manifests
  (incl. `manifest_K_38v2_mtpon.json` = K leg, the new 5.21bpw v2 weights/MTP).
  Pre-commit hook ran the eval harness (97.9%) — passed.
- **Benchmark repo commit `e720a71`** — "feat(evidence): add K-leg manifest +
  analysis docs" → added the missing `manifest_K_38v2_mtpon.json` to `evidence/`
  plus a new `analysis/` folder (prod config + 2 session docs). Verified on
  GitHub via API.

Now-redundant coverage: main-repo git AND the llm-benchmarks GitHub repo
(`github.com/lacattano/llm-benchmarks`, private). Nothing analysis-related
remains untracked. The `.gguf` weight files stay local-only (binary, by design).

---

## Outstanding items (not part of this session)

- Commit the 7 `generated_tests/test_*.py` files into the main repo (option 2
  of the versioning plan) — still open.
- Archive the 5.3 GB `generated_tests/` evidence into release tarballs (option
  3) — still open. They are intentionally gitignored (PNG-heavy, exceed GitHub
  size limits).