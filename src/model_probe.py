"""Ask the configured endpoint what models it serves, without ever blocking the page.

A fresh install has no LLM running. Constructing an `LLMClient` in that state is not
free: on Windows it resolves localhost for each candidate port, and the client also
asks the endpoint for its loaded model twice before the sidebar even draws. Measured
on a machine with no server (2026-11-26):

    auto_detect_provider()                    10.6 s
    get_provider("openai-local", base_url="") 12.1 s   (_detect_local_url, 3 ports)
    get_loaded_model()                         4.0 s
    list_models()                              4.1 s

Streamlit runs the script top to bottom on every interaction, so that ~24 s landed
before the licence panel and the run controls, and the browser showed a half-drawn
page with Streamlit's Stop button still spinning (t-1509).

This module puts a **hard deadline** on the whole probe: it runs in a daemon thread
and the caller gets an answer (models, or "no answer within the budget") on time. The
thread is abandoned if it overruns - the request it made is bounded by its own
timeout, so it ends by itself.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

__all__ = [
    "PROBE_BUDGET_SECONDS",
    "ProbeResult",
    "probe_models",
]

#: The whole probe may take this long, including client construction. A page must
#: draw inside five seconds (t-1509), and this leaves room for the rest of the render.
PROBE_BUDGET_SECONDS = 1.5


@dataclass(frozen=True)
class ProbeResult:
    """What the probe found, and whether it finished in time."""

    models: list[str] = field(default_factory=list)
    finished: bool = True
    elapsed: float = 0.0
    error: str = ""

    @property
    def reachable(self) -> bool:
        return bool(self.models)

    def message(self, endpoint: str) -> str:
        """The sentence the sidebar shows. Empty when models were found."""
        if self.models:
            return ""
        where = endpoint or "the configured endpoint"
        if not self.finished:
            return (
                f"No answer from {where} within {PROBE_BUDGET_SECONDS:.1f}s - no model is configured yet. "
                "Start your LLM server and reload, or set Provider Base URL to the server you use."
            )
        if self.error:
            return (
                f"No model is configured yet: {where} did not answer ({self.error}). "
                "Start your LLM server and reload, or set Provider Base URL to the server you use."
            )
        return (
            f"No model is configured yet: {where} answered but listed none. "
            "Load a model there, or set Provider Base URL to the server you use."
        )


def probe_models(
    provider: str,
    base_url: str,
    *,
    budget: float = PROBE_BUDGET_SECONDS,
) -> ProbeResult:
    """List the models *provider* serves, giving up after *budget* seconds.

    The probe runs off the caller's thread, so a slow or dead endpoint cannot hold
    the page. A probe that overruns is reported as unfinished rather than waited for.
    """
    found: list[str] = []
    failure: list[str] = []

    def _work() -> None:
        try:
            from src.llm_client import LLMClient

            client = LLMClient(provider=provider, base_url=base_url)
            found.extend(str(model) for model in client.list_models(timeout=max(1, int(budget))))
        except Exception as exc:  # the endpoint is down, or the provider refused
            failure.append(f"{type(exc).__name__}: {exc}"[:160])

    started = time.perf_counter()
    worker = threading.Thread(target=_work, name="tancat-model-probe", daemon=True)
    worker.start()
    worker.join(budget)
    elapsed = time.perf_counter() - started
    if worker.is_alive():
        return ProbeResult(models=[], finished=False, elapsed=elapsed, error="")
    return ProbeResult(models=found, finished=True, elapsed=elapsed, error=failure[0] if failure else "")
