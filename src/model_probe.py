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
    "keep_previous_models",
    "probe_models",
]

#: The whole probe may take this long, including client construction. A page must
#: draw inside five seconds (t-1509), and this leaves room for the rest of the render.
#:
#: A probe that overruns is NOT a verdict: llama.cpp's first ``/v1/models`` answer took
#: about 7s for the owner (t-0715), and a slow local model must never be reported as
#: "no model" (t-1514). An unfinished probe says "still checking" and keeps the models
#: it already had. 0.8s is chosen against the page budget: Streamlit's own boot costs
#: ~3.5s on the owner's machine, and the whole page must draw inside 5s (t-1509).
PROBE_BUDGET_SECONDS = 0.8


@dataclass(frozen=True)
class ProbeResult:
    """What the probe found, and whether it finished in time."""

    models: list[str] = field(default_factory=list)
    finished: bool = True
    elapsed: float = 0.0
    error: str = ""
    budget: float = PROBE_BUDGET_SECONDS

    @property
    def reachable(self) -> bool:
        return bool(self.models)

    def message(self, endpoint: str) -> str:
        """The sentence the sidebar shows. Empty when models were found.

        An unfinished probe is **not** a verdict: a slow model answers after the
        deadline, and telling that buyer they have no model is the t-0715 mistake
        (t-1514). Only a probe that finished may say "no model is configured yet".
        """
        if self.models:
            return ""
        where = endpoint or "the configured endpoint"
        if not self.finished:
            return (
                f"Still checking {where} - the page works meanwhile, and a model that is still "
                f"loading will be picked up on the next reload (the check stopped after {self.budget:.1f}s)."
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
        client = None
        try:
            from src.llm_client import LLMClient

            client = LLMClient(provider=provider, base_url=base_url)
            found.extend(str(model) for model in client.list_models(timeout=max(1, int(budget))))
        except Exception as exc:  # the endpoint is down, or the provider refused
            failure.append(f"{type(exc).__name__}: {exc}"[:160])
        finally:
            # The client owns an httpx pool; an abandoned probe thread must not leave it
            # open (t-1514).
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover
                    pass

    started = time.perf_counter()
    worker = threading.Thread(target=_work, name="tancat-model-probe", daemon=True)
    worker.start()
    worker.join(budget)
    elapsed = time.perf_counter() - started
    if worker.is_alive():
        return ProbeResult(models=[], finished=False, elapsed=elapsed, error="", budget=budget)
    return ProbeResult(models=found, finished=True, elapsed=elapsed, error=failure[0] if failure else "", budget=budget)


def keep_previous_models(result: ProbeResult, previous: ProbeResult | None) -> ProbeResult:
    """Keep the models a previous probe found when this one ran out of time.

    An unfinished probe has no verdict to give, so replacing a known-good list with an
    empty one would turn a slow model into "no model" (t-1514).
    """
    if result.finished or previous is None or not previous.models:
        return result
    from dataclasses import replace

    return replace(result, models=list(previous.models))
