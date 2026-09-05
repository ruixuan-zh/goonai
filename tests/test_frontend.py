from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit is not installed")
class FrontendSmokeTests(unittest.TestCase):
    def test_app_loads_and_runs_replay_investigation(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
        app = AppTest.from_file(str(app_path)).run(timeout=15)
        self.assertFalse(app.exception)
        app = app.radio[0].set_value("Curated scenario").run(timeout=15)
        start_button = next(button for button in app.button if button.label == "Start investigation")
        app = start_button.click().run(timeout=15)
        self.assertFalse(app.exception)
        self.assertTrue(any(metric.label == "Case status" for metric in app.metric))
        self.assertTrue(any(header.value == "Agent trace" for header in app.header))

    def test_evidence_can_only_be_injected_once_per_investigation(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
        app = AppTest.from_file(str(app_path)).run(timeout=15)
        app.radio[0].set_value("Curated scenario").run()
        next(button for button in app.button if button.label == "Start investigation").click().run()
        next(button for button in app.button if button.label == "Inject new synthetic evidence").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(next(button for button in app.button if button.label == "Inject new synthetic evidence").disabled)
        next(button for button in app.button if button.label == "Start investigation").click().run()
        self.assertFalse(next(button for button in app.button if button.label == "Inject new synthetic evidence").disabled)

    def test_failed_public_refresh_preserves_matching_snapshot_and_hides_old_result(self) -> None:
        from streamlit.testing.v1 import AppTest
        from backend.schemas import PublicDataBundle
        from tests.test_public_sources import NOW

        app_path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
        app = AppTest.from_file(str(app_path)).run(timeout=15)
        bundle = PublicDataBundle(retrieved_at=NOW)
        with patch("backend.public_sources.collect_singapore_public_data", return_value=bundle):
            next(button for button in app.button if button.label == "Start investigation").click().run()
        previous = app.session_state.profile.case_id
        with patch("backend.public_sources.collect_singapore_public_data", return_value=PublicDataBundle(retrieved_at=NOW)), patch(
            "backend.orchestrator.BioSignalOrchestrator.run_public", side_effect=RuntimeError("test failure")
        ):
            next(button for button in app.button if button.label == "Start investigation").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(app.metric)
        self.assertEqual(app.session_state.profile.case_id, previous)
        self.assertIs(app.session_state.public_bundle, bundle)

    def test_source_switch_hides_previous_result_and_approval_is_recorded(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
        app = AppTest.from_file(str(app_path)).run(timeout=15)
        app.radio[0].set_value("Curated scenario").run()
        next(button for button in app.button if button.label == "Start investigation").click().run()
        next(button for button in app.button if button.label == "Approve").click().run()
        self.assertEqual(app.session_state.profile.proposed_actions[0].status.value, "approved")
        app.radio[0].set_value("Singapore public data").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)


if __name__ == "__main__":
    unittest.main()
