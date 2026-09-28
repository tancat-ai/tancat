"""Shared data models for the intelligent pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ExportMode(StrEnum):
    """Controls how exported test files are produced.

    - POM: export pages/ directory with clean POM classes
    - FLAT: export only test files (no pages/)
    """

    POM = "pom"
    FLAT = "flat"


@dataclass(frozen=True)
class PlaceholderUse:
    """A single placeholder token found in generated skeleton code."""

    action: str
    description: str
    token: str
    line_number: int
    raw_line: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class TestStep:
    """An ordered step within a generated pytest test function."""

    __test__ = False

    line_number: int
    raw_line: str
    placeholders: list[PlaceholderUse] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "line_number": self.line_number,
            "raw_line": self.raw_line,
            "placeholders": [placeholder.to_dict() for placeholder in self.placeholders],
        }


@dataclass(frozen=True)
class PageRequirement:
    """A page reference declared in the skeleton's PAGES_NEEDED block.

    The LLM writes short keywords (not URLs) that match GOTO placeholder descriptions.
    For example: {{GOTO:cart}} → keyword "cart". Actual URLs are resolved later
    against journey scraping results.
    """

    keyword: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class TestJourney:
    """A structured representation of one generated pytest test function."""

    __test__ = False

    test_name: str
    start_line: int
    end_line: int
    page_object_names: list[str] = field(default_factory=list)
    steps: list[TestStep] = field(default_factory=list)

    @property
    def placeholders(self) -> list[PlaceholderUse]:
        """Return all placeholders encountered across the journey."""
        return [placeholder for step in self.steps for placeholder in step.placeholders]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "test_name": self.test_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "page_object_names": list(self.page_object_names),
            "steps": [step.to_dict() for step in self.steps],
            "placeholders": [placeholder.to_dict() for placeholder in self.placeholders],
        }


@dataclass(frozen=True)
class TestResolutionCounts:
    """Resolved/unresolved placeholder counts for one generated test (B-097).

    When any placeholder in a test is unresolved, the emitter writes one
    ``pytest.skip()`` at the top of the test, which also hides every step that
    DID resolve. These counts carry that hidden work beside the test's outcome,
    so a partially resolved test does not read as if nothing ran.
    """

    test_name: str
    resolved: int
    unresolved: int

    __test__ = False

    @property
    def total(self) -> int:
        """Total placeholders seen in this test."""
        return self.resolved + self.unresolved

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "test_name": self.test_name,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "total": self.total,
        }


class VerificationStatus(StrEnum):
    """How strongly a generated test verified its own criterion (B-100).

    - VERIFIED_BY_ELEMENT: an ASSERT resolved to a specific element and the
      emitter wrote a real check against it.
    - VERIFIED_BY_PAGE_ARRIVAL: the criterion's check is a URL assertion -- the
      test proves it reached the page the criterion describes.
    - UNVERIFIED: nothing provably checked the criterion. ``reason`` names what
      was missing and is never empty.
    """

    VERIFIED_BY_ELEMENT = "verified_by_element"
    VERIFIED_BY_PAGE_ARRIVAL = "verified_by_page_arrival"
    UNVERIFIED = "unverified"


_VERIFICATION_LABELS: dict[str, str] = {
    VerificationStatus.VERIFIED_BY_ELEMENT: "verified by element",
    VerificationStatus.VERIFIED_BY_PAGE_ARRIVAL: "verified by page arrival",
    VerificationStatus.UNVERIFIED: "unverified",
}


@dataclass(frozen=True)
class TestVerificationVerdict:
    """What one generated test proved, decided at emit time (B-100).

    The eval harness has to *guess* this from the emitted code alone. The
    resolver knows it: it saw which page a locator was resolved against, and
    whether the emitted check targets an element or a page arrival. This
    verdict carries that knowledge into the evidence bundle, so "every pass
    names what it checked" is provable from the artifact the customer keeps.
    """

    __test__ = False

    test_name: str
    status: VerificationStatus
    checked: str = ""
    page_url: str = ""
    reason: str = ""

    @property
    def label(self) -> str:
        """Human-readable status phrase (e.g. ``verified by element``)."""
        raw = getattr(self.status, "value", self.status)
        return _VERIFICATION_LABELS.get(str(raw), str(raw))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        raw = getattr(self.status, "value", self.status)
        return {
            "test_name": self.test_name,
            "status": str(raw),
            "label": self.label,
            "checked": self.checked,
            "page_url": self.page_url,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScrapedPage:
    """Metadata for one scraped page used by the pipeline."""

    url: str
    element_count: int
    elements: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class GeneratedPageObject:
    """A page object module generated from scraped page data."""

    class_name: str
    module_name: str
    file_path: str
    url: str
    methods: list[str] = field(default_factory=list)
    module_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class ManifestRecord:
    """One unresolved or informational record written into the pipeline manifest."""

    kind: str
    message: str
    test_name: str = ""
    placeholder: str = ""
    page_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class PipelineArtifactSet:
    """The structured output package produced by one pipeline run."""

    run_id: str
    test_file_path: str
    page_object_paths: list[str] = field(default_factory=list)
    manifest_path: str = ""
    pages: list[ScrapedPage] = field(default_factory=list)
    records: list[ManifestRecord] = field(default_factory=list)
    pom_mode: bool = False
    # B-100: path to the per-test verification-strength evidence file.
    verification_strength_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "run_id": self.run_id,
            "test_file_path": self.test_file_path,
            "page_object_paths": list(self.page_object_paths),
            "manifest_path": self.manifest_path,
            "pages": [page.to_dict() for page in self.pages],
            "records": [record.to_dict() for record in self.records],
            "pom_mode": self.pom_mode,
            "verification_strength_path": self.verification_strength_path,
        }
