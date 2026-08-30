#!/usr/bin/env python3
"""AI-058 metric gate — deterministic resolver-level A/B on the AMBIGUOUS mock.

The LLM skeleton generator is unreliable on this box for the local-mock story
(it burns the token budget producing degenerate output), so a *generation-level*
``mean_pass_depth`` A/B cannot be forced. This script proves the same thing at
the level that actually shipped (AI-064) — the **resolver** — with zero run-to-
run variance: identical frozen candidate pool for both legs, the sole variable
is the step-scoped seeded negative.

The ambiguous mock's confirmation page offers 2+ genuine candidates for the
"order success message" step:

  * ``#order-success-message``  — the golden (visible, highest-scoring)
  * ``#order-success-title``    — the other correct element
  * ``#order-note``             — the VISIBLE TRAP (shares the "Your order ..."
                                  text prefix; the wrong pick for this step)

Three legs (no LLM, no mock server — frozen ``scraped_pages/`` dump only):
  1. base ranking        — confirm the trap IS in the candidate pool and that
                           the control ranks the correct winner.
  2. seeded negative     — the step-scoped negative on ``#order-note`` must
                           demote the trap on the 'order success message' step
                           WITHOUT harming the correct winner.
  3. step-scoping guard  — a different step ('Back to Store') is unchanged by
                           the negative (no cross-step bleed).

Usage:
    python scripts/ai058_ambiguous_resolver_ab.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.learning_impact import lab_site_hash  # noqa: E402
from src.placeholder_resolver import PlaceholderResolver  # noqa: E402
from src.rag_store import RetrievedPattern  # noqa: E402

LAB_IDENTITY = "ai059-lab:ambiguous"
SENTINEL = lab_site_hash(LAB_IDENTITY)
DUMP = PROJECT_ROOT / "scripts" / "eval" / "scraped_pages" / "http_localhost_8781_success.html.json"

TRAP = "#order-note"
CORRECT = "#order-success-message"
STEP_DESC = "order success message"


def load_pool() -> list[dict[str, str]]:
    data = json.loads(DUMP.read_text(encoding="utf-8"))
    els = data.get("elements", data.get("page_elements", []))
    return [dict(el) for el in els]


def seed_patterns(*, seed: bool) -> list[RetrievedPattern]:
    if not seed:
        return []
    return [
        RetrievedPattern(
            description=f"ASSERT: {STEP_DESC}",
            selector=TRAP,
            action_type="ASSERT",
            confidence=1.0,
            source="learned_negative",
            site_hash=SENTINEL,
            hit_count=4,
            last_seen=0.0,
        )
    ]


def rank(action: str, description: str, pool: list[dict[str, str]], *, seed: bool) -> list[tuple[int, dict[str, str]]]:
    resolver = PlaceholderResolver(match_threshold=0)
    return resolver.rank_candidates(
        action, description, pool, golden_patterns=seed_patterns(seed=seed), site_hash=SENTINEL
    )


def score_of(ranked: list[tuple[int, dict[str, str]]], selector: str) -> int | None:
    for s, e in ranked:
        if e.get("selector") == selector:
            return s
    return None


def top(ranked: list[tuple[int, dict[str, str]]]) -> str:
    return str(ranked[0][1].get("selector", "")) if ranked else "UNRESOLVED"


def main() -> int:
    if not DUMP.exists():
        print(
            "frozen scraped_pages/ dump for the ambiguous mock not present "
            "(gitignored; regenerate by scraping http://localhost:8781/success.html "
            "from mock_sites/ambiguous). Exiting 2.",
            file=sys.stderr,
        )
        return 2

    pool = load_pool()
    checks: list[tuple[str, bool]] = []

    print("=" * 66)
    print("AI-058 metric gate — resolver-level A/B on the ambiguous mock")
    print(f"  candidate pool: {len(pool)} elements (frozen, identical for both legs)")
    print("=" * 66)

    # ── LEG 1: base ranking (the trap must be a real candidate) ──────────────
    ctrl = rank("ASSERT", STEP_DESC, pool, seed=False)
    treat = rank("ASSERT", STEP_DESC, pool, seed=True)
    print("\n[LEG 1] base ranking — 'order success message'")
    print(f"  control  : {top(ctrl)!r}  score={ctrl[0][0]}")
    print(f"  treatment: {top(treat)!r}  score={treat[0][0]}")
    trap_c = score_of(ctrl, TRAP)
    trap_t = score_of(treat, TRAP)
    correct_c = score_of(ctrl, CORRECT)
    correct_t = score_of(treat, CORRECT)
    print(f"  {TRAP}        control score={trap_c}   treatment score={trap_t}")
    print(f"  {CORRECT}      control score={correct_c}   treatment score={correct_t}")
    checks.append(("leg1 trap is a real candidate (present in control pool)", trap_c is not None))
    checks.append(("leg1 control ranks the correct winner", top(ctrl) == CORRECT))
    checks.append(
        (
            "leg1 negative demotes the trap (score drops)",
            (trap_c is not None and trap_t is not None and trap_t < trap_c),
        )
    )

    # ── LEG 2: the negative must not harm the correct winner ─────────────────
    checks.append(("leg2 treatment keeps the correct winner", top(treat) == CORRECT))
    checks.append(("leg2 correct winner score unchanged by the negative", correct_c == correct_t))

    # ── LEG 3: step-scoping guard (a different step is unchanged) ────────────
    ctrl3 = rank("CLICK", "Back to Store", pool, seed=False)
    treat3 = rank("CLICK", "Back to Store", pool, seed=True)
    print("\n[LEG 3] step-scoping guard — 'Back to Store' (different step)")
    print(f"  control  : {top(ctrl3)!r}  score={ctrl3[0][0]}")
    print(f"  treatment: {top(treat3)!r}  score={treat3[0][0]}")
    checks.append(("leg3 different step unchanged (no cross-step bleed)", top(ctrl3) == top(treat3)))

    print("\n" + "=" * 66)
    print("CHECKS")
    print("=" * 66)
    all_ok = True
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print(
        "\n"
        + (
            "VERDICT: resolver-level negative flip proven (deterministic). AI-058 gate demonstrable at the resolver level."
            if all_ok
            else "VERDICT: one or more checks failed — see above."
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
