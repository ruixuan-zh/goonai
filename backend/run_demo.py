"""Command-line entry point for a reproducible BIO-SIGNAL demonstration."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Replay mode deliberately works without optional dependencies.
    load_dotenv = None

from .orchestrator import BioSignalOrchestrator
from .public_sources import collect_singapore_public_data
from .scenario_loader import available_scenarios, load_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded BIO-SIGNAL scenario")
    parser.add_argument(
        "--scenario",
        choices=available_scenarios(),
        default="zoonotic_spillover",
        help="Synthetic scenario to investigate",
    )
    parser.add_argument(
        "--mode",
        choices=("replay", "live"),
        default="replay",
        help="Replay is keyless; live uses Amazon Bedrock",
    )
    parser.add_argument(
        "--include-new-evidence",
        action="store_true",
        help="Include the scenario's evidence-injection packet",
    )
    parser.add_argument(
        "--public-data",
        action="store_true",
        help="Collect current Singapore public sources instead of a curated scenario",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        help="Optional path for the full normalised public-data snapshot",
    )
    return parser


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()
    args = build_parser().parse_args()
    orchestrator = BioSignalOrchestrator(mode=args.mode)
    if args.public_data:
        bundle = collect_singapore_public_data()
        profile = orchestrator.run_public(bundle)
        print(
            f"Public data: {len(bundle.observations)} observation(s), "
            f"{len(bundle.sources)} registered source(s)"
        )
        if args.snapshot_output:
            args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot_output.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
            print(f"Wrote public snapshot: {args.snapshot_output.resolve()}")
    else:
        scenario = load_scenario(args.scenario)
        profile = orchestrator.run(scenario, include_new_evidence=args.include_new_evidence)

    print(f"Case: {profile.case_id}")
    print(f"Status: {profile.status.value}")
    print(f"Leading hypothesis: {profile.leading_hypothesis.value}")
    print(f"Confidence: {profile.confidence.value}")
    print(f"Evidence records: {len(profile.known_findings)}")
    print(
        "Run limits: "
        f"{profile.metrics.model_calls} model call(s), "
        f"{profile.metrics.tool_calls} tool call(s), "
        f"estimated US${profile.metrics.estimated_cost_usd:.4f}"
    )
    print("Human approval required for all proposed actions.")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
