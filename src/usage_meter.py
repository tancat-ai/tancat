"""Per-deployment usage meter + free-tier cap (Phase 6e, spec §5.5).

A "run" = one pytest execution of a generated package (the value moment). The
meter reads the **existing** ``evidence/run_results.sqlite`` (runs are already
persisted there by ``run_result_persistence``) plus a small local ledger for
**evidence exports** (which had no persisted record). Storage used is computed
on demand from the workspace. LLM tokens are reported as ``None`` (the customer
may run a provider that reports no ``usage`` — §9 Q6 accepts unknown).

Free tier: N runs + M evidence exports per 30 days. At the limit, new **runs**
block with an upgrade prompt; evidence **exports** block the non-core formats
(CSV/NDJSON/JUnit are core; Jira export is the gated one — a clear, honest
line). Configuration, all local, no network:

- ``AITEST_FREE_TIER_RUNS`` (default 25) — monthly run cap on the free tier.
- ``AITEST_FREE_TIER_EXPORTS`` (default 10) — monthly evidence-export cap.
- ``AITEST_ENFORCE_FREE_TIER=0`` — disable the hard stop (self-hoster override).
- ``AITEST_GRACE_DAYS`` is handled by the license layer.

The gate never fires for paid tiers (a valid license's tier has no caps).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.licensing.license import effective_tier, license_status
from src.licensing.tiers import is_paid_tier, limit_for

logger = logging.getLogger(__name__)

__all__ = [
    "FreeTierLimitError",
    "UsageMeter",
    "monthly_window",
]


def monthly_window(now: datetime | None = None) -> tuple[str, str]:
    """Return (start_iso, end_iso) of the current 30-day usage window (UTC)."""
    end = now or datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


_UPGRADE_PROMPT = (
    "You've hit the free-tier limit. Upgrade to a paid tier (self-serve / pro / air-gap) "
    "for unlimited runs and exports — see the license key from Cat Tan Operations."
)


class FreeTierLimitError(RuntimeError):
    """Raised when a free-tier run/export cap is exceeded and enforcement is on."""

    def __init__(self, message: str, *, run_remaining: int = 0, export_remaining: int = 0) -> None:
        super().__init__(message)
        self.run_remaining = run_remaining
        self.export_remaining = export_remaining

    @property
    def upgrade_prompt(self) -> str:
        return _UPGRADE_PROMPT


@dataclass
class UsageSummary:
    """One view into the deployment's usage (the Usage panel / --json)."""

    tier: str
    license_status: str
    windows_start: str
    windows_end: str
    runs_used: int = 0
    runs_limit: int | None = None
    exports_used: int = 0
    exports_limit: int | None = None
    storage_bytes: int = 0
    llm_tokens: int | None = None
    enforcement_on: bool = True

    @property
    def runs_remaining(self) -> int | None:
        if self.runs_limit is None:
            return None
        return max(0, self.runs_limit - self.runs_used)

    @property
    def exports_remaining(self) -> int | None:
        if self.exports_limit is None:
            return None
        return max(0, self.exports_limit - self.exports_used)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "license_status": self.license_status,
            "window_start": self.windows_start,
            "window_end": self.windows_end,
            "runs": {
                "used": self.runs_used,
                "limit": self.runs_limit,
                "remaining": self.runs_remaining,
            },
            "evidence_exports": {
                "used": self.exports_used,
                "limit": self.exports_limit,
                "remaining": self.exports_remaining,
            },
            "storage_bytes": self.storage_bytes,
            "llm_tokens": self.llm_tokens,
            "enforcement_on": self.enforcement_on,
        }


