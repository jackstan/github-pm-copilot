import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from eng_health_copilot.llm_client import build_weekly_summary_prompts


class TestWeeklySummaryPrompts(unittest.TestCase):
    def test_prompt_contains_low_data_instruction_when_sufficiency_low(self) -> None:
        metrics = {"pr_throughput": 1}
        anomalies = []
        context = {
            "data_sufficiency": {
                "history_weeks": 2,
                "recent_pr_count": 1,
                "recent_commit_count": 4,
                "level": "low",
            }
        }

        _system_prompt, user_prompt, payload = build_weekly_summary_prompts(metrics, anomalies, context)

        self.assertIn("Data sufficiency is LOW", user_prompt)
        self.assertEqual(payload["context"]["data_sufficiency"]["level"], "low")

    def test_prompt_mentions_data_sufficiency_usage(self) -> None:
        metrics = {"pr_throughput": 5}
        anomalies = []
        context = {}

        _system_prompt, user_prompt, _payload = build_weekly_summary_prompts(metrics, anomalies, context)
        self.assertIn("Use any `context.data_sufficiency` information", user_prompt)


if __name__ == "__main__":
    unittest.main()
