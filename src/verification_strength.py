"""B-100: what each generated test proved, decided where the resolver knows it.

The eval harness (B-093 gate 2) has to *infer* verification strength from the
emitted code alone, because that is all it sees. The emitter knows more: it saw
which page a locator was resolved against, and whether the emitted check is an
element check or a page arrival. This module turns those resolution facts into
one verdict per test -- ``verified by element`` / ``verified by page arrival`` /
``unverified`` plus a reason -- so the evidence bundle can carry the verdict
instead of leaving a reader (or the harness) to guess it.

Pure functions, no I/O. The orchestrator calls :func:`compute_test_verification_verdicts`
once at the emit chokepoint and carries the result into the evidence bundle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.pipeline_models import (
    TestJourney,
    TestResolutionCounts,
    TestVerificationVerdict,
    VerificationStatus,
)


@dataclass(frozen=True)
class ResolvedAssertion:
    """One ASSERT placeholder and what the emitter wrote for it.

    ``resolved_value`` is the emitted expression (a selector, a
    ``to_have_url`` call, or a skip), ``assertion_type`` is ``"url"`` for a
    page-arrival assertion, and ``is_page_level`` marks the B-069/B-086/B-088
    page-level families whose skip VALUE the emitter overrides into a real
    structural check.
    """

    description: str
    resolved_value: str
    assertion_type: str | None = None
    page_url: str | None = None
    is_page_level: bool = False

    @property
    def is_skip(self) -> bool:
        """True when the emitted replacement is a ``pytest.skip`` (no check)."""
        return "pytest.skip" in self.resolved_value

    @property
    def is_page_arrival(self) -> bool:
        """True when the check proves arrival at a page (a URL assertion)."""
        return self.assertion_type == "url" and not self.is_skip

    @property
    def is_element_check(self) -> bool:
        """True when the emitter wrote a real check against an element."""
        if self.is_page_arrival:
            return False
        if self.is_skip and not self.is_page_level:
            return False
        return True


def _unresolved_reason(descriptions: Sequence[str], unresolved: int, total: int) -> str:
    """Name the unresolved placeholders and the count -- never return silence."""
    unique = list(dict.fromkeys(description for description in descriptions if description))
    if not unique:
        return f"{unresolved} of {total} placeholders unresolved"
    named = "; ".join(f"'{description}'" for description in unique)
    return f"{unresolved} of {total} placeholders unresolved: {named}"


def compute_test_verification_verdicts(
    journeys: Sequence[TestJourney],
    assertions_by_test: Mapping[str, Sequence[ResolvedAssertion]],
    unresolved_descriptions: Mapping[str, Sequence[str]],
    counts_by_test: Mapping[str, TestResolutionCounts],
) -> list[TestVerificationVerdict]:
    """Return one verdict per journey, in journey order.

    Args:
        journeys: Parsed test functions, one per criterion.
        assertions_by_test: Test name -> resolved ASSERT placeholders.
        unresolved_descriptions: Test name -> descriptions the emitter skipped.
        counts_by_test: Test name -> resolved/unresolved counts (B-097), so the
            reason names the same split the report already shows.

    Returns:
        One :class:`TestVerificationVerdict` per journey. An ``unverified``
        verdict always carries a non-empty reason.
    """
    verdicts: list[TestVerificationVerdict] = []
    for journey in journeys:
        name = journey.test_name
        counts = counts_by_test.get(name)
        unresolved = counts.unresolved if counts is not None else 0
        total = counts.total if counts is not None else len(journey.placeholders)

        if unresolved > 0:
            verdicts.append(
                TestVerificationVerdict(
                    test_name=name,
                    status=VerificationStatus.UNVERIFIED,
                    reason=_unresolved_reason(unresolved_descriptions.get(name, ()), unresolved, total),
                )
            )
            continue

        assertions = assertions_by_test.get(name, ())
        element = next((a for a in assertions if a.is_element_check), None)
        if element is not None:
            verdicts.append(
                TestVerificationVerdict(
                    test_name=name,
                    status=VerificationStatus.VERIFIED_BY_ELEMENT,
                    checked=element.resolved_value,
                    page_url=element.page_url or "",
                )
            )
            continue

        page = next((a for a in assertions if a.is_page_arrival), None)
        if page is not None:
            verdicts.append(
                TestVerificationVerdict(
                    test_name=name,
                    status=VerificationStatus.VERIFIED_BY_PAGE_ARRIVAL,
                    checked=page.resolved_value,
                    page_url=page.page_url or "",
                )
            )
            continue

        verdicts.append(
            TestVerificationVerdict(
                test_name=name,
                status=VerificationStatus.UNVERIFIED,
                reason="no element or page-arrival assertion was emitted for this criterion",
            )
        )
    return verdicts


__all__ = [
    "ResolvedAssertion",
    "compute_test_verification_verdicts",
]
