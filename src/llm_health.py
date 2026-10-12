"""Phase 6d — BYO-LLM health check ("check my LLM" first-run probe).

The onboarding moment: a customer points TanCat at *their* LLM endpoint and
must be told, before they write a story, whether the endpoint is reachable,
the key (if any) is valid, the requested model is present, and the model
actually returns content. A broken endpoint that silently fails on the first
real generation is the worst first impression — this probe surfaces it up front
with an actionable message.

Design constraints (Phase 6 / air-gap):
- **Reuse the product's own provider path.** The probe constructs an
  :class:`src.llm_client.LLMClient` exactly the way the UI/CLI do, so "what the
  user configured" and "what the probe checks" can't drift.
- **Stdlib + existing deps only.** No new dependency, no egress beyond the
  customer's own endpoint (the no-egress wedge is preserved — the probe calls
  only the configured provider).
- **Cheap.** Listing models is a single metadata call; the capability probe is
  one tiny completion (a few tokens) so it never burns a token budget.
- **Offline-testable.** Every check is a pure function of the client it is
  handed, so tests inject a fake ``LLMClient`` and assert the report — no
  network, no LLM, CI-able.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from src.provider_config import LOCAL_MODEL_LIST_TIMEOUT, provider_requires_openai_api_key

if TYPE_CHECKING:
    from src.llm_client import LLMClient


class LLMCheckable(Protocol):
    """The minimal client surface the health probe needs.

    Duck-typed so tests can inject fakes; the real ``LLMClient`` satisfies it
    structurally (same pattern as the ranker's ``AsyncGeneratorLike``).
    """

    @property
    def provider_name(self) -> str: ...

    @property
    def base_url(self) -> str: ...

    @property
    def model(self) -> str: ...

    def list_models(self, timeout: int = 30) -> list[str]: ...

    def _complete_sync(self, prompt: str, *, timeout: int, temperature: float, enable_thinking: bool | None) -> Any: ...


__all__ = [
    "HealthCheckResult",
    "RecommendedModel",
    "RECOMMENDED_MODELS",
    "check_llm",
    "build_client",
    "render_report",
    "min_context_chars",
]


@dataclass
class RecommendedModel:
    """A documented minimum-model recommendation for a provider.

    ``min_context`` is a *loose* floor (in tokens) — a model below it will
    under-perform on skeleton generation; the probe only warns, it never blocks
    on the heuristic (the hard gate is reachability + key + non-empty content).
    """

    provider: str
    model: str
    min_context: int = 8192
    note: str = ""


# Documented but overridable — the customer's own model always wins. These are
# the "this is what we test against" defaults surfaced alongside the probe.
RECOMMENDED_MODELS: tuple[RecommendedModel, ...] = (
    RecommendedModel(
        provider="lm-studio",
        model="Qwen/Qwen2.5-14B-Instruct",
        min_context=32768,
        note="Balanced local default for skeleton generation + resolution.",
    ),
    RecommendedModel(
        provider="ollama",
        model="qwen2.5:14b-instruct",
        min_context=32768,
        note="Balanced local default for skeleton generation + resolution.",
    ),
    RecommendedModel(
        provider="openai-local",
        model="Qwen/Qwen2.5-14B-Instruct",
        min_context=32768,
        note="OpenAI-compatible local server (llama.cpp / vLLM).",
    ),
    RecommendedModel(
        provider="openai",
        model="gpt-4o",
        min_context=128000,
        note="Cloud reference; any recent instruct model works.",
    ),
    RecommendedModel(
        provider="azure-openai",
        model="gpt-4o",
        min_context=128000,
        note="Azure OpenAI deployment name; any recent instruct model works.",
    ),
)


def min_context_chars(provider: str, models: tuple[RecommendedModel, ...] = RECOMMENDED_MODELS) -> int:
    """Loose context-window floor (tokens) recommended for *provider*.

    Returns 0 when the provider has no documented recommendation (no floor to
    warn about) — the probe then skips the size check for that provider.
    """
    for m in models:
        if m.provider == provider:
            return m.min_context
    return 0


@dataclass
class HealthCheckResult:
    """Outcome of the BYO-LLM probe.

    ``ok`` is True only when *every* hard check passed: reachable + (key valid
    if required) + model available (if listable) + the capability probe returned
    non-empty content. Soft/heuristic signals (context-window floor) never set
    ``ok`` to False — they surface in ``warnings``.
    """

    provider: str
    base_url: str
    requested_model: str
    reachable: bool
    key_ok: bool  # True unless a keyed call was rejected (or no key is present)
    model_available: bool  # True when no model list is available to check
    capability_ok: bool
    key_required: bool = False  # True for keyed cloud providers
    key_verified: bool = False  # True once a keyed call completed successfully
    elapsed_s: float = 0.0
    available_models: list[str] = field(default_factory=list)
    sample_output: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reachable and self.key_ok and self.model_available and self.capability_ok

    @property
    def headline(self) -> str:
        """One-line status for a console / UI banner."""
        if self.ok:
            return f"LLM OK — {self.provider} / {self.requested_model} is reachable and responsive."
        if not self.reachable:
            return f"LLM UNREACHABLE — could not reach {self.provider} at {self.base_url}."
        if not self.key_ok:
            return f"LLM KEY INVALID — {self.provider} rejected the configured API key."
        if not self.model_available:
            return f"MODEL MISSING — '{self.requested_model}' is not listed on {self.provider}."
        return f"LLM BROKEN RESPONSE — {self.provider} / {self.requested_model} returned no usable content."


def build_client(
    provider: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> LLMClient:
    """Construct an :class:`LLMClient` the same way the UI/CLI do.

    This is the seam that keeps the probe honest: it uses the product's own
    construction path (``get_provider`` + defaults) rather than a parallel one.
    """
    from src.llm_client import LLMClient

    return LLMClient(provider=provider, model=model, base_url=base_url, api_key=api_key, **kwargs)


# Names the app or a user may store to mean "whatever the local server loaded".
# llama.cpp ignores the model field on a request and serves the loaded GGUF, so
# the app's openai-local default ("llama") is valid even though /v1/models
# advertises the GGUF path. See t-0715.
_LOCAL_MODEL_ALIASES: frozenset[str] = frozenset({"llama", "local", "local-model", "local_model", "default", "model"})


def _model_key(name: str) -> str:
    """Normalise a model name or path for comparison.

    Lower-cases, treats backslashes as separators, drops directories and strips
    a known model file extension, so
    ``C:\\models\\Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`` becomes
    ``qwen3.8-27b-ud-q4_k_xl_v2``.
    """
    key = name.strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".gguf", ".bin", ".safetensors", ".pt"):
        if key.endswith(ext):
            return key[: -len(ext)]
    return key


def _model_matches(requested: str, available: list[str], *, provider: str = "") -> bool:
    """True when *requested* names a model in *available* (exact, alias or substring).

    A stored name rarely equals the advertised id: a local server advertises the
    GGUF path (``C:\\...\\Qwen3.8-27B-UD-Q4_K_XL_v2.gguf``) while the app stores
    a short default such as ``llama``. The match accepts, in order: an exact
    case-insensitive name; a matching file stem (path and extension ignored); a
    substring either way; and a generic local alias when the endpoint is
    llama.cpp (``openai-local``, which ignores the model field) or advertises a
    single model.
    """
    requested_clean = requested.strip()
    if not requested_clean:
        return True
    if not available:
        return False

    requested_lower = requested_clean.lower()
    keys = [_model_key(m) for m in available if m.strip()]
    if requested_lower in keys:
        return True

    requested_key = _model_key(requested_clean)
    for key in keys:
        if not key or not requested_key:
            continue
        # A substring must be long enough to be a name, not a stray letter
        # (a single-letter key would otherwise match any name containing it).
        if min(len(requested_key), len(key)) >= 4 and (requested_key in key or key in requested_key):
            return True

    return requested_lower in _LOCAL_MODEL_ALIASES and (provider == "openai-local" or len(keys) == 1)


def _is_auth_error(exc: BaseException) -> bool:
    """True when *exc* looks like an HTTP 401/403 auth rejection.

    Checks the httpx response status first (the reliable signal), then falls
    back to the message for providers that wrap the error.
    """
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) in (401, 403):
        return True
    text = str(exc).lower()
    return any(token in text for token in ("401", "403", "unauthorized", "invalid api key", "incorrect api key"))


def _probe_capability(client: LLMCheckable, timeout: int) -> str:
    """One minimal synchronous completion; returns the (stripped) content.

    Uses the provider's sync completion path directly (not the async
    ``generate``) so the probe is a single cheap call. ``enable_thinking=False``
    is passed deliberately: thinking models would otherwise burn their token
    budget on reasoning and return empty content (AI-050), which would read as
    a false "broken response" for a perfectly good endpoint.
    """
    completion = client._complete_sync(  # noqa: SLF001 — deliberate, the sync probe path
        prompt="Reply with the single word: pong",
        timeout=timeout,
        temperature=0.0,
        enable_thinking=False,
    )
    return (completion.content or "").strip()


def check_llm(
    client: LLMCheckable,
    *,
    requested_model: str | None = None,
    probe_timeout: int = 20,
    list_timeout: int = LOCAL_MODEL_LIST_TIMEOUT,
    context_floor: int | None = None,
) -> HealthCheckResult:
    """Run the BYO-LLM health checks against *client* and return a report.

    *requested_model* defaults to the client's configured model. *context_floor*
    is an optional token floor for the soft size warning; pass ``None`` to use
    the documented recommendation for the client's provider, or ``0`` to skip
    the size check entirely.
    """
    provider = client.provider_name
    base_url = getattr(client, "base_url", "") or ""
    model = requested_model or getattr(client, "model", None) or ""
    if context_floor is None:
        context_floor = min_context_chars(provider)

    key_required = provider_requires_openai_api_key(provider)

    result = HealthCheckResult(
        provider=provider,
        base_url=base_url,
        requested_model=model,
        reachable=False,
        key_required=key_required,
        # key_ok means "no evidence of a key problem" — it is cleared to False
        # only by an auth-shaped rejection. key_verified records positive proof
        # (a keyed call that completed), so the report never prints "ok" on a
        # probe that never got as far as the key.
        key_ok=True,
        model_available=True,
        capability_ok=False,
    )
    t0 = time.monotonic()

    # 1. Reachability — listing models is a cheap metadata call. A failure here
    #    means the endpoint is unreachable OR (for keyed cloud providers) the
    #    key is rejected. We can't always tell which from the list call alone,
    #    so the capability probe below disambiguates (and an auth-shaped
    #    exception flags a key rejection directly).
    try:
        models = client.list_models(timeout=list_timeout)
        result.available_models = list(models)
        result.reachable = True
        if key_required:
            # A successful keyed call proves the key is accepted.
            result.key_ok = True
            result.key_verified = True
    except Exception as exc:  # noqa: BLE001 — any provider error is an actionable report line
        if key_required and _is_auth_error(exc):
            result.key_ok = False
            result.errors.append(f"List models rejected the API key: {exc}")
        else:
            result.errors.append(f"List models failed: {exc}")
        result.errors.append("  → Check the base URL, that the server is running, and (for cloud) the API key.")
        # Reachability is unknown from the list call alone; let the probe decide.
        result.reachable = False

    # 2. Key validity — set by the list call above: a successful keyed call
    #    proves the key, an auth rejection clears it. A keyless provider needs
    #    no key, so key_ok stays True.

    # 3. Model availability — only meaningful when we got a model list.
    #    The stored name may be a short alias ("llama") or a prefix rather than
    #    the advertised GGUF path, so match on alias/stem/substring (t-0715).
    if result.available_models and model:
        if not _model_matches(model, result.available_models, provider=provider):
            result.model_available = False
            result.errors.append(
                f"Model '{model}' is not in the {len(result.available_models)} models listed. "
                f"Available: {', '.join(result.available_models[:10])}"
            )

    # 4. Capability probe — one tiny completion. Distinguishes a reachable-but-
    #    wrong-endpoint / wrong-model / empty-response failure from a truly
    #    unreachable one, and confirms the model returns content.
    try:
        sample = _probe_capability(client, probe_timeout)
        result.reachable = True  # a completed request proves the endpoint is up
        if key_required:
            result.key_ok = True  # a completed request proves the key is accepted
            result.key_verified = True
        if sample:
            result.capability_ok = True
            result.sample_output = sample[:120]
            # The probe succeeded — any earlier list failure was transient or a
            # non-fatal listing quirk; the endpoint is demonstrably usable.
            result.errors = [
                e for e in result.errors if "List models failed" not in e and "rejected the API key" not in e
            ]
        else:
            result.errors.append(
                "Capability probe returned empty content — the model may be a thinking model "
                "misconfigured, or the endpoint returned an error body. "
                "(Probe sends enable_thinking=False; a genuine thinking-only endpoint may need "
                "a different model or config.)"
            )
    except Exception as exc:  # noqa: BLE001
        # Distinguish connection failures (unreachable) from auth rejections
        # and other errors.
        if key_required and _is_auth_error(exc):
            result.key_ok = False
            result.reachable = True  # the endpoint answered — it just refused the key
            result.errors.append(f"Capability probe rejected the API key: {exc}")
        elif isinstance(exc, (ConnectionError, TimeoutError)) or "connect" in str(exc).lower():
            result.reachable = False
            result.errors.append(f"Capability probe could not connect to {base_url}: {exc}")
        else:
            result.errors.append(f"Capability probe failed: {exc}")

    result.elapsed_s = round(time.monotonic() - t0, 3)

    # 5. Soft size warning — never blocks, just informs.
    if context_floor and context_floor > 0 and result.capability_ok:
        result.warnings.append(
            f"Note: we recommend a model with at least ~{context_floor} context tokens for "
            f"reliable skeleton generation. If '{model}' is smaller, results may degrade."
        )

    return result


def render_report(result: HealthCheckResult) -> str:
    """Render a human-readable probe report (console / UI / CLI identical)."""
    mark = "✓" if result.ok else "✗"
    if not result.key_ok:
        key_line = "INVALID"
    elif not result.key_required:
        key_line = "ok (no key required)"
    elif result.key_verified:
        key_line = "ok"
    else:
        key_line = "unverified (no keyed call completed)"
    lines = [
        f"{mark} {result.headline}",
        f"    provider : {result.provider}",
        f"    base_url : {result.base_url or '(default)'}",
        f"    model    : {result.requested_model or '(provider default)'}",
        f"    reachable: {'yes' if result.reachable else 'no'}",
        f"    key      : {key_line}",
        f"    model    : {'listed' if result.model_available else 'NOT in list'}"
        + (f"  ({len(result.available_models)} available)" if result.available_models else ""),
        f"    responds : {'yes' if result.capability_ok else 'no'}",
        f"    elapsed  : {result.elapsed_s}s",
    ]
    if result.sample_output:
        lines.append(f"    sample   : {result.sample_output!r}")
    for w in result.warnings:
        lines.append(f"    ⚠ {w}")
    for e in result.errors:
        lines.append(f"    ✗ {e}")
    return "\n".join(lines)
