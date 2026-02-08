import os
import tempfile
import unittest
from datetime import datetime, timezone

from evals.run_weekly_summary_eval import (
    build_eval_schema,
    compare_with_baseline,
    compute_score_coverage,
    compute_slice_scores,
    load_production_dataset,
    persist_eval_results_to_db,
    prepare_eval_item,
    run_deterministic_checks,
)
from eng_health_copilot.db import get_db


class TestEvalRunnerHelpers(unittest.TestCase):
    def _sample_item(self) -> dict:
        return {
            "id": "sample_case",
            "tags": ["sparse_data", "anomalous"],
            "metrics": {
                "pr_throughput": 0,
                "net_bug_delta": 2,
                "commits_per_week": 2,
            },
            "anomalies": [{"metric": "pr_throughput", "message": "drop", "value": 0}],
            "context": {"weekly_history": [{"commits_per_week": 2}] * 2, "recent_pull_requests": []},
            "expected": {"summary_markdown": "placeholder"},
            "rubric": {
                "format": "f",
                "grounding": "g",
                "actionable": "a",
                "uncertainty": "u",
                "hallucination": "h",
                "anomaly_handling": "an",
                "recommendation_relevance": "rr",
            },
            "expectations": {
                "must_mention": ["confidence"],
                "must_avoid": ["backlog shrank"],
                "must_include_sections": [
                    "### Weekly Engineering Summary",
                    "### High-level read",
                    "### Notable anomalies vs recent history",
                    "### Additional context and recommendations",
                ],
                "confidence_level_expected": "low",
            },
        }

    def test_schema_contains_v2_fields(self) -> None:
        schema = build_eval_schema()
        required = set(schema.get("required", []))
        self.assertIn("tags", required)
        self.assertIn("expect_confidence_level", required)
        self.assertIn("rubric_uncertainty", required)

    def test_prepare_eval_item_flattens_fields(self) -> None:
        eval_item = prepare_eval_item(self._sample_item(), "summary")
        self.assertEqual(eval_item["id"], "sample_case")
        self.assertEqual(eval_item["rubric_uncertainty"], "u")
        self.assertEqual(eval_item["expect_confidence_level"], "low")
        self.assertEqual(eval_item["output_text"], "summary")

    def test_deterministic_checks_detect_conflict(self) -> None:
        eval_item = prepare_eval_item(self._sample_item(), """
### Weekly Engineering Summary
- Throughput is down.

### High-level read
- backlog shrank despite rising bugs.

### Notable anomalies vs recent history
- throughput dropped.

### Additional context and recommendations
- clear trend that this will fix itself.
""")
        checks = run_deterministic_checks(eval_item)
        self.assertFalse(checks["all_pass"])
        self.assertIn("must_avoid", checks["failed_checks"])

    def test_slice_aggregation_and_baseline_comparison(self) -> None:
        cases = [
            {
                "id": "a",
                "tags": ["sparse_data"],
                "status": "pass",
                "scores": {
                    "format_correctness": 4.0,
                    "grounding_to_metrics": 4.0,
                    "actionable_recommendations": 4.0,
                    "uncertainty_calibration": 3.6,
                    "hallucination_guard": 3.7,
                    "anomaly_handling": 3.8,
                    "recommendation_relevance": 4.1,
                },
                "criterion_pass": {"format_correctness": True, "grounding_to_metrics": True, "actionable_recommendations": True, "uncertainty_calibration": True, "hallucination_guard": True, "anomaly_handling": True, "recommendation_relevance": True},
                "model_all_pass": True,
                "deterministic": {"all_pass": True},
                "anomaly_count": 0,
            },
            {
                "id": "b",
                "tags": ["normal_data", "anomalous"],
                "status": "pass",
                "scores": {
                    "format_correctness": 3.2,
                    "grounding_to_metrics": 3.1,
                    "actionable_recommendations": 3.4,
                    "uncertainty_calibration": 3.0,
                    "hallucination_guard": 3.2,
                    "anomaly_handling": 3.0,
                    "recommendation_relevance": 3.3,
                },
                "criterion_pass": {"format_correctness": True, "grounding_to_metrics": True, "actionable_recommendations": True, "uncertainty_calibration": True, "hallucination_guard": True, "anomaly_handling": True, "recommendation_relevance": True},
                "model_all_pass": True,
                "deterministic": {"all_pass": False},
                "anomaly_count": 1,
            },
        ]

        slice_scores = compute_slice_scores(cases)
        self.assertEqual(slice_scores["overall"]["n_cases"], 2)
        self.assertEqual(slice_scores["sparse_data"]["n_cases"], 1)

        baseline = {
            "slice_scores": {
                "overall": {"overall_average": 4.2},
                "sparse_data": {"overall_average": 4.2},
            }
        }
        comparison = compare_with_baseline(
            slice_scores,
            baseline,
            max_overall_drop=0.2,
            max_sparse_drop=0.2,
            min_critical_score=3.0,
            min_sparse_calibration=3.5,
        )
        self.assertIn("metric_deltas", comparison)
        self.assertIsInstance(comparison["soft_gate_failed"], bool)
        coverage = compute_score_coverage(cases)
        self.assertEqual(coverage["format_correctness"]["total_cases"], 2)
        self.assertEqual(coverage["format_correctness"]["scored_cases"], 2)

    def test_load_production_dataset_from_sqlite(self) -> None:
        original_db_path = os.environ.get("ENG_HEALTH_DB_PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "eng_health.db")
            os.environ["ENG_HEALTH_DB_PATH"] = db_path

            conn = get_db()
            try:
                completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                conn.execute(
                    """
                    INSERT INTO analysis_runs (
                        run_id, repo_owner, repo_name, days_back, started_at, completed_at, status,
                        duration_ms, model, temperature, data_sufficiency_level, input_hash,
                        metrics_json, anomalies_json, context_json, summary_markdown, error_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "analysis_test_1",
                        "acme",
                        "widget",
                        90,
                        completed_at,
                        completed_at,
                        "completed",
                        1234,
                        "gpt-4.1-mini",
                        0.3,
                        "low",
                        "hash1",
                        '{"pr_throughput": 1, "net_bug_delta": 2}',
                        "[]",
                        '{"weekly_history": []}',
                        "### Weekly Engineering Summary\n- test\n### High-level read\n- test\n### Additional context and recommendations\n- recommend",
                        None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            items = load_production_dataset(limit=5, since_hours=24)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["metadata"]["repo"], "acme/widget")
            self.assertIn("sparse_data", items[0]["tags"])
            self.assertIn("output_text", items[0])

        if original_db_path is None:
            os.environ.pop("ENG_HEALTH_DB_PATH", None)
        else:
            os.environ["ENG_HEALTH_DB_PATH"] = original_db_path

    def test_persist_eval_results_to_db(self) -> None:
        original_db_path = os.environ.get("ENG_HEALTH_DB_PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "eng_health.db")
            os.environ["ENG_HEALTH_DB_PATH"] = db_path

            payload = {
                "eval_id": "eval_123",
                "run_id": "evalrun_123",
                "dataset_info": {
                    "static_count": 1,
                    "production_count": 1,
                    "total_count": 2,
                    "ran_count": 2,
                    "skipped_count": 0,
                },
                "slice_scores": {
                    "overall": {"overall_average": 3.8},
                    "sparse_data": {"overall_average": 3.4, "calibration_average": 3.6},
                },
                "baseline_comparison": {"baseline_present": True, "soft_gate_failed": False},
                "results": [
                    {
                        "id": "case_a",
                        "status": "pass",
                        "tags": ["sparse_data"],
                        "scores": {"format_correctness": 4.0},
                        "criterion_pass": {"format_correctness": True},
                        "deterministic": {"all_pass": True},
                        "anomaly_count": 0,
                        "model_all_pass": True,
                    }
                ],
            }

            run_key = persist_eval_results_to_db(
                payload,
                model="gpt-4.1-mini",
                grading_model="gpt-4.1-mini",
                eval_name="weekly-summary-markdown-eval-v2",
                run_name="weekly-summary-run-v2",
                dataset_path="evals/weekly_summary_dataset_v2.jsonl",
            )
            self.assertEqual(run_key, "evalrun_123")

            conn = get_db()
            try:
                run_count = conn.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0]
                case_count = conn.execute("SELECT COUNT(*) FROM eval_case_results").fetchone()[0]
                self.assertEqual(run_count, 1)
                self.assertEqual(case_count, 1)
            finally:
                conn.close()

        if original_db_path is None:
            os.environ.pop("ENG_HEALTH_DB_PATH", None)
        else:
            os.environ["ENG_HEALTH_DB_PATH"] = original_db_path


if __name__ == "__main__":
    unittest.main()
