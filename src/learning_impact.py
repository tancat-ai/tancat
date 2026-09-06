"""Controlled cold/warm learning-impact runner (AI-059 Phase 2).

The runner is a lab utility, not part of the generation path.  It executes the
same command once per leg, restoring a fixed store snapshot and directing each
leg to a fresh evidence directory.  Learning is disabled through explicit
environment gates so sidecars from one leg cannot mutate the next leg's store.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.failure_classifier import FailureCategory, classify_failure
from src.learning_metrics import LearningImpactMetrics, analyze_sidecars

# These names are intentionally public.  Generated-test fixtures can consume
# the same gate without importing this module (which keeps the lab decoupled
# from production test packages).
AUTO_LEARN_DISABLE_ENV = "AI059_DISABLE_AUTO_LEARN"
AUTO_LEARN_DISABLE_VALUE = "1"


@dataclass(frozen=True)
class BaselineLeg:
    """One controlled comparison leg.

    ``store_snapshot`` may be a file (e.g. a copied JSON/SQLite store) or a
    directory.  ``None`` means an empty store and is useful for a true cold
    start.  The runner never modifies the snapshot itself.
    """

    name: str
    store_snapshot: Path | None = None


@dataclass
class BaselineLegResult:
    """Result and persisted metadata for one leg."""

    name: str
    returncode: int
    duration_s: float
    evidence_dir: str
    store_snapshot: str | None
    metrics: LearningImpactMetrics
    store_snapshot_sha256: str | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "returncode": self.returncode,
            "duration_s": self.duration_s,
            "evidence_dir": self.evidence_dir,
            "store_snapshot": self.store_snapshot,
            "store_snapshot_sha256": self.store_snapshot_sha256,
            "timed_out": self.timed_out,
            "succeeded": self.succeeded,
            "metrics": self.metrics.to_dict(),
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        return data


@dataclass
class ControlledBaselineReport:
    """Aggregate report containing independently persisted leg results."""

    legs: list[BaselineLegResult] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "legs": [leg.to_dict() for leg in self.legs],
        }


def _refuse_production_store_target(target: Path) -> None:
    """Raise when ``target`` would destroy the production RAG store (B-048).

    The 2026-08-31 AI-059 lab rebuild passed the production store path as the
    restore target and ``shutil.rmtree`` erased the golden/learned patterns
    while the seed marker survived. The guard refuses any target that IS the
    production ``rag_path`` (or its ``.embedder.json`` companion), is an
    ANCESTOR of it (wiping ``evidence/`` or the storage root), or lies INSIDE
    it. ``restore_store_snapshot`` exposes ``allow_production_store=True`` for
    a deliberate, production-aware lab run.
    """
    from src.storage import get_storage

    try:
        production = get_storage().rag_path()
    except Exception:  # pragma: no cover - storage backends resolve statically
        return
    try:
        resolved = target.resolve()
        production_resolved = Path(production).resolve()
    except OSError:  # pragma: no cover - unresolvable paths
        return
    companion = Path(str(production_resolved) + ".embedder.json")
    endangered = (production_resolved, companion)

    def _within(child: Path, ancestor: Path) -> bool:
        return child == ancestor or ancestor in child.parents

    # Target IS the store/companion; or target sits INSIDE it; or target is
    # an ANCESTOR of it (wiping evidence/ or the storage root kills the store).
    if any(_within(resolved, p) or _within(p, resolved) for p in endangered):
        raise ValueError(
            "restore_store_snapshot refuses to touch the production RAG store "
            f"({production_resolved}); pass allow_production_store=True only "
            "for a deliberate, production-aware lab run (B-048)."
        )


def restore_store_snapshot(
    snapshot: Path | None,
    target: Path,
    *,
    allow_production_store: bool = False,
) -> None:
    """Restore ``target`` from ``snapshot`` or make the target empty.

    Restoration is performed before every leg.  Existing targets are removed
    first, including a directory containing a SQLite store.  A snapshot is
    copied rather than moved, so all legs remain repeatable.

    **B-048 guard:** the wipe is refused when ``target`` is (or contains) the
    production RAG store, unless ``allow_production_store=True`` is passed —
    a stale seed marker must never again be the only thing standing between
    the lab and the golden pack.
    """
    target = Path(target)
    if not allow_production_store:
        _refuse_production_store_target(target)
    snapshot_path = Path(snapshot) if snapshot is not None else None
    if snapshot_path is not None and not snapshot_path.exists():
        raise FileNotFoundError(f"store snapshot does not exist: {snapshot_path}")
    if snapshot_path is not None and snapshot_path.resolve() == target.resolve():
        return
    companion_target = Path(str(target) + ".embedder.json")
    companion_snapshot = Path(str(snapshot_path) + ".embedder.json") if snapshot_path is not None else None
    if companion_target.exists():
        companion_target.unlink()
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    if snapshot_path is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.is_dir():
        shutil.copytree(snapshot_path, target)
    else:
        shutil.copy2(snapshot_path, target)
    # Milvus-lite keeps its embedder stamp beside the database directory.
    # Treat that companion as part of a store snapshot when present.
    if companion_snapshot is not None and companion_snapshot.exists():
        shutil.copy2(companion_snapshot, companion_target)


def measurement_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build an environment that disables all known auto-learning hooks.

    ``RAG_ENABLED`` is deliberately *not* changed: warm legs must still read
    their restored store.  The extra aliases support older generated conftest
    templates while ``AI059_DISABLE_AUTO_LEARN`` is the canonical contract for
    new fixtures.
    """
    env = dict(base or os.environ)
    env[AUTO_LEARN_DISABLE_ENV] = AUTO_LEARN_DISABLE_VALUE
    env["RAG_AUTO_LEARN"] = "0"
    env["FLOW_MEMORY_AUTO_LEARN"] = "0"
    env["AUTO_LEARN"] = "0"
    return env


