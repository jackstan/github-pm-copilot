from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from eng_health_copilot.orchestrator import run_full_analysis


class TestOrchestratorDaysBack(unittest.TestCase):
    @patch("eng_health_copilot.orchestrator.record_analysis_run")
    @patch("eng_health_copilot.orchestrator.get_settings")
    @patch("eng_health_copilot.orchestrator.generate_weekly_summary", return_value="summary")
    @patch("eng_health_copilot.orchestrator.get_llm_context", return_value={})
    @patch("eng_health_copilot.orchestrator.detect_anomalies", return_value=[])
    @patch("eng_health_copilot.orchestrator.get_weekly_metrics_history", return_value=pd.DataFrame())
    @patch("eng_health_copilot.orchestrator.recompute_weekly_metrics", return_value={"pr_throughput": 1})
    @patch("eng_health_copilot.orchestrator.run_ingest", return_value={"skipped": False})
    def test_days_back_scales_weeks_back(
        self,
        run_ingest_mock,
        recompute_mock,
        history_mock,
        detect_mock,
        context_mock,
        summary_mock,
        settings_mock,
        record_mock,
    ) -> None:
        settings_mock.return_value = SimpleNamespace(openai_model="gpt-4.1-mini")

        summary = run_full_analysis("acme", "widget", days_back=180)

        self.assertEqual(summary, "summary")
        run_ingest_mock.assert_called_once_with("acme", "widget", 180, force_refresh=False)
        recompute_mock.assert_called_once_with("acme", "widget", weeks_back=26)
        context_mock.assert_called_once_with("acme", "widget", weeks_back=26)
        self.assertTrue(record_mock.called)


if __name__ == "__main__":
    unittest.main()
