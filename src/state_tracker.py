"""State tracking utilities for detecting DOM changes and URL transitions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class DOMState:
    """Snapshot of page DOM state at a point in time."""

    url: str
    dom_hash: str
    element_count: int
    title: str


@dataclass
class StateChange:
    """Represents detected changes between two DOM states."""

    change_type: str  # "initial" | "url" | "content" | "navigation"
    description: str
    from_state: DOMState | None
    to_state: DOMState


@dataclass
class StateTracker:
    """Track DOM and URL state changes across page interactions."""

    _history: list[DOMState] = field(default_factory=list)
    _changes: list[StateChange] = field(default_factory=list)

    @staticmethod
    def compute_dom_hash(content: str) -> str:
        """Return a SHA-256 hash of the page HTML content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def capture_state(
        self,
        url: str,
        html_content: str,
        element_count: int = 0,
        title: str = "",
    ) -> DOMState:
        """Capture and store the current page state."""
        state = DOMState(
            url=url,
            dom_hash=self.compute_dom_hash(html_content),
            element_count=element_count,
            title=title,
        )
        self._history.append(state)
        return state

    def detect_changes(self, new_state: DOMState) -> StateChange:
        """Compare new state against the previous one and return the change."""
        prev = self._history[-1] if self._history else None
        change = self._compute_change(prev, new_state)
        self._changes.append(change)
        return change

    def track_url_transition(self, from_url: str, to_url: str) -> StateChange | None:
        """Track a URL transition and classify it."""
        if not self._history:
            return None
        prev = self._history[-1]
        if from_url != to_url:
            change = StateChange(
                change_type="navigation",
                description=f"Navigated from {from_url} to {to_url}",
                from_state=prev,
                to_state=DOMState(url=to_url, dom_hash="", element_count=0, title=""),
            )
            self._changes.append(change)
            return change
        return None

    def get_history(self) -> list[DOMState]:
        """Return the full state history."""
        return list(self._history)

    def get_changes(self) -> list[StateChange]:
        """Return all detected state changes."""
        return list(self._changes)

    def _compute_change(self, prev: DOMState | None, curr: DOMState) -> StateChange:
        if prev is None:
            return StateChange(
                change_type="initial",
                description=f"Initial page load: {curr.url}",
                from_state=None,
                to_state=curr,
            )
        if prev.url != curr.url:
            return StateChange(
                change_type="url",
                description=f"URL changed from {prev.url} to {curr.url}",
                from_state=prev,
                to_state=curr,
            )
        if prev.dom_hash != curr.dom_hash:
            return StateChange(
                change_type="content",
                description=f"Content changed on {curr.url}",
                from_state=prev,
                to_state=curr,
            )
        return StateChange(
            change_type="none",
            description="No detectable change",
            from_state=prev,
            to_state=curr,
        )

    @staticmethod
    def urls_are_same_domain(url_a: str, url_b: str) -> bool:
        """Check if two URLs share the same domain."""
        return urlparse(url_a).netloc == urlparse(url_b).netloc