def _storage_environment(store_target: Path) -> dict[str, str]:
    """Map a conventional ``.../evidence/rag_store.db`` target to storage env."""
    target = store_target.resolve()
    if target.parent.name != "evidence":
        return {}
    return {
        "AITEST_STORAGE_ROOT": str(target.parent.parent),
        "AITEST_WORKSPACE": "default",
    }


def _with_lab_tokens(command: Sequence[str], *, evidence_dir: Path, leg: str, store_target: Path | None) -> list[str]:
    """Replace only the runner's explicit tokens in a command.

    We intentionally do not call ``str.format``: generated Python snippets
    often contain braces.  A caller may use ``{evidence_dir}``, ``{leg}``, and
    ``{store_target}`` in a command without shell interpolation.
    """
    replacements = {
        "{evidence_dir}": str(evidence_dir),
        "{leg}": leg,
        "{store_target}": str(store_target) if store_target is not None else "",
    }
    rendered: list[str] = []
    for part in command:
        value = part
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        rendered.append(value)
    return rendered


class ControlledBaselineRunner:
    """Run cold/warm legs with store and evidence isolation."""

    def __init__(
        self,
        *,
        evidence_root: str | Path,
        output_root: str | Path,
        store_target: str | Path | None = None,
        cwd: str | Path | None = None,
        base_env: Mapping[str, str] | None = None,
        timeout_s: float = 1800.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.evidence_root = Path(evidence_root)
        self.output_root = Path(output_root)
        self.store_target = Path(store_target) if store_target is not None else None
        self.cwd = Path(cwd) if cwd is not None else None
        self.base_env = dict(base_env or os.environ)
        self.timeout_s = timeout_s
        self.metadata = dict(metadata or {})

    def run(self, command: Sequence[str], legs: Sequence[BaselineLeg]) -> ControlledBaselineReport:
        """Execute ``command`` once per leg and persist each metric payload.

        The same command sequence is used for every leg.  Use the explicit
        ``{evidence_dir}`` token when the command needs to select the current
        output directory.  A non-zero subprocess exit is retained in the
        report rather than raising, allowing a lab run to compare partial
        evidence and inspect the failing leg.
        """
        if not command:
            raise ValueError("command must contain at least one executable")
        if not legs:
            raise ValueError("at least one baseline leg is required")
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        report = ControlledBaselineReport(
            metadata={
                "harness": "AI-059",
                "command": list(command),
                "timeout_s": self.timeout_s,
                "cwd": str(self.cwd) if self.cwd is not None else str(Path.cwd()),
                "auto_learning_disabled": True,
                "rag_enabled": self.base_env.get("RAG_ENABLED", "default-on"),
                **self.metadata,
            }
        )
        for leg in legs:
            safe_name = _safe_leg_name(leg.name)
            evidence_dir = self.evidence_root / safe_name
            output_dir = self.output_root / safe_name
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            diagnostics_path = output_dir / "rag_diagnostics.jsonl"
            if diagnostics_path.exists():
                diagnostics_path.unlink()
            # Fresh sidecars are required: stale output would make a leg's
            # denominator differ from the other legs.
            for sidecar in evidence_dir.glob("*.evidence.json"):
                sidecar.unlink()
            if self.store_target is not None:
                restore_store_snapshot(leg.store_snapshot, self.store_target)

            env = measurement_environment(self.base_env)
            if self.store_target is not None:
                env.update(_storage_environment(self.store_target))
            env["AI059_LEG"] = leg.name
            env["AI059_EVIDENCE_DIR"] = str(evidence_dir)
            env["AI059_RAG_DIAGNOSTICS_PATH"] = str(output_dir / "rag_diagnostics.jsonl")
            env["AI059_STORE_SNAPSHOT"] = str(leg.store_snapshot or "")
            started = time.monotonic()
            timed_out = False
            try:
                completed = subprocess.run(
                    _with_lab_tokens(command, evidence_dir=evidence_dir, leg=leg.name, store_target=self.store_target),
                    cwd=str(self.cwd) if self.cwd is not None else None,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    check=False,
                )
                returncode = completed.returncode
                stdout, stderr = completed.stdout, completed.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                returncode = 124
                stdout = _decode_output(exc.stdout)
                stderr = _decode_output(exc.stderr) + "\nmeasurement command timed out"
            duration = time.monotonic() - started
            metrics = analyze_sidecars(evidence_dir)
            result = BaselineLegResult(
                name=leg.name,
                returncode=returncode,
                duration_s=duration,
                evidence_dir=str(evidence_dir),
                store_snapshot=str(leg.store_snapshot) if leg.store_snapshot is not None else None,
                store_snapshot_sha256=_sha256_path(leg.store_snapshot),
                metrics=metrics,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
            )
            report.legs.append(result)
            (output_dir / "metrics.json").write_text(
                json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        (self.output_root / "baseline_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return report


def _sha256_path(path: Path | None) -> str | None:
    """Return a deterministic SHA-256 for a snapshot file or directory."""
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(str(child.relative_to(path)).replace("\\", "/").encode("utf-8"))
        with child.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _safe_leg_name(name: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "_" for character in name.strip())
    return cleaned or "leg"


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


# ---------------------------------------------------------------------------
# AI-059 lab hardening: sentinel-scoped warm store rebuild
# ---------------------------------------------------------------------------
# A fixed sentinel identity for lab warm stores so they never collide with (or
# bleed into) a real localhost project or another eval mock that happens to
# share a port -- the failure mode identified during AI-059 Session 1. The
# run-time resolver must be told to use the same sentinel via
# AI059_LAB_SITE_HASH for the bonus to apply.
DEFAULT_LAB_SITE_IDENTITY = "ai059-lab:ecommerce"

_REBUILD_STEP_ACTION = {
    "fill": "FILL",
    "click": "CLICK",
    "assertion": "ASSERT",
    "select": "SELECT",
}


def lab_site_hash(identity: str = DEFAULT_LAB_SITE_IDENTITY) -> str:
    """Deterministic sentinel site hash for a lab store identity string."""
    from src.rag_learn import site_hash

    return site_hash(identity)


def build_lab_identity(
    *,
    site: str,
    input_version: str = "",
    story_set: str = "",
    run_tag: str = "",
) -> str:
    """Compose a structured lab identity for one experimental cell.

    A cell is scoped by (site, input/site-edit version, story set, run tag)
    rather than a single constant or the fragile host:port hash. Distinct
    cells produce distinct sentinel hashes; the same cell reproduces the same
    hash across reruns. This keeps learned patterns from bleeding between
    sites, input edits, or story sets during the AI-059 controlled A/B --
    the exact failure mode the original single sentinel would have reintroduced.
    """
    parts = ["ai059-lab", site, input_version, story_set, run_tag]
    return "|".join(part for part in parts if part)


def _lab_pattern_for_step(step: dict[str, Any], sentinel: str) -> Any | None:
    """Map one evidence step to a sentinel-scoped ``LearnedPattern``, or None."""
    from src.rag_learn import LearnedPattern

    action = _REBUILD_STEP_ACTION.get(str(step.get("type", "")).lower())
    if action is None:
        return None
    label = str(step.get("label", "") or "").strip()
    locator = str(step.get("locator", "") or "").strip()
    if not label or not locator:
        return None
    return LearnedPattern(
        action_type=action,
        description=label,
        locator=locator,
        site_hash=sentinel,
    )


#: Failure classes that make a failed step a CONFIRMED locator negative (AI-058).
#: Mirrors ``rag_learn._LOCATOR_FAILURE_CATEGORIES`` so the lab store and the
#: production store agree on what counts as a locator failure.
_LAB_LOCATOR_FAILURE_CATEGORIES: set[FailureCategory] = {FailureCategory.LOCATOR_TIMEOUT}

#: AI-063 resolved-but-wrong classes — mirrors ``rag_learn._RESOLVED_WRONG_CATEGORIES``.
_LAB_RESOLVED_WRONG_CATEGORIES: set[FailureCategory] = {FailureCategory.ASSERTION_FAILURE}


def _lab_negative_pattern_for_step(step: dict[str, Any], sentinel: str) -> Any | None:
    """Map one FAILED evidence step to a sentinel-scoped ``learned_negative``, or None.

    AI-058 Slice 2: mirrors ``_lab_pattern_for_step`` (same action / label /
    locator gate + sentinel scoping) but only a *locator-class* failure (a
    non-passed step whose error classifies as ``LOCATOR_TIMEOUT``) becomes a
    negative. Assertion / navigation / unknown + selector-less steps are
    excluded so infra flakes never enter the lab negative store.

    AI-063: a failed ``ASSERTION`` step that carried a resolved selector is
    ALSO a negative (resolved-but-wrong) at lower confidence — the element was
    picked, existed, and failed its check. Mirrors the production trigger so
    the lab A/B evaluates the same signal the product would learn.
    """
    from src.rag_learn import LearnedPattern

    action = _REBUILD_STEP_ACTION.get(str(step.get("type", "")).lower())
    if action is None:
        return None
    label = str(step.get("label", "") or "").strip()
    locator = str(step.get("locator", "") or "").strip()
    if not label or not locator:
        return None
    result = step.get("result") or {}
    if str(result.get("status", "")) in ("passed", "partial_pass"):
        return None
    error = str(result.get("error", "") or "")
    try:
        detail = classify_failure(error)
    except Exception:
        return None
    if detail.category in _LAB_LOCATOR_FAILURE_CATEGORIES:
        confidence = 0.9
    elif detail.category in _LAB_RESOLVED_WRONG_CATEGORIES:
        confidence = 0.6
    else:
        return None
    return LearnedPattern(
        action_type=action,
        description=label,
        locator=locator,
        site_hash=sentinel,
        confidence=confidence,
        source="learned_negative",
    )


def rebuild_warm_store_from_evidence(
    evidence_dir: str | Path,
    *,
    store: Any,
    lab_site_identity: str = DEFAULT_LAB_SITE_IDENTITY,
    learn_negatives: bool = True,
) -> dict[str, int]:
    """Re-derive a lab-scoped warm RAG store from source evidence sidecars.

    Unlike the production learn path (``rag_learn.learn_from_evidence``), every
    pattern is tagged with a fixed LAB sentinel ``site_hash`` (derived from
    *lab_site_identity*, not the URL's host:port). This guarantees the warm
    store cannot collide with, or bleed into, a real localhost project or
    another eval mock that shares a port. The run-time resolver must use the
    same sentinel via ``AI059_LAB_SITE_HASH`` for the bonus / penalty to apply.

    **AI-058 Slice 2 (negative-aware rebuild):** when *learn_negatives* is set
    (default), failed / partial sidecars are ALSO scanned for confirmed
    locator-class failures and written as ``learned_negative`` entries tagged
    with the SAME sentinel — ``hit_count`` / ``last_seen`` intact — so the
    resolver can down-weight elements that failed before. The locator-class
    gate (``classify_failure`` → ``LOCATOR_TIMEOUT``) excludes infra flakes.
    This produces the ``warm-positive-negative`` store the A/B runner compares
    against the positives-only ``warm-positive`` store.

    The ``store`` is injectable so tests can use a fake backend (no Milvus or
    embedding model download required).

    Returns ``{"inserted": N, "exists": M, "skipped": K,
    "negatives_inserted": NI, "negatives_exists": NE}``.
    """
    from src.rag_learn import site_hash

    sentinel = site_hash(lab_site_identity)
    sidecars = sorted(Path(evidence_dir).glob("*.evidence.json"))
    inserted = exists = skipped = 0
    neg_inserted = neg_exists = 0
    for sidecar in sidecars:
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue
        test_status = str((data.get("test") or {}).get("status", ""))
        for step in data.get("steps") or []:
            result = step.get("result") or {}
            if test_status == "passed":
                if str(result.get("status", "")) != "passed":
                    continue
                pattern = _lab_pattern_for_step(step, sentinel)
                if pattern is None:
                    continue
                status, _hit = store.upsert_pattern(pattern)
                if status == "inserted":
                    inserted += 1
                else:
                    exists += 1
            elif learn_negatives:
                # AI-058 Slice 2: contrastive negatives from locator failures.
                neg = _lab_negative_pattern_for_step(step, sentinel)
                if neg is None:
                    continue
                status, _hit = store.upsert_negative_pattern(neg)
                if status == "inserted":
                    neg_inserted += 1
                else:
                    neg_exists += 1
    return {
        "inserted": inserted,
        "exists": exists,
        "skipped": skipped,
        "negatives_inserted": neg_inserted,
        "negatives_exists": neg_exists,
    }


__all__ = [
    "AUTO_LEARN_DISABLE_ENV",
    "AUTO_LEARN_DISABLE_VALUE",
    "BaselineLeg",
    "BaselineLegResult",
    "ControlledBaselineReport",
    "ControlledBaselineRunner",
    "DEFAULT_LAB_SITE_IDENTITY",
    "build_lab_identity",
    "lab_site_hash",
    "rebuild_warm_store_from_evidence",
    "measurement_environment",
    "restore_store_snapshot",
]
