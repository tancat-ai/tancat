"""eval_metrics.py — Metric computation for the Phase 5 evaluation harness.

Pure functions — no browser, no LLM, no I/O. Consumes structured results
from golden_validator.py and produces metric scores.

Metrics:
  - Placeholder resolution accuracy
  - Generated test pass rate
  - False positive rate
  - Skeleton generation completeness
  - Generation duration (wall-clock, per story)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ResolutionResult:
    """Single placeholder resolution outcome."""

    action: str
    description: str
    expected_locator: str
    tolerance_selectors: list[str]
    generated_locator: str | None  # None = skip/unresolved
    matched: bool  # True if generated_locator is in [expected, *tolerances]
    # Gate 2 (B-093): the criterion this placeholder belongs to, so the
    # runner can attribute a false green to the test function of its own
    # criterion instead of the whole story.
    criterion_index: int | None = None
    # How strongly the criterion's own test verified this ASSERT, when
    # measured on the emitted code (see golden_validator._classify_verification):
    # "golden" | "subject" | "page" | "unverified" | None (non-ASSERT rows).
    verification: str | None = None


@dataclass
class StoryResult:
    """Complete evaluation result for one story."""

    story_id: str
    site: str
    total_criteria: int
    criteria_with_skeletons: int
    resolutions: list[ResolutionResult] = field(default_factory=list)
    tests_executed: int = 0
    tests_passed: int = 0
    tests_false_positive: int = 0
    generation_duration_s: float = 0.0
    # B-061: True when the pytest subprocess was killed by its timeout. A
    # timed-out run must never render as "Tests: 0" — that is indistinguishable
    # from "no test files persisted".
    tests_timed_out: bool = False


@dataclass
class HarnessReport:
    """Aggregated report across all stories."""

    stories: list[StoryResult] = field(default_factory=list)

    @property
    def total_placeholders(self) -> int:
        return sum(len(s.resolutions) for s in self.stories)

    @property
    def correct_resolutions(self) -> int:
        return sum(r.matched for s in self.stories for r in s.resolutions)

    @property
    def total_tests_executed(self) -> int:
        return sum(s.tests_executed for s in self.stories)

    @property
    def total_tests_passed(self) -> int:
        return sum(s.tests_passed for s in self.stories)

    @property
    def total_false_positives(self) -> int:
        return sum(s.tests_false_positive for s in self.stories)

    def resolution_accuracy(self) -> float:
        """% of placeholders that resolved to the correct locator."""
        if not self.total_placeholders:
            return 0.0
        return self.correct_resolutions / self.total_placeholders * 100

    def test_pass_rate(self) -> float:
        """% of generated tests that passed when executed."""
        if not self.total_tests_executed:
            return 0.0
        return self.total_tests_passed / self.total_tests_executed * 100

    def false_positive_rate(self) -> float:
        """% of tests that passed but verified nothing (B-093 gate 2)."""
        if not self.total_tests_executed:
            return 0.0
        return self.total_false_positives / self.total_tests_executed * 100

    def _verification_counts(self) -> dict[str, int]:
        """ASSERT placeholders by how strongly the generated test verified them."""
        counts = {"golden": 0, "subject": 0, "page": 0, "unverified": 0}
        for s in self.stories:
            for r in s.resolutions:
                if r.action != "ASSERT":
                    continue
                key = r.verification or "unverified"
                counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def verified_by_element(self) -> int:
        """ASSERTs matched to the golden element or to a distinctive element."""
        c = self._verification_counts()
        return c["golden"] + c["subject"]

    @property
    def verified_by_page(self) -> int:
        """ASSERTs verified by reaching the expected page (URL assertion)."""
        return self._verification_counts()["page"]

    @property
    def unverified_asserts(self) -> int:
        """ASSERTs the generated test did not provably verify."""
        return self._verification_counts()["unverified"]

    def skeleton_completeness(self) -> float:
        """% of criteria that produced a skeleton test function."""
        total = sum(s.total_criteria for s in self.stories)
        if not total:
            return 0.0
        return sum(s.criteria_with_skeletons for s in self.stories) / total * 100

    def mean_generation_duration(self) -> float:
        """Mean pipeline wall-clock time per story in seconds."""
        if not self.stories:
            return 0.0
        return sum(s.generation_duration_s for s in self.stories) / len(self.stories)

    def to_summary(self) -> str:
        """Human-readable summary table."""
        vc = self._verification_counts()
        lines = [
            "=" * 70,
            "EVALUATION HARNESS REPORT",
            "=" * 70,
            "",
            f"  Stories evaluated:        {len(self.stories)}",
            f"  Total placeholders:       {self.total_placeholders}",
            f"  Correct resolutions:      {self.correct_resolutions}",
            f"  Resolution accuracy:      {self.resolution_accuracy():.1f}%",
            "",
            "  ASSERT verification (B-093 gate 2):",
            f"    by element (golden)              {vc['golden']}",
            f"    by element (distinctive match)   {vc['subject']}",
            f"    by page arrival (URL assertion)  {vc['page']}",
            f"    unverified                       {vc['unverified']}",
            "",
            f"  Tests executed:           {self.total_tests_executed}",
            f"  Tests passed:             {self.total_tests_passed}",
        ]
        timed_out = [s.story_id for s in self.stories if s.tests_timed_out]
        if timed_out:
            # B-061: a timeout is NOT "zero tests ran" — say so explicitly.
            lines.append(
                f"  Tests timed out:          {len(timed_out)} story run(s) killed by the "
                f"pytest timeout: {', '.join(timed_out)} (not counted in the totals above)"
            )
        lines += [
            f"  Test pass rate:           {self.test_pass_rate():.1f}%",
            f"  False positives:          {self.total_false_positives}",
            f"  False positive rate:      {self.false_positive_rate():.1f}%",
            "",
            f"  Skeleton completeness:    {self.skeleton_completeness():.1f}%",
            f"  Mean gen. duration:       {self.mean_generation_duration():.1f}s",
            "",
            "-" * 70,
            "PER-STORY BREAKDOWN",
            "-" * 70,
        ]
        for s in self.stories:
            acc = sum(r.matched for r in s.resolutions) / len(s.resolutions) * 100 if s.resolutions else 0.0
            lines.append(f"  {s.story_id} ({s.site}):")
            lines.append(
                f"    Placeholders: {len(s.resolutions)} correct={sum(r.matched for r in s.resolutions)}/{len(s.resolutions)} ({acc:.0f}%)"
            )
            if s.tests_timed_out:
                lines.append("    Tests:        TIMED OUT (pytest run killed — no result)")
            else:
                lines.append(
                    f"    Tests:        {s.tests_executed} passed={s.tests_passed} false_pos={s.tests_false_positive}"
                )
            lines.append(f"    Skeletons:    {s.criteria_with_skeletons}/{s.total_criteria}")
            lines.append(f"    Duration:     {s.generation_duration_s:.1f}s")
            lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return {
            "stories": [asdict(s) for s in self.stories],
        }

    @classmethod
    def from_dict(cls, data: dict) -> HarnessReport:
        """Deserialize from a plain dict (JSON baseline)."""
        stories = []
        for s_data in data.get("stories", []):
            resolutions = [ResolutionResult(**r) for r in s_data.get("resolutions", [])]
            stories.append(
                StoryResult(
                    story_id=s_data["story_id"],
                    site=s_data["site"],
                    total_criteria=s_data["total_criteria"],
                    criteria_with_skeletons=s_data["criteria_with_skeletons"],
                    resolutions=resolutions,
                    tests_executed=s_data.get("tests_executed", 0),
                    tests_passed=s_data.get("tests_passed", 0),
                    tests_false_positive=s_data.get("tests_false_positive", 0),
                    generation_duration_s=s_data.get("generation_duration_s", 0.0),
                    tests_timed_out=s_data.get("tests_timed_out", False),
                )
            )
        return cls(stories=stories)


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------


@dataclass
class BaselineDelta:
    """Metric delta between a baseline and a new run."""

    metric: str
    baseline: float
    current: float
    delta: float  # positive = improvement

    def formatted(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        indicator = "[+]" if self.delta > 0 else ("[-]" if self.delta < 0 else "[=]")
        return f"  {indicator} {self.metric}: {self.baseline:.1f}% -> {self.current:.1f}% ({sign}{self.delta:.1f}pp)"


def compute_deltas(baseline: HarnessReport, current: HarnessReport) -> list[BaselineDelta]:
    """Compare two reports and return per-metric deltas."""
    return [
        BaselineDelta(
            "Resolution accuracy",
            baseline.resolution_accuracy(),
            current.resolution_accuracy(),
            current.resolution_accuracy() - baseline.resolution_accuracy(),
        ),
        BaselineDelta(
            "Test pass rate",
            baseline.test_pass_rate(),
            current.test_pass_rate(),
            current.test_pass_rate() - baseline.test_pass_rate(),
        ),
        BaselineDelta(
            "False positive rate",
            baseline.false_positive_rate(),
            current.false_positive_rate(),
            baseline.false_positive_rate() - current.false_positive_rate(),  # lower is better
        ),
        BaselineDelta(
            "Skeleton completeness",
            baseline.skeleton_completeness(),
            current.skeleton_completeness(),
            current.skeleton_completeness() - baseline.skeleton_completeness(),
        ),
    ]


def deltas_to_report(deltas: list[BaselineDelta]) -> str:
    """Render deltas as a human-readable comparison."""
    lines = [
        "=" * 70,
        "BASELINE COMPARISON",
        "=" * 70,
        "",
    ]
    for d in deltas:
        lines.append(d.formatted())
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)
