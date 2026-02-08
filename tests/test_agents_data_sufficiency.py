import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from eng_health_copilot.agents import compute_data_sufficiency, generate_weekly_summary


class TestDataSufficiency(unittest.TestCase):
    def test_low_when_history_is_short(self) -> None:
        metrics = {"commits_per_week": 12}
        context = {"weekly_history": [{"commits_per_week": 12}] * 3, "recent_pull_requests": [{}, {}, {}]}
        suff = compute_data_sufficiency(metrics, context)
        self.assertEqual(suff["level"], "low")

    def test_low_when_prs_and_commits_are_both_low(self) -> None:
        metrics = {"commits_per_week": 5}
        context = {"weekly_history": [{"commits_per_week": 2}] * 8, "recent_pull_requests": [{}]}
        suff = compute_data_sufficiency(metrics, context)
        self.assertEqual(suff["level"], "low")

    def test_medium_when_history_under_eight(self) -> None:
        metrics = {"commits_per_week": 20}
        context = {"weekly_history": [{"commits_per_week": 20}] * 6, "recent_pull_requests": [{}] * 9}
        suff = compute_data_sufficiency(metrics, context)
        self.assertEqual(suff["level"], "medium")

    def test_high_when_history_and_activity_are_strong(self) -> None:
        metrics = {"commits_per_week": 32}
        context = {"weekly_history": [{"commits_per_week": 30}] * 10, "recent_pull_requests": [{}] * 10}
        suff = compute_data_sufficiency(metrics, context)
        self.assertEqual(suff["level"], "high")

    @patch("eng_health_copilot.agents.generate_weekly_summary_llm", return_value=None)
    def test_fallback_summary_mentions_low_confidence_for_sparse_data(self, _mock_llm: object) -> None:
        metrics = {
            "pr_throughput": 0,
            "pr_lead_time_p50": None,
            "pr_lead_time_p90": None,
            "open_bugs_count": 0,
            "wip_prs": 0,
            "aging_prs_7d_plus": 0,
            "net_bug_delta": 0,
            "commits_per_week": 1,
            "active_contributors_per_week": 1,
        }
        context = {
            "weekly_history": [{"commits_per_week": 1}],
            "recent_pull_requests": [],
            "recent_ci_statuses": [],
            "recent_releases": [],
        }

        summary = generate_weekly_summary(metrics, anomalies=[], context=context)
        self.assertIn("Data confidence is low", summary)
        self.assertIn("### Additional context and recommendations", summary)


if __name__ == "__main__":
    unittest.main()
