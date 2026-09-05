---
purpose: >
  BYO-LLM health check for Phase 6d: a first-run "check my LLM" probe that tells a customer
  before their first generation whether their endpoint is reachable, the key (if any) is valid,
  the requested model is present, and the model actually returns content. Reuses the product's
  own LLMClient construction path so "what the user configured" and "what the probe checks"
  cannot drift.
lines: ~320
created: "2026-09-05"
---

# `src/llm_health.py`

## High-Level Purpose

The onboarding moment: a customer points TanCat at *their* LLM endpoint and must be told,
before they write a story, whether the endpoint is reachable, the key (if any) is valid, the
requested model is present, and the model actually returns content. A broken endpoint that
silently fails on the first real generation is the worst first impression — this probe surfaces
it up front with an actionable message.

Design constraints (Phase 6 / air-gap): **reuse the product's own provider path**
(`build_client` constructs an `LLMClient` exactly like the UI/CLI), **stdlib + existing deps
only** (no new egress beyond the customer's own endpoint), **cheap** (list_models + one tiny
completion), and **offline-testable** (every check is a pure function of the injected client).

## Public API

### `build_client(provider, base_url=None, model=None, api_key=None, **kwargs) -> LLMClient`
The honest seam: constructs a real `LLMClient` (same `get_provider` + defaults path as the
UI/CLI). The probe checks exactly what the user configured.

### `check_llm(client: LLMCheckable, *, requested_model=None, probe_timeout=20, list_timeout=10, context_floor=None) -> HealthCheckResult`
Runs the full probe ladder and returns a report:
1. **Reachability** — `list_models` (cheap metadata call).
2. **Key validity** — a successful list proves the key is accepted (no key required for locals).
3. **Model availability** — requested model present in the provider's list.
4. **Capability probe** — one minimal sync completion (`_probe_capability`), which doubles as
   the reachability truth (a completed request proves the endpoint is up; a transient list
   failure is cleared). `context_floor` (default: the documented recommendation for the
   provider) only produces a soft warning — it never sets `ok=False`.

### `HealthCheckResult` (dataclass)
Fields: `provider`, `base_url`, `requested_model`, `reachable`, `key_ok`, `model_available`,
`capability_ok`, `elapsed_s`, `available_models`, `sample_output`, `errors`, `warnings`.
- `ok` — True only when every hard check passed (soft warnings never block).
- `headline` — one-line status for a console/UI banner (UNREACHABLE / KEY INVALID /
  MODEL MISSING / BROKEN RESPONSE / OK).

### `render_report(result) -> str`
Identical human-readable report for console/UI/CLI (`✓`/`✗` lines + sample + warnings/errors).

### `min_context_chars(provider, models=RECOMMENDED_MODELS) -> int`
Loose context-window floor (tokens) for the provider's soft size warning; 0 = no floor
(unknown provider skips the check).

### `RECOMMENDED_MODELS` (tuple of `RecommendedModel`)
Documented-but-overridable minimum-model table (lm-studio / ollama / openai-local / openai).

## How It Works (internals)

### `check_llm(client, ...)` — the probe ladder
- `_probe_capability(client, timeout)` — ONE synchronous completion via
  `client._complete_sync(prompt="Reply with the single word: pong", timeout, temperature=0.0,
  enable_thinking=False)`. Thinking-off + temp-0 are deliberate: a thinking model left on
  would burn its token budget on reasoning and return empty content (the AI-050 trap), which
  would read as a false "broken response" for a perfectly good endpoint. Returns the stripped
  content; a non-empty result flips `capability_ok`, proves reachability, and clears any
  earlier "List models failed" error (a completed request is stronger evidence than a list hiccup).

### `LLMCheckable` (Protocol)
The minimal client surface the probe needs: `provider_name` / `base_url` / `model` properties,
`list_models(timeout)`, and `_complete_sync(...)`. Duck-typed so tests inject fakes; the real
`LLMClient` satisfies it structurally (same pattern as the ranker's `AsyncGeneratorLike`).