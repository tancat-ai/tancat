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
class JourneyResult:
    """Result of executing a journey through authenticated pages."""

    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]  # url -> elements
    failed_steps: list[str]  # human-readable descriptions
    error_message: str | None = None  # top-level error (SSO, MFA, CAPTCHA)
    redirected_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JourneyResult:
        """Deserialize from a plain dictionary."""
        return cls(
            success=bool(data.get("success", False)),
            captured_pages=data.get("captured_pages", {}),
            failed_steps=data.get("failed_steps", []),
            error_message=data.get("error_message"),
            redirected_urls=data.get("redirected_urls", []),
        )


def substitute_templates(text: str, credential_profile: CredentialProfile | None) -> str:
    """Replace {{username}} and {{password}} placeholders with credential values."""
    if credential_profile is None:
        return text
    result = text.replace("{{username}}", credential_profile.username)
    result = result.replace("{{password}}", credential_profile.password)
    return result
