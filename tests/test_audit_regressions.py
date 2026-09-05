"""Regression coverage for data integrity, degraded collection and controller limits."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import Request

from pydantic import ValidationError

from backend.analytics import assess_spread_plausibility, correlate_signals
from backend.evaluate import evaluate_replay_suite, main as evaluate_main
from backend.orchestrator import (
    BedrockDecisionClient, BioSignalOrchestrator, BudgetExceededError, Decision,
    InvalidDecisionError, ModelResult, OrchestrationError,
)
from backend.public_sources import (
    AllowListedRedirectHandler, ENVIRONMENTAL_ENDPOINTS, PublicSourceClient, PublicSourceError,
    collect_singapore_public_data, fetch_cda_bulletin, fetch_environment, fetch_nea_dengue,
    fetch_who_outbreak_news, public_bundle_to_evidence,
)
from backend.run_demo import main as demo_main
from backend.scenario_loader import load_scenario
from backend.schemas import CaseState, Confidence, Domain, Evidence, PublicDataBundle, RiskProfile, Scenario, Signal, SourceStatus
from tests.test_analytics import make_signal
from tests.test_end_to_end import FakeBedrockClient, FakeBedrockRuntime
from tests.test_public_sources import NOW, coverage, observation
from tests.test_schemas import valid_signal


class InputIntegrityTests(unittest.TestCase):
    def test_non_finite_signal_numbers_are_rejected(self):
        for field in ("observed_value", "baseline_mean", "baseline_std", "source_confidence"):
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    Signal.model_validate(valid_signal(**{field: value}))

    def test_synthetic_marker_must_be_explicit_and_boolean(self):
        for value in (None, "true", 1):
            payload = valid_signal(synthetic=value)
            if value is None:
                payload.pop("synthetic")
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Signal.model_validate(payload)

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValidationError):
            Signal.model_validate(valid_signal(timestamp=datetime(2026, 1, 1)))

    def test_duplicate_scenario_signal_cannot_inflate_support(self):
        payload = load_scenario("zoonotic_spillover").model_dump()
        payload["new_evidence_signals"].append(payload["initial_signals"][0])
        with self.assertRaises(ValidationError):
            Scenario.model_validate(payload)

    def test_public_provenance_counts_and_identifiers_are_validated(self):
        item = observation("A", "CDA-WEEKLY", Domain.HUMAN, "count", 3, 1)
        for sources, observations in (
            ([], [item]),
            ([coverage("CDA-WEEKLY", Domain.HUMAN, SourceStatus.AVAILABLE, 2)], [item]),
            ([coverage("CDA-WEEKLY", Domain.HUMAN, SourceStatus.AVAILABLE, 2)], [item, item]),
            ([coverage("CDA-WEEKLY", Domain.HUMAN, SourceStatus.UNAVAILABLE, 1)], [item]),
        ):
            with self.subTest(sources=sources), self.assertRaises(ValidationError):
                PublicDataBundle(retrieved_at=NOW, observations=observations, sources=sources)

    def test_non_finite_evidence_effect_is_rejected(self):
        with self.assertRaises(ValidationError):
            Evidence(evidence_id="A", finding="Fixture", source_ids=["A"], quality=1,
                     hypothesis_effects={"natural_zoonotic": float("nan")}, limitations="Fixture")

    def test_simultaneous_signals_do_not_establish_temporal_precedence(self):
        signals = [make_signal("A", Domain.ANIMAL, NOW), make_signal("H", Domain.HUMAN, NOW)]
        self.assertEqual(assess_spread_plausibility(signals)[0].evidence_id, "EV-SPREAD-UNRESOLVED")
        self.assertNotEqual(correlate_signals(signals)[0].evidence_id, "EV-CORR-NONE")


class SourceBoundaryTests(unittest.TestCase):
    def test_redirect_target_is_checked_before_following(self):
        handler = AllowListedRedirectHandler()
        request = Request("https://www.cda.gov.sg/resources/")
        for target in ("https://example.com/", "http://www.cda.gov.sg/", "https://www.cda.gov.sg:8080/"):
            with self.subTest(target=target), self.assertRaises(PublicSourceError):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        self.assertEqual(handler.redirect_request(
            request, None, 302, "Found", {}, "https://www.nea.gov.sg/"
        ).host, "www.nea.gov.sg")

    def test_response_size_is_bounded(self):
        client = PublicSourceClient()
        client.max_response_bytes = 3
        response = Mock()
        response.geturl.return_value = "https://www.cda.gov.sg/"
        response.read.return_value = b"1234"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("backend.public_sources.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(PublicSourceError):
                client.request_bytes("https://www.cda.gov.sg/")
        response.read.assert_called_once_with(4)

    def test_collector_failures_preserve_manifest_provenance(self):
        client = Mock(spec=PublicSourceClient)
        client.get_text.side_effect = PublicSourceError("offline")
        client.get_json.side_effect = PublicSourceError("offline")
        client.post_json.side_effect = PublicSourceError("offline")
        bundle = collect_singapore_public_data(client)
        self.assertEqual(len(bundle.sources), 9)
        avs = next(source for source in bundle.sources if source.source_id == "AVS-BIOSURVEILLANCE")
        self.assertEqual(avs.domain, Domain.ANIMAL)
        self.assertTrue(avs.url.startswith("https://avs.nparks.gov.sg/"))
        self.assertEqual(avs.status, SourceStatus.UNAVAILABLE)

    def test_one_weather_failure_preserves_other_endpoints_and_latest_readings(self):
        client = Mock(spec=PublicSourceClient)
        def get_json(url):
            if url == ENVIRONMENTAL_ENDPOINTS["air_temperature"]:
                raise PublicSourceError("offline")
            return {"data": {"readings": [
                {"timestamp": (NOW - timedelta(hours=1)).isoformat(), "data": [{"value": 99}]},
                {"timestamp": NOW.isoformat(), "data": [{"value": 2}, {"value": 4}]},
            ]}}
        client.get_json.side_effect = get_json
        observations, source = fetch_environment(client)
        self.assertEqual(len(observations), 6)
        self.assertEqual(source.status, SourceStatus.PARTIAL)
        self.assertIn("air_temperature", source.note)
        self.assertTrue(all(item.observed_at == NOW for item in observations))
        self.assertEqual(next(item.value for item in observations if item.metric == "rainfall_mean"), 3)

    def test_unknown_red_cluster_word_is_not_fabricated_as_zero(self):
        client = Mock(spec=PublicSourceClient)
        client.get_text.return_value = "12 active dengue clusters were reported, of which eleven were classified under red"
        observations, _ = fetch_nea_dengue(client)
        self.assertEqual([item.metric for item in observations], ["active_clusters"])

    def test_cda_units_baselines_and_wrapped_decimal_positivity(self):
        client = Mock(spec=PublicSourceClient)
        client.get_text.return_value = '<a href="https://isomer-user-content.by.gov.sg/test.pdf">2026_week_34</a>'
        client.request_bytes.return_value = b"mock PDF"
        reader = Mock()
        reader.pages = [Mock(), Mock()]
        reader.pages[0].extract_text.return_value = (
            "EPIDEMIOLOGICAL WEEK 34 23 - 29 Aug 2026\n"
            "Dengue Fever 1,234 47 185 2157 3216\n"
            "Chickenpox 4 6 6\n"
            "Severe Acute Respiratory Syndrome 0 0 0 0 0\n"
        )
        reader.pages[1].extract_text.return_value = "The positivity rate for\nCOVID-19 among ARI samples was 2.5%"
        with patch("pypdf.PdfReader", return_value=reader), patch("backend.public_sources._now", return_value=NOW):
            observations, source = fetch_cda_bulletin(client)
        by_metric = {item.metric: item for item in observations}
        self.assertEqual(by_metric["dengue_fever"].value, 1234)
        self.assertEqual(by_metric["dengue_fever"].baseline_value, 185)
        self.assertEqual(by_metric["dengue_fever"].unit, "weekly notifications")
        self.assertEqual(by_metric["chickenpox"].unit, "average daily attendances")
        self.assertEqual(by_metric["severe_acute_respiratory_syndrome"].unit, "weekly notifications")
        self.assertEqual(by_metric["covid_ari_positivity"].value, 2.5)
        self.assertEqual(source.observation_count, 4)

    def test_regional_country_matching_uses_word_boundaries(self):
        client = Mock(spec=PublicSourceClient)
        client.get_json.return_value = {"value": [{
            "Title": "Outbreak in the Indian Ocean", "Overview": "A global update", "Id": "A",
            "PublicationDateAndTime": NOW.isoformat(), "UrlName": "test",
        }]}
        observations, _ = fetch_who_outbreak_news(client)
        self.assertEqual(observations[0].metric, "global_outbreak_report")

    def test_future_food_notice_is_not_counted_as_recent(self):
        item = observation("A", "SFA-ALERTS", Domain.FOOD, "food_alert", 1)
        item.observed_at = NOW + timedelta(days=1)
        bundle = PublicDataBundle(retrieved_at=NOW, observations=[item], sources=[
            coverage("SFA-ALERTS", Domain.FOOD, SourceStatus.AVAILABLE, 1)
        ])
        finding = next(item.finding for item in public_bundle_to_evidence(bundle) if item.evidence_id == "EV-PUBLIC-SFA-ALERTS")
        self.assertIn("0 SFA food alert(s)", finding)


class ControllerBoundaryTests(unittest.TestCase):
    def test_invalid_limits_are_rejected_before_client_initialisation(self):
        for options in ({"max_model_calls": 0}, {"max_tool_calls": -1}, {"max_output_tokens": True},
                        {"session_budget_usd": float("nan")}, {"session_budget_usd": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                BioSignalOrchestrator(**options)

    def test_empty_public_snapshot_is_low_confidence_and_needs_verification(self):
        profile = BioSignalOrchestrator().run_public(PublicDataBundle(retrieved_at=NOW))
        self.assertEqual(profile.confidence, Confidence.LOW)
        self.assertEqual(profile.status.value, "verify")
        self.assertEqual([record.tool_name for record in profile.tool_trace], ["recommend_next_check"])
        self.assertFalse(any(item.evidence_id.startswith("EV-CORR") for item in profile.known_findings))
        self.assertIn("AVS", profile.recommended_verification[0])

    def test_initial_public_fallback_is_reported(self):
        with patch.object(BioSignalOrchestrator, "_make_client", side_effect=RuntimeError("offline")):
            orchestrator = BioSignalOrchestrator(mode="live", fallback_to_replay=True)
        self.assertTrue(orchestrator.run_public(PublicDataBundle(retrieved_at=NOW)).metrics.fallback_used)

    def test_failed_model_call_is_counted_and_reused_fallback_stays_visible(self):
        client = Mock(model_id="failed-model")
        client.choose.side_effect = InvalidDecisionError("invalid output", 100, 20)
        orchestrator = BioSignalOrchestrator(mode="live", decision_client=client, fallback_to_replay=True)
        for calls in (1, 0):
            profile = orchestrator.run(load_scenario("zoonotic_spillover"))
            self.assertTrue(profile.metrics.fallback_used)
            self.assertEqual(profile.metrics.model_calls, calls)
            self.assertEqual(profile.metrics.input_tokens, calls * 100)

    def test_model_limit_can_finish_checks_through_replay(self):
        orchestrator = BioSignalOrchestrator(mode="live", decision_client=FakeBedrockClient(),
                                            max_model_calls=1, fallback_to_replay=True)
        profile = orchestrator.run(load_scenario("contradictory_evidence"))
        self.assertEqual(profile.metrics.model_calls, 1)
        self.assertTrue(profile.metrics.fallback_used)
        self.assertIn("verify_external_report", [record.tool_name for record in profile.tool_trace])

    def test_exhausted_model_limit_without_fallback_does_not_return_incomplete_profile(self):
        orchestrator = BioSignalOrchestrator(mode="live", decision_client=FakeBedrockClient(),
                                            max_model_calls=1, fallback_to_replay=False)
        with self.assertRaises(OrchestrationError):
            orchestrator.run(load_scenario("zoonotic_spillover"))

    def test_unavailable_tool_is_never_executed(self):
        client = Mock(model_id="invalid-model")
        client.choose.return_value = ModelResult(Decision("recommend_next_check", {"rationale": "Skip checks"}), 1, 1)
        orchestrator = BioSignalOrchestrator(mode="live", decision_client=client, fallback_to_replay=False)
        with patch.object(orchestrator, "_execute_tool") as execute:
            with self.assertRaises(OrchestrationError):
                orchestrator.run(load_scenario("zoonotic_spillover"))
            execute.assert_not_called()

    def test_budget_preflight_prevents_model_request(self):
        client = Mock(model_id="model")
        orchestrator = BioSignalOrchestrator(mode="live", decision_client=client, session_budget_usd=0.000001)
        with self.assertRaises(BudgetExceededError):
            orchestrator.run(load_scenario("zoonotic_spillover"))
        client.choose.assert_not_called()

    def test_bedrock_request_omits_unsupported_sampling_parameter(self):
        client = object.__new__(BedrockDecisionClient)
        client._client = FakeBedrockRuntime()
        client.model_id = "global.anthropic.claude-sonnet-5"
        client.max_output_tokens = 300
        client.choose({}, ["correlate_signals"])
        self.assertNotIn("temperature", client._client.request["inferenceConfig"])
        self.assertEqual(client._client.request["toolConfig"]["toolChoice"], {"auto": {}})

    def test_packet_contains_provenance(self):
        scenario = load_scenario("zoonotic_spillover")
        profile = BioSignalOrchestrator().run(scenario)
        state = CaseState(case_id="A", scenario_id=scenario.scenario_id, scenario_title=scenario.title,
                          signals=scenario.initial_signals, evidence=profile.known_findings)
        packet = BioSignalOrchestrator()._packet(state)
        self.assertTrue(all(item["source_ids"] for item in packet["evidence"]))


class CommandAndBaselineTests(unittest.TestCase):
    def test_example_is_a_valid_current_risk_profile(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "sample_risk_profile.json"
        example = RiskProfile.model_validate_json(path.read_text(encoding="utf-8"))
        current = BioSignalOrchestrator().run(load_scenario(example.scenario_id))
        self.assertEqual(example.hypotheses, current.hypotheses)
        self.assertEqual(example.recommended_verification, current.recommended_verification)

    def test_committed_evaluation_matches_current_replay(self):
        path = Path(__file__).resolve().parents[1] / "evals" / "replay_baseline.json"
        self.assertEqual(evaluate_replay_suite(), json.loads(path.read_text(encoding="utf-8")))

    def test_evaluation_failure_sets_nonzero_exit_status(self):
        report = evaluate_replay_suite()
        report["summary"]["expected_status_match_rate"] = 0.5
        with patch("sys.argv", ["evaluate"]), patch("backend.evaluate.evaluate_replay_suite", return_value=report), patch("builtins.print"):
            self.assertEqual(evaluate_main(), 1)

    def test_invalid_cli_combinations_do_not_start_collection(self):
        for args in (["--snapshot-output", "output/a.json"], ["--public-data", "--include-new-evidence"],
                     ["--public-data", "--output", "output/a.json", "--snapshot-output", "output/a.json"]):
            with self.subTest(args=args), patch("sys.argv", ["run_demo", *args]), patch("sys.stderr"), patch("backend.run_demo.BioSignalOrchestrator") as orchestrator:
                with self.assertRaises(SystemExit) as result:
                    demo_main()
                self.assertEqual(result.exception.code, 2)
                orchestrator.assert_not_called()