class UsageMeter:
    """Local usage accounting: runs (from run_results.sqlite), exports (ledger)."""

    def __init__(
        self,
        *,
        run_db_path: str | Path | None = None,
        ledger_path: str | Path | None = None,
        storage_root: str | Path | None = None,
        now: datetime | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        # Resolved lazily so a bare UsageMeter() works without storage config.
        self._run_db_path: Path | None = Path(run_db_path) if run_db_path else None
        self._ledger_path: Path | None = Path(ledger_path) if ledger_path else None
        self._storage_root: Path | None = Path(storage_root) if storage_root else None
        self._now = now
        self._env = env if env is not None else os.environ

    # -- paths ---------------------------------------------------------------
    def _db_path(self) -> Path:
        if self._run_db_path is not None:
            return self._run_db_path
        try:
            from src.storage import get_storage

            return get_storage().db_path()
        except Exception:  # pragma: no cover - fallback
            return Path("evidence/run_results.sqlite")

    def _ledger(self) -> Path:
        if self._ledger_path is not None:
            return self._ledger_path
        try:
            from src.storage import get_storage

            return get_storage().evidence_dir() / ".usage_ledger.json"
        except Exception:  # pragma: no cover - fallback
            return Path("evidence/.usage_ledger.json")

    def _root(self) -> Path:
        if self._storage_root is not None:
            return self._storage_root
        try:
            from src.storage import get_storage

            return get_storage().root
        except Exception:  # pragma: no cover - fallback
            return Path(".")

    # -- configuration -------------------------------------------------------
    def _int_env(self, key: str, default: int) -> int:
        try:
            return int(self._env.get(key, str(default)))
        except TypeError, ValueError:
            return default

    @property
    def runs_limit(self) -> int | None:
        tier = effective_tier(now=_epoch(self._now)) if self._now else effective_tier()
        if is_paid_tier(tier):
            return None
        return self._int_env("AITEST_FREE_TIER_RUNS", limit_for("free", "runs_per_month", 25) or 25)

    @property
    def exports_limit(self) -> int | None:
        tier = effective_tier(now=_epoch(self._now)) if self._now else effective_tier()
        if is_paid_tier(tier):
            return None
        return self._int_env("AITEST_FREE_TIER_EXPORTS", limit_for("free", "evidence_exports_per_month", 10) or 10)

    @property
    def enforcement_on(self) -> bool:
        return self._env.get("AITEST_ENFORCE_FREE_TIER", "1") != "0"

    # -- runs ----------------------------------------------------------------
    def count_runs_this_month(self, now: datetime | None = None) -> int:
        start_iso, _end = monthly_window(now or self._now)
        db = self._db_path()
        if not db.exists():
            return 0
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE created_at >= ?",
                    (start_iso,),
                ).fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.warning("UsageMeter cannot read run history at %s: %s", db, exc)
            return 0

    # -- evidence exports (local ledger) --------------------------------------
    def _load_ledger(self) -> dict[str, Any]:
        path = self._ledger()
        if not path.exists():
            return {"exports": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and "exports" in data else {"exports": []}
        except OSError, ValueError:
            return {"exports": []}

    def _save_ledger(self, data: dict[str, Any]) -> None:
        path = self._ledger()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def record_export(self, format_name: str, output_path: str | Path = "") -> None:
        """Record one evidence export in the local ledger (idempotent append)."""
        data = self._load_ledger()
        data.setdefault("exports", []).append(
            {
                "format": format_name,
                "output": str(output_path),
                "at": (self._now or datetime.now(UTC)).isoformat(),
            }
        )
        self._save_ledger(data)

    def count_exports_this_month(self, now: datetime | None = None) -> int:
        start, _end = monthly_window(now or self._now)
        start_dt = _parse_iso(start)
        count = 0
        for entry in self._load_ledger().get("exports", []):
            at = _parse_iso(entry.get("at"))
            if at is not None and start_dt is not None and at >= start_dt:
                count += 1
        return count

    # -- storage --------------------------------------------------------------
    def storage_bytes(self) -> int:
        root = self._root()
        total = 0
        if not root.exists():
            return 0
        for top in ("generated_tests", "evidence"):
            d = root / top
            if not d.exists():
                continue
            for p in d.rglob("*"):
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except OSError:  # pragma: no cover - race
                    pass
        return total

    # -- summary + gates -------------------------------------------------------
    def summary(self) -> UsageSummary:
        now = self._now or datetime.now(UTC)
        status = license_status(now=_epoch(now))
        tier = effective_tier(now=_epoch(now))
        start, end = monthly_window(now)
        return UsageSummary(
            tier=tier,
            license_status=status.status,
            windows_start=start,
            windows_end=end,
            runs_used=self.count_runs_this_month(now),
            runs_limit=self.runs_limit,
            exports_used=self.count_exports_this_month(now),
            exports_limit=self.exports_limit,
            storage_bytes=self.storage_bytes(),
            llm_tokens=None,
            enforcement_on=self.enforcement_on,
        )

    def assert_run_allowed(self) -> None:
        """Raise :class:`FreeTierLimitError` when a free-tier run is disallowed."""
        if not self.enforcement_on:
            return
        summary = self.summary()
        remaining = summary.runs_remaining
        if remaining is not None and remaining <= 0:
            raise FreeTierLimitError(
                f"Free tier run limit reached ({summary.runs_used}/{summary.runs_limit} runs in the current 30-day window). "
                f"{_UPGRADE_PROMPT}",
                run_remaining=remaining,
                export_remaining=summary.exports_remaining or 0,
            )

    def assert_export_allowed(self, format_name: str) -> None:
        """Raise for paid-gated export formats beyond the monthly free cap.

        Core evidence formats (CSV/NDJSON/JUnit/HTML) stay free; only formats
        outside the free tier's claims (e.g. Jira) are capped here — the calling
        gate also checks `feature_enabled` for the required claim.
        """
        if not self.enforcement_on:
            return
        from src.licensing.license import feature_enabled

        if feature_enabled("jira_export") or format_name.lower() not in ("jira",):
            return
        summary = self.summary()
        remaining = summary.exports_remaining
        if remaining is not None and remaining <= 0:
            raise FreeTierLimitError(
                f"Free tier evidence-export limit reached ({summary.exports_used}/{summary.exports_limit} exports "
                f"in the current 30-day window). {_UPGRADE_PROMPT}",
                run_remaining=summary.runs_remaining or 0,
                export_remaining=remaining,
            )


def _epoch(now: datetime | None) -> int | None:
    if now is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return int(now.timestamp())
