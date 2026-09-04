from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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
        self.assertTrue(any(header.value == "Agent trace" for header in app.subheader))


if __name__ == "__main__":
    unittest.main()
