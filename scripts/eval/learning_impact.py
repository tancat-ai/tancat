#!/usr/bin/env python3
"""AI-059 learning-impact metric and controlled baseline harness.

Phase 1 (read-only):
    python scripts/eval/learning_impact.py metrics --evidence-dir evidence

Phase 2 (same command, store-only variable):
    python scripts/eval/learning_impact.py baseline \
        --store-target evidence/rag_store.db \
        --cold-snapshot lab/stores/golden.db \
        --warm-positive-snapshot lab/stores/golden-positive.db \
        --command python -m pytest generated_tests/{leg}

The command receives ``AI059_EVIDENCE_DIR`` and ``AI059_LEG`` in its
environment.  Prefer ``{evidence_dir}`` in a command argument when the test
fixture needs an explicit output directory.  Auto-learning is disabled by the
runner; RAG reading remains enabled for warm legs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.learning_impact import BaselineLeg, ControlledBaselineRunner  # noqa: E402
from src.learning_metrics import analyze_sidecars  # noqa: E402


def _metrics_command(args: argparse.Namespace) -> int:
    metrics = analyze_sidecars(args.evidence_dir, include_invalid=args.include_invalid)
    payload = metrics.to_dict(include_per_test=not args.compact)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _baseline_command(args: argparse.Namespace) -> int:
    if not args.command:
        raise SystemExit("baseline requires a command after --command")
    legs = [BaselineLeg("cold", args.cold_snapshot)]
    if args.warm_positive_snapshot is not None:
        legs.append(BaselineLeg("warm-positive", args.warm_positive_snapshot))
    if args.warm_positive_negative_snapshot is not None:
        legs.append(BaselineLeg("warm-positive-negative", args.warm_positive_negative_snapshot))
    metadata = {
        key: value
        for key, value in {
            "pipeline": args.pipeline,
            "pom_mode": args.pom_mode,
            "provider": args.provider,
            "model": args.model,
            "temperature": args.temperature,
            "thinking": args.thinking,
        }.items()
        if value is not None
    }
    runner = ControlledBaselineRunner(
        evidence_root=args.evidence_root,
        output_root=args.output_root,
        store_target=args.store_target,
        cwd=args.cwd,
        timeout_s=args.timeout,
        metadata=metadata,
    )
    report = runner.run(args.command, legs)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if all(leg.succeeded for leg in report.legs) else 1


def _rebuild_warm_command(args: argparse.Namespace) -> int:
    from src.learning_impact import (
        build_lab_identity,
        lab_site_hash,
        rebuild_warm_store_from_evidence,
    )
    from src.rag_store import MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder

    if args.site or args.input_version or args.story_set:
        identity = build_lab_identity(
            site=args.site or "",
            input_version=args.input_version or "",
            story_set=args.story_set or "",
        )
    else:
        identity = args.lab_identity
    embedder = SentenceTransformerEmbedder()
    backend = MilvusLiteBackend(
        str(args.store_target),
        embedder.dimension,
        embedder_identity=embedder.identity,
    )
    store = RAGStore(backend, embedder)
    result = rebuild_warm_store_from_evidence(
        args.evidence_dir,
        store=store,
        lab_site_identity=identity,
    )
    payload = {
        "lab_site_identity": identity,
        "sentinel_site_hash": lab_site_hash(identity),
        **result,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-059 evidence metrics and controlled baseline runner")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    metrics = subparsers.add_parser("metrics", help="analyze existing evidence sidecars (read-only)")
    metrics.add_argument("--evidence-dir", type=Path, required=True)
    metrics.add_argument("--output", type=Path)
    metrics.add_argument("--compact", action="store_true", help="omit per-test records")
    metrics.add_argument("--include-invalid", action="store_true")
    metrics.set_defaults(handler=_metrics_command)

    baseline = subparsers.add_parser("baseline", help="run cold/warm legs with store isolation")
    baseline.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    baseline.add_argument("--evidence-root", type=Path, default=Path("lab/evidence"))
    baseline.add_argument("--output-root", type=Path, default=Path("lab/learning-impact"))
    baseline.add_argument("--store-target", type=Path)
    baseline.add_argument("--cold-snapshot", type=Path, required=True)
    baseline.add_argument("--warm-positive-snapshot", type=Path)
    baseline.add_argument("--warm-positive-negative-snapshot", type=Path)
    baseline.add_argument("--cwd", type=Path)
    baseline.add_argument("--timeout", type=float, default=1800.0)
    baseline.add_argument("--pipeline", choices=("linear", "graph"))
    baseline.add_argument("--pom-mode", action="store_true", default=None)
    baseline.add_argument("--provider")
    baseline.add_argument("--model")
    baseline.add_argument("--temperature", type=float)
    baseline.add_argument("--thinking", choices=("on", "off"))
    baseline.set_defaults(handler=_baseline_command)

    rebuild = subparsers.add_parser(
        "rebuild-warm",
        help="re-derive a sentinel-scoped warm RAG store from evidence sidecars",
    )
    rebuild.add_argument("--evidence-dir", type=Path, required=True)
    rebuild.add_argument("--store-target", type=Path, required=True)
    rebuild.add_argument("--lab-identity", default="ai059-lab:ecommerce")
    rebuild.add_argument("--site", help="compose a structured identity from components")
    rebuild.add_argument("--input-version", help="site/edit version, e.g. v1/v2")
    rebuild.add_argument("--story-set", help="story-set label for this cell")
    rebuild.set_defaults(handler=_rebuild_warm_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
