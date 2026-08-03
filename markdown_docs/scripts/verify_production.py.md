# `scripts/verify_production.py` — Production Verification

## Purpose
End-to-end product verification: runs the full generation → resolution → execution → evidence pipeline against known demo sites and emits a PASS/FAIL verdict via gate checks. The single source of truth for "does the product work?" (AGENTS.md §12).

## Usage
```bash
python scripts/verify_production.py saucedemo          # one site
python scripts/verify_production.py --all-sites        # saucedemo + automationexercise
python scripts/verify_production.py --flat             # flat mode (default is POM)
```

## Sites
| site | URL | Story |
|------|-----|-------|
| `saucedemo` | https://www.saucedemo.com | login → add to cart → checkout (5+ tests) |
| `automationexercise` | https://automationexercise.com | browse → add to cart → checkout (5+ tests) |

## Gates (13 per site)
LLM connected → Pipeline generation → No unresolved placeholders → Test function count → Evidence tracker calls → `@pytest.mark.evidence` decorators → POM imports → Pipeline unresolved → Execution (runs the generated tests) → Evidence JSON → Evidence steps → (verdict).

## Key Logic
- **Credentials (2026-08-03):** saucedemo gets a `CredentialProfile` (env-overridable `SAUCEDEMO_USERNAME`/`SAUCEDEMO_PASSWORD`, default `standard_user`/`secret_sauce`, matching `scripts/eval/eval_resolver.py`) passed to `TestOrchestrator` — without it the stateful scraper captures the login wall, not the cart
- LLM provider from `LLM_PROVIDER` env (defaults to the `.env` openai-local config); avoids auto-detect which can pick the wrong provider when LM Studio is shared
- Generates tests to `generated_tests/verify_<site>_<timestamp>/`, executes with a generated conftest (evidence tracker fixture), and validates evidence JSON + step counts
- Failed runs are kept on disk for debugging (`[KEPT]`)

## Related
- `src/orchestrator.py` — `TestOrchestrator.run_pipeline()`
- `src/llm_client.py` — LLM client
- `scripts/eval/eval_harness.py` — static resolution accuracy (pre-commit quality gate)
