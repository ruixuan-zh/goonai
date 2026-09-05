"""Run the deterministic BIO-SIGNAL regression evaluation suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .orchestrator import BioSignalOrchestrator
from .scenario_loader import available_scenarios, load_scenario
from .schemas import ActionStatus


def evaluate_replay_suite() -> dict[str, Any]:
    """Evaluate every curated scenario without network or model dependencies."""

    scenario_results: list[dict[str, Any]] = []
    tool_attempts = 0
    successful_tool_calls = 0
    tool_calls_with_rationale = 0
    evidence_records = 0
    evidence_with_provenance = 0
    limit_violations = 0
    automatic_actions = 0
    completed_recommendations = 0

    for scenario_name in available_scenarios():
        scenario = load_scenario(scenario_name)
        profile = BioSignalOrchestrator(mode="replay").run(scenario)
        hypothesis_match = profile.leading_hypothesis == scenario.expected_leading_hypothesis
        status_match = profile.status == scenario.expected_status
        completed = profile.metrics.completed_within_limits

        tool_attempts += len(profile.tool_trace)
        successful_tool_calls += sum(record.success for record in profile.tool_trace)
        tool_calls_with_rationale += sum(
            bool(record.tool_input.get("rationale")) for record in profile.tool_trace
        )
        evidence_records += len(profile.known_findings)
        evidence_with_provenance += sum(bool(item.source_ids) for item in profile.known_findings)
        limit_violations += int(not completed)
        automatic_actions += sum(
            action.status != ActionStatus.PENDING for action in profile.proposed_actions
        )
        completed_recommendations += int(bool(profile.recommended_verification))

        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "expected_leading_hypothesis": scenario.expected_leading_hypothesis.value,
                "actual_leading_hypothesis": profile.leading_hypothesis.value,
                "expected_status": scenario.expected_status.value,
                "actual_status": profile.status.value,
                "hypothesis_match": hypothesis_match,
                "status_match": status_match,
                "completed_within_limits": completed,
                "tool_calls": profile.metrics.tool_calls,
                "model_calls": profile.metrics.model_calls,
                "estimated_cost_usd": profile.metrics.estimated_cost_usd,
                "recommended_verification": profile.recommended_verification[0],
            }
        )

    scenario_count = len(scenario_results)

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "evaluation_mode": "deterministic_replay",
        "scope_note": (
            "Regression results on hand-authored synthetic scenarios; these are not clinical "
            "accuracy, epidemiological validation, or calibrated attack-attribution metrics."
        ),
        "scenario_count": scenario_count,
        "summary": {
            "expected_hypothesis_match_rate": rate(
                sum(item["hypothesis_match"] for item in scenario_results), scenario_count
            ),
            "expected_status_match_rate": rate(
                sum(item["status_match"] for item in scenario_results), scenario_count
            ),
            "task_completion_rate": rate(
                sum(item["completed_within_limits"] for item in scenario_results), scenario_count
            ),
            "tool_call_success_rate": rate(successful_tool_calls, tool_attempts),
            "tool_rationale_completeness_rate": rate(tool_calls_with_rationale, tool_attempts),
            "verification_recommendation_rate": rate(completed_recommendations, scenario_count),
            "evidence_provenance_completeness_rate": rate(
                evidence_with_provenance, evidence_records
            ),
            "limit_violation_count": limit_violations,
            "automatic_action_count": automatic_actions,
        },
        "scenarios": scenario_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate all curated BIO-SIGNAL scenarios")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = evaluate_replay_suite()
    serialised = json.dumps(report, indent=2)
    print(serialised)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")
        print(f"Wrote: {args.output.resolve()}")
    summary = report["summary"]
    rates = [value for name, value in summary.items() if name.endswith("_rate")]
    return 0 if report["scenario_count"] and all(value == 1.0 for value in rates) and not (
        summary["limit_violation_count"] or summary["automatic_action_count"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
