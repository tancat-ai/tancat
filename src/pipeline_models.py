"""Shared data models for the intelligent pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    """A page URL declared in the skeleton's PAGES_NEEDED block."""

    url: str
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "run_id": self.run_id,
            "test_file_path": self.test_file_path,
            "page_object_paths": list(self.page_object_paths),
            "manifest_path": self.manifest_path,
            "pages": [page.to_dict() for page in self.pages],
            "records": [record.to_dict() for record in self.records],
        }
