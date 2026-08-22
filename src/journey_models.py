"""Data models for journey-aware scraping.

This module contains pure dataclasses and utility functions used across
the journey scraping pipeline. Keeping models separate from execution
logic allows lightweight imports (e.g., CLI sessions, UI pipelines)
without pulling in Playwright or subprocess machinery.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class JourneyStep:
    """A single action in the scraping journey.

    Attributes:
        action: The action type: "navigate", "click", "fill", "wait", "scrape".
        url: URL to navigate to (for "navigate" action).
        selector: Element selector to interact with (for "click"/"fill" actions).
        text: Text to fill into an input (for "fill" action).
        description: Human-readable description of this step.
        timeout_ms: Custom timeout for this step (default: 30000).
    """

    action: str
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    description: str = ""
    timeout_ms: int = 30_000


@dataclass
class ScrapedStep:
    """Result of scraping at a specific journey step.

    Attributes:
        url: The URL that was scraped.
        elements: The scraped elements at this URL.
        step_index: Which step in the journey this corresponds to.
        step_description: Human-readable description of the journey step.
    """

    url: str
    elements: list[dict[str, Any]]
    step_index: int
    step_description: str = ""


@dataclass
class CredentialProfile:
    """User-defined credentials for authenticated journey scraping.

    Stored in session state only — never persisted to disk.
    """

    label: str
    username: str
    password: str


@dataclass
class ObservedStep:
    """One observed transition in a journey (AI-052).

    A factual record of where the browser actually was at each step —
    captured from ``page.url``, never inferred. The resolver consumes these
    observations instead of re-guessing next-page URLs.

    Attributes:
        index: Zero-based step index within the journey.
        action: The step action ("navigate", "click", "fill", "wait", "scrape", "capture").
        description: Human-readable description of the step.
        selector_used: The selector actually clicked/filled ("" when discovered
            text or none at all).
        from_url: URL before the step ran ("" before the starting page).
        to_url: URL after the step ran ("" when the step raised before a URL
            could be observed).
        navigated: True when the step changed ``page.url`` relative to
            ``from_url``. For the very first step ``from_url`` is "" (the
            browser had no URL yet) so ``navigated`` is always False there;
            consumers should use ``from_url != to_url`` directly for step 0.
        scraped: True when the step caused the destination page to be scraped
            (``output`` gained a key for ``to_url``).
        error: Exception message when the step failed after all retries.
    """

    index: int
    action: str
    description: str = ""
    selector_used: str = ""
    from_url: str = ""
    to_url: str = ""
    navigated: bool = False
    scraped: bool = False
    error: str | None = None


@dataclass
class ObservedTrail:
    """Ordered, per-journey record of observed page transitions (AI-052).

    Observation, not inference: every URL here was read from the live browser
    after the step ran. The resolver (Sessions 3-4) consumes this trail to
    scope resolution to pages that were actually reached.

    Attributes:
        steps: One :class:`ObservedStep` per journey step, in order.
    """

    steps: list[ObservedStep] = field(default_factory=list)

    @property
    def pages_visited(self) -> list[str]:
        """Ordered, deduped list of observed URLs."""
        urls: list[str] = []
        for step in self.steps:
            for url in (step.to_url,):
                if url and url not in urls:
                    urls.append(url)
        return urls

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return {"steps": [asdict(s) for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservedTrail:
        """Deserialize from a plain dictionary."""
        steps = [ObservedStep(**s) for s in data.get("steps", []) if isinstance(s, dict)]
        return cls(steps=steps)


@dataclass
class JourneyResult:
    """Result of executing a journey through authenticated pages."""

    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]  # url -> elements
    failed_steps: list[str]  # human-readable descriptions
    error_message: str | None = None  # top-level error (SSO, MFA, CAPTCHA)
    redirected_urls: list[str] = field(default_factory=list)
    trail: ObservedTrail | None = None  # observed transition trail (AI-052)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JourneyResult:
        """Deserialize from a plain dictionary."""
        trail_data = data.get("trail")
        return cls(
            success=bool(data.get("success", False)),
            captured_pages=data.get("captured_pages", {}),
            failed_steps=data.get("failed_steps", []),
            error_message=data.get("error_message"),
            redirected_urls=data.get("redirected_urls", []),
            trail=ObservedTrail.from_dict(trail_data) if isinstance(trail_data, dict) else None,
        )


def substitute_templates(text: str, credential_profile: CredentialProfile | None) -> str:
    """Replace {{username}} and {{password}} placeholders with credential values."""
    if credential_profile is None:
        return text
    result = text.replace("{{username}}", credential_profile.username)
    result = result.replace("{{password}}", credential_profile.password)
    return result
