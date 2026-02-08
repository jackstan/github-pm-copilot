import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI

from eng_health_copilot.agents import compute_data_sufficiency
from eng_health_copilot.config import get_settings
from eng_health_copilot.db import get_db, get_db_path, read_sql_query
from eng_health_copilot.llm_client import build_weekly_summary_prompts

DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 900
POLL_INTERVAL_S = 2
TERMINAL_STATUSES = {"completed", "failed", "canceled", "cancelled"}

SECTION_WEEKLY = "### Weekly Engineering Summary"
SECTION_READ = "### High-level read"
SECTION_ANOMALIES = "### Notable anomalies vs recent history"
SECTION_CONTEXT = "### Additional context and recommendations"

ALL_CRITERIA = [
    "format_correctness",
    "grounding_to_metrics",
    "actionable_recommendations",
    "uncertainty_calibration",
    "hallucination_guard",
    "anomaly_handling",
    "recommendation_relevance",
]
CRITICAL_CRITERIA = [
    "format_correctness",
    "grounding_to_metrics",
    "uncertainty_calibration",
    "hallucination_guard",
    "recommendation_relevance",
]
CALIBRATION_CRITERIA = [
    "uncertainty_calibration",
    "hallucination_guard",
    "anomaly_handling",
]
DEFAULT_PASS_THRESHOLD = 3.0
PRODUCTION_BASE_TAG = "production"

PRODUCTION_RUBRIC = {
    "format": (
        "Include markdown sections with clear bullets. Required flow: Weekly Engineering Summary, "
        "High-level read, and Additional context and recommendations. Include anomalies section when anomaly signals exist."
    ),
    "grounding": "Ground all claims in provided metrics and context; avoid unsupported numeric or causal claims.",
    "actionable": "Provide 3-5 concrete recommendations tied to observed bottlenecks.",
    "uncertainty": (
        "Calibrate confidence to data sufficiency. With sparse data, explicitly state lower confidence "
        "and avoid strong trend claims."
    ),
    "hallucination": "Do not invent incidents, releases, CI trends, or metric movements not present in input.",
    "anomaly_handling": "Represent anomaly signals accurately; do not fabricate anomaly interpretation when none are present.",
    "recommendation_relevance": "Recommendations should map directly to metrics/context bottlenecks.",
}


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                items.append(json.loads(line))
    return items


def _as_str_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        if isinstance(value, str):
            out.append(value)
    return out


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def validate_dataset_item(item: Dict[str, Any]) -> None:
    required_keys = ["id", "metrics", "anomalies", "context", "expected", "rubric", "tags", "expectations"]
    missing = [k for k in required_keys if k not in item]
    if missing:
        raise ValueError(f"Dataset item missing required keys {missing}: {item.get('id', 'unknown')}")

    rubric = item.get("rubric") or {}
    rubric_keys = [
        "format",
        "grounding",
        "actionable",
        "uncertainty",
        "hallucination",
        "anomaly_handling",
        "recommendation_relevance",
    ]
    missing_rubrics = [k for k in rubric_keys if k not in rubric]
    if missing_rubrics:
        raise ValueError(
            f"Dataset item missing rubric keys {missing_rubrics}: {item.get('id', 'unknown')}"
        )

    expectations = item.get("expectations") or {}
    if expectations.get("confidence_level_expected") not in {"high", "medium", "low"}:
        raise ValueError(
            "Dataset item must set expectations.confidence_level_expected to one of high/medium/low: "
            f"{item.get('id', 'unknown')}"
        )


def _parse_db_json(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _production_expectations(
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    confidence_level: str,
) -> Dict[str, Any]:
    must_mention = ["recommend"]
    if metrics.get("pr_throughput") is not None:
        must_mention.append("throughput")
    if metrics.get("pr_lead_time_p90") is not None:
        must_mention.append("lead time")

    must_avoid: List[str] = []
    net_bug_delta = _to_float(metrics.get("net_bug_delta"))
    if net_bug_delta is not None and net_bug_delta > 0:
        must_avoid.append("backlog shrank")
    if net_bug_delta is not None and net_bug_delta < 0:
        must_avoid.append("backlog grew")

    sections = [SECTION_WEEKLY, SECTION_READ]
    if anomalies:
        sections.append(SECTION_ANOMALIES)
    sections.append(SECTION_CONTEXT)

    if confidence_level not in {"high", "medium", "low"}:
        confidence_level = "medium"

    return {
        "must_mention": must_mention,
        "must_avoid": must_avoid,
        "must_include_sections": sections,
        "confidence_level_expected": confidence_level,
    }


def load_production_dataset(limit: int, since_hours: int) -> List[Dict[str, Any]]:
    backend = os.getenv("DATABASE_URL", "").strip()
    if not backend and not get_db_path().exists():
        return []

    conn = get_db()
    try:
        since_dt = datetime.utcnow() - timedelta(hours=max(0, since_hours))
        since_iso = since_dt.replace(microsecond=0).isoformat() + "Z"
        rows_df = read_sql_query(
            """
            SELECT
                run_id,
                repo_owner,
                repo_name,
                data_sufficiency_level,
                metrics_json,
                anomalies_json,
                context_json,
                summary_markdown,
                completed_at
            FROM analysis_runs
            WHERE status = 'completed'
              AND summary_markdown IS NOT NULL
              AND LENGTH(TRIM(summary_markdown)) > 0
              AND completed_at >= ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            conn,
            params=(since_iso, max(1, limit)),
        )
    finally:
        conn.close()

    dataset: List[Dict[str, Any]] = []
    for row in rows_df.to_dict(orient="records"):
        metrics = _parse_db_json(row.get("metrics_json"), {})
        anomalies = _parse_db_json(row.get("anomalies_json"), [])
        context = _parse_db_json(row.get("context_json"), {})

        confidence_level = str(row.get("data_sufficiency_level") or "").lower()
        if confidence_level not in {"high", "medium", "low"}:
            computed = compute_data_sufficiency(metrics, context)
            confidence_level = str(computed.get("level") or "medium")

        tags = [PRODUCTION_BASE_TAG]
        if confidence_level == "low":
            tags.append("sparse_data")
        else:
            tags.append("normal_data")
        tags.append("anomalous" if anomalies else "no_anomalies")

        run_id = str(row.get("run_id") or "")
        owner = str(row.get("repo_owner") or "")
        repo = str(row.get("repo_name") or "")
        completed_at = str(row.get("completed_at") or "")

        item = {
            "id": f"prod::{owner}/{repo}::{run_id}",
            "tags": tags,
            "metrics": metrics,
            "anomalies": anomalies,
            "context": context,
            "expected": {"summary_markdown": ""},
            "rubric": dict(PRODUCTION_RUBRIC),
            "expectations": _production_expectations(metrics, anomalies, confidence_level),
            "output_text": row["summary_markdown"],
            "metadata": {
                "source": "analysis_runs",
                "run_id": run_id,
                "repo": f"{owner}/{repo}",
                "completed_at": completed_at,
            },
        }
        dataset.append(item)

    return dataset


def build_eval_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "metrics": {"type": "object"},
            "anomalies": {"type": "array"},
            "anomaly_count": {"type": "integer"},
            "context": {"type": "object"},
            "output_text": {"type": "string"},
            "expected_summary_markdown": {"type": "string"},
            "rubric_format": {"type": "string"},
            "rubric_grounding": {"type": "string"},
            "rubric_actionable": {"type": "string"},
            "rubric_uncertainty": {"type": "string"},
            "rubric_hallucination": {"type": "string"},
            "rubric_anomaly_handling": {"type": "string"},
            "rubric_recommendation_relevance": {"type": "string"},
            "expect_must_mention": {"type": "array", "items": {"type": "string"}},
            "expect_must_avoid": {"type": "array", "items": {"type": "string"}},
            "expect_must_include_sections": {"type": "array", "items": {"type": "string"}},
            "expect_confidence_level": {"type": "string"},
        },
        "required": [
            "id",
            "tags",
            "metrics",
            "anomalies",
            "anomaly_count",
            "context",
            "output_text",
            "expected_summary_markdown",
            "rubric_format",
            "rubric_grounding",
            "rubric_actionable",
            "rubric_uncertainty",
            "rubric_hallucination",
            "rubric_anomaly_handling",
            "rubric_recommendation_relevance",
            "expect_must_mention",
            "expect_must_avoid",
            "expect_must_include_sections",
            "expect_confidence_level",
        ],
    }


def _score_model_criterion(
    name: str,
    model: str,
    rubric_field: str,
    system_instruction: str,
) -> Dict[str, Any]:
    return {
        "type": "score_model",
        "name": name,
        "model": model,
        "range": [1, 5],
        "pass_threshold": DEFAULT_PASS_THRESHOLD,
        "sampling_params": {"temperature": 0},
        "input": [
            {"role": "system", "content": system_instruction},
            {
                "role": "user",
                "content": (
                    "Score this output from 1 to 5. "
                    f"Use this rubric: {{{{item.{rubric_field}}}}}\n\n"
                    "Model output:\n{{item.output_text}}\n\n"
                    "Return only a single integer score from 1 to 5."
                ),
            },
        ],
    }


def build_grading_criteria(grading_model: str) -> List[Dict[str, Any]]:
    return [
        _score_model_criterion(
            name="format_correctness",
            model=grading_model,
            rubric_field="rubric_format",
            system_instruction="You are a strict grader for markdown formatting and structure.",
        ),
        _score_model_criterion(
            name="grounding_to_metrics",
            model=grading_model,
            rubric_field="rubric_grounding",
            system_instruction="You are a strict grader for data grounding and factuality.",
        ),
        _score_model_criterion(
            name="actionable_recommendations",
            model=grading_model,
            rubric_field="rubric_actionable",
            system_instruction="You are a strict grader for actionable, concrete recommendations.",
        ),
        _score_model_criterion(
            name="uncertainty_calibration",
            model=grading_model,
            rubric_field="rubric_uncertainty",
            system_instruction="You are a strict grader for confidence calibration, especially with sparse data.",
        ),
        _score_model_criterion(
            name="hallucination_guard",
            model=grading_model,
            rubric_field="rubric_hallucination",
            system_instruction="You are a strict grader for unsupported or fabricated claims.",
        ),
        _score_model_criterion(
            name="anomaly_handling",
            model=grading_model,
            rubric_field="rubric_anomaly_handling",
            system_instruction="You are a strict grader for anomaly interpretation and section handling.",
        ),
        _score_model_criterion(
            name="recommendation_relevance",
            model=grading_model,
            rubric_field="rubric_recommendation_relevance",
            system_instruction="You are a strict grader for recommendation relevance to observed bottlenecks.",
        ),
    ]


def _enrich_context_for_prompt(metrics: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(context or {})
    if "data_sufficiency" not in enriched:
        enriched["data_sufficiency"] = compute_data_sufficiency(metrics, enriched)
    return enriched


def generate_summary(
    client: OpenAI,
    model: str,
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    prompt_context = _enrich_context_for_prompt(metrics, context)
    system_prompt, user_prompt, _payload = build_weekly_summary_prompts(metrics, anomalies, prompt_context)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    return (resp.choices[0].message.content or "").strip()


def prepare_eval_item(item: Dict[str, Any], summary: str) -> Dict[str, Any]:
    rubric = item.get("rubric", {})
    expectations = item.get("expectations", {})
    required_sections = _as_str_list(expectations.get("must_include_sections")) or [
        SECTION_WEEKLY,
        SECTION_READ,
        SECTION_CONTEXT,
    ]
    return {
        "id": item.get("id"),
        "tags": _as_str_list(item.get("tags")),
        "metrics": item.get("metrics", {}),
        "anomalies": item.get("anomalies", []),
        "anomaly_count": len(item.get("anomalies", [])),
        "context": item.get("context", {}),
        "output_text": summary,
        "expected_summary_markdown": (item.get("expected", {}) or {}).get("summary_markdown", ""),
        "rubric_format": rubric.get("format", ""),
        "rubric_grounding": rubric.get("grounding", ""),
        "rubric_actionable": rubric.get("actionable", ""),
        "rubric_uncertainty": rubric.get("uncertainty", ""),
        "rubric_hallucination": rubric.get("hallucination", ""),
        "rubric_anomaly_handling": rubric.get("anomaly_handling", ""),
        "rubric_recommendation_relevance": rubric.get("recommendation_relevance", ""),
        "expect_must_mention": _as_str_list(expectations.get("must_mention")),
        "expect_must_avoid": _as_str_list(expectations.get("must_avoid")),
        "expect_must_include_sections": required_sections,
        "expect_confidence_level": expectations.get("confidence_level_expected", "medium"),
    }


def wait_for_run(client: OpenAI, eval_id: str, run_id: str) -> Dict[str, Any]:
    while True:
        run = client.get(f"/evals/{eval_id}/runs/{run_id}", cast_to=object)
        if not isinstance(run, dict):
            raise RuntimeError("Unexpected eval run response shape.")
        if run.get("status") in TERMINAL_STATUSES:
            return run
        time.sleep(POLL_INTERVAL_S)


def fetch_output_items(client: OpenAI, eval_id: str, run_id: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    after: str = ""

    while True:
        query: Dict[str, Any] = {"limit": 100}
        if after:
            query["after"] = after

        page = client.get(
            f"/evals/{eval_id}/runs/{run_id}/output_items",
            cast_to=object,
            options={"query": query},
        )
        if not isinstance(page, dict):
            raise RuntimeError("Unexpected output items response shape.")

        data = page.get("data", [])
        if not isinstance(data, list) or not data:
            break

        items.extend(data)
        if not page.get("has_more"):
            break

        last = data[-1]
        if not isinstance(last, dict) or not last.get("id"):
            break
        after = str(last["id"])

    return items


def _sections_in_order(output_text: str, sections: List[str]) -> bool:
    text = output_text.lower()
    last_idx = -1
    for section in sections:
        idx = text.find(section.lower())
        if idx == -1 or idx < last_idx:
            return False
        last_idx = idx
    return True


def _has_any_phrase(output_text: str, phrases: List[str]) -> bool:
    text = output_text.lower()
    for phrase in phrases:
        if phrase.lower() in text:
            return True
    return False


def run_deterministic_checks(eval_item: Dict[str, Any]) -> Dict[str, Any]:
    output_text = str(eval_item.get("output_text", ""))
    text_lower = output_text.lower()

    must_mention = _as_str_list(eval_item.get("expect_must_mention"))
    must_avoid = _as_str_list(eval_item.get("expect_must_avoid"))
    must_sections = _as_str_list(eval_item.get("expect_must_include_sections"))

    missing_mentions = [p for p in must_mention if p.lower() not in text_lower]
    hit_avoid = [p for p in must_avoid if p.lower() in text_lower]
    sections_pass = _sections_in_order(output_text, must_sections) if must_sections else True

    confidence_expected = (eval_item.get("expect_confidence_level") or "medium").lower()
    low_conf_markers = [
        "confidence is low",
        "limited confidence",
        "limited data",
        "insufficient data",
        "data confidence is low",
    ]
    overconfident_markers = ["definitive trend", "clear trend", "certainly", "conclusive"]

    if confidence_expected == "low":
        confidence_pass = _has_any_phrase(text_lower, low_conf_markers) and not _has_any_phrase(
            text_lower,
            overconfident_markers,
        )
    elif confidence_expected == "high":
        confidence_pass = not _has_any_phrase(text_lower, low_conf_markers)
    else:
        confidence_pass = True

    metrics = eval_item.get("metrics") or {}
    anomaly_count = int(eval_item.get("anomaly_count") or 0)
    conflict_checks: List[str] = []

    net_bug_delta = _to_float(metrics.get("net_bug_delta"))
    if net_bug_delta is not None and net_bug_delta > 0:
        if re.search(r"backlog\s+(shrank|reduced|decreased)", text_lower):
            conflict_checks.append("bug_backlog_direction_conflict")
    if net_bug_delta is not None and net_bug_delta < 0:
        if re.search(r"backlog\s+(grew|increased|rising)", text_lower):
            conflict_checks.append("bug_backlog_direction_conflict")

    if anomaly_count == 0 and ("anomaly" in text_lower or "anomalies" in text_lower):
        if "no anomalies" not in text_lower and "no notable anomalies" not in text_lower:
            conflict_checks.append("anomaly_claim_without_signal")

    throughput = _to_float(metrics.get("pr_throughput"))
    if throughput is not None and throughput == 0 and "steady stream" in text_lower:
        conflict_checks.append("throughput_claim_conflict")

    must_mention_pass = len(missing_mentions) == 0
    must_avoid_pass = len(hit_avoid) == 0
    conflict_pass = len(conflict_checks) == 0

    failed_checks: List[str] = []
    if not must_mention_pass:
        failed_checks.append("must_mention")
    if not must_avoid_pass:
        failed_checks.append("must_avoid")
    if not sections_pass:
        failed_checks.append("section_order")
    if not confidence_pass:
        failed_checks.append("confidence_calibration")
    if not conflict_pass:
        failed_checks.append("metric_conflicts")

    return {
        "must_mention_pass": must_mention_pass,
        "must_avoid_pass": must_avoid_pass,
        "sections_pass": sections_pass,
        "confidence_pass": confidence_pass,
        "conflict_pass": conflict_pass,
        "missing_mentions": missing_mentions,
        "hit_avoid": hit_avoid,
        "conflict_details": conflict_checks,
        "all_pass": len(failed_checks) == 0,
        "failed_checks": failed_checks,
    }


def _score_pass(score: Any, threshold: float) -> bool:
    score_f = _to_float(score)
    if score_f is None:
        return False
    return score_f >= threshold


def build_case_results(output_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    for output_item in output_items:
        datasource_item = output_item.get("datasource_item") or {}
        source_item = datasource_item.get("item") or {}
        if not source_item and isinstance(datasource_item, dict):
            source_item = datasource_item

        case_id = source_item.get("id") or datasource_item.get("id") or "unknown"
        results = output_item.get("results", [])

        scores: Dict[str, Optional[float]] = {name: None for name in ALL_CRITERIA}
        for result in results:
            if not isinstance(result, dict):
                continue
            name = result.get("name")
            if name in scores:
                scores[name] = _to_float(result.get("score"))

        criterion_pass = {name: _score_pass(scores.get(name), DEFAULT_PASS_THRESHOLD) for name in ALL_CRITERIA}
        deterministic = run_deterministic_checks(source_item if isinstance(source_item, dict) else {})

        cases.append(
            {
                "id": case_id,
                "tags": _as_str_list(source_item.get("tags") if isinstance(source_item, dict) else []),
                "status": output_item.get("status"),
                "scores": scores,
                "criterion_pass": criterion_pass,
                "model_all_pass": all(criterion_pass.values()),
                "deterministic": deterministic,
                "anomaly_count": int((source_item or {}).get("anomaly_count") or 0) if isinstance(source_item, dict) else 0,
            }
        )

    return cases


def compute_slice_scores(cases: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    def _slice_cases(name: str) -> List[Dict[str, Any]]:
        if name == "overall":
            return cases
        if name == "sparse_data":
            return [c for c in cases if "sparse_data" in c.get("tags", [])]
        if name == "normal_data":
            return [c for c in cases if "normal_data" in c.get("tags", [])]
        if name == "anomalous":
            return [
                c
                for c in cases
                if "anomalous" in c.get("tags", []) or int(c.get("anomaly_count") or 0) > 0
            ]
        return []

    out: Dict[str, Dict[str, Any]] = {}

    for slice_name in ["overall", "sparse_data", "normal_data", "anomalous"]:
        slice_cases = _slice_cases(slice_name)
        n_cases = len(slice_cases)

        avg_scores: Dict[str, Optional[float]] = {}
        criterion_pass_rate: Dict[str, Optional[float]] = {}

        for criterion in ALL_CRITERIA:
            vals = [
                _to_float(c.get("scores", {}).get(criterion))
                for c in slice_cases
                if _to_float(c.get("scores", {}).get(criterion)) is not None
            ]
            avg_scores[criterion] = _mean([v for v in vals if v is not None])

            if n_cases == 0:
                criterion_pass_rate[criterion] = None
            else:
                passes = sum(1 for c in slice_cases if c.get("criterion_pass", {}).get(criterion))
                criterion_pass_rate[criterion] = round(passes / n_cases, 4)

        aggregate_values = [v for v in avg_scores.values() if v is not None]
        overall_average = _mean(aggregate_values)

        calibration_values = [
            avg_scores.get(name)
            for name in CALIBRATION_CRITERIA
            if avg_scores.get(name) is not None
        ]
        calibration_average = _mean([v for v in calibration_values if v is not None])

        critical_values = [
            avg_scores.get(name)
            for name in CRITICAL_CRITERIA
            if avg_scores.get(name) is not None
        ]
        critical_average = _mean([v for v in critical_values if v is not None])

        model_all_pass_rate = None
        deterministic_pass_rate = None
        if n_cases > 0:
            model_all_pass_rate = round(sum(1 for c in slice_cases if c.get("model_all_pass")) / n_cases, 4)
            deterministic_pass_rate = round(
                sum(1 for c in slice_cases if c.get("deterministic", {}).get("all_pass")) / n_cases,
                4,
            )

        out[slice_name] = {
            "n_cases": n_cases,
            "avg_scores": avg_scores,
            "criterion_pass_rate": criterion_pass_rate,
            "model_all_pass_rate": model_all_pass_rate,
            "deterministic_pass_rate": deterministic_pass_rate,
            "overall_average": overall_average,
            "calibration_average": calibration_average,
            "critical_average": critical_average,
        }

    return out


def compare_with_baseline(
    slice_scores: Dict[str, Dict[str, Any]],
    baseline_payload: Optional[Dict[str, Any]],
    max_overall_drop: float,
    max_sparse_drop: float,
    min_critical_score: float,
    min_sparse_calibration: float,
) -> Dict[str, Any]:
    def _baseline_slice_value(slice_name: str, key: str) -> Optional[float]:
        if not baseline_payload:
            return None
        base_slice = (baseline_payload.get("slice_scores") or {}).get(slice_name) or {}
        return _to_float(base_slice.get(key))

    current_overall = _to_float((slice_scores.get("overall") or {}).get("overall_average"))
    current_sparse = _to_float((slice_scores.get("sparse_data") or {}).get("overall_average"))
    current_sparse_calibration = _to_float((slice_scores.get("sparse_data") or {}).get("calibration_average"))

    baseline_overall = _baseline_slice_value("overall", "overall_average")
    baseline_sparse = _baseline_slice_value("sparse_data", "overall_average")

    overall_delta = None if (current_overall is None or baseline_overall is None) else round(current_overall - baseline_overall, 4)
    sparse_delta = None if (current_sparse is None or baseline_sparse is None) else round(current_sparse - baseline_sparse, 4)

    overall_drop = None if (overall_delta is None) else round(-overall_delta, 4)
    sparse_drop = None if (sparse_delta is None) else round(-sparse_delta, 4)

    reasons: List[str] = []
    if overall_drop is not None and overall_drop >= max_overall_drop:
        reasons.append(
            f"overall_average_drop={overall_drop} exceeded threshold {max_overall_drop}"
        )
    if sparse_drop is not None and sparse_drop >= max_sparse_drop:
        reasons.append(
            f"sparse_data_average_drop={sparse_drop} exceeded threshold {max_sparse_drop}"
        )

    overall_avg_scores = (slice_scores.get("overall") or {}).get("avg_scores") or {}
    critical_below: Dict[str, float] = {}
    for criterion in CRITICAL_CRITERIA:
        value = _to_float(overall_avg_scores.get(criterion))
        if value is not None and value < min_critical_score:
            critical_below[criterion] = value
            reasons.append(
                f"critical criterion '{criterion}' scored {value} < {min_critical_score}"
            )

    if current_sparse_calibration is not None and current_sparse_calibration < min_sparse_calibration:
        reasons.append(
            f"sparse_data calibration_average={current_sparse_calibration} < {min_sparse_calibration}"
        )

    return {
        "metric_deltas": {
            "overall_average_delta": overall_delta,
            "sparse_data_average_delta": sparse_delta,
            "overall_average_drop": overall_drop,
            "sparse_data_average_drop": sparse_drop,
        },
        "critical_below_threshold": critical_below,
        "soft_gate_failed": len(reasons) > 0,
        "soft_gate_reasons": reasons,
        "baseline_present": baseline_payload is not None,
    }


def _load_baseline(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def persist_eval_results_to_db(
    output_payload: Dict[str, Any],
    *,
    model: str,
    grading_model: str,
    eval_name: str,
    run_name: str,
    dataset_path: str,
    source: str = "weekly_summary_eval_v2",
) -> str:
    run_key = str(output_payload.get("run_id") or f"local_eval_{int(time.time())}")
    eval_id = str(output_payload.get("eval_id") or "")
    eval_run_id = str(output_payload.get("run_id") or "")
    dataset_info = output_payload.get("dataset_info") or {}
    baseline = output_payload.get("baseline_comparison") or {}
    slice_scores = output_payload.get("slice_scores") or {}

    overall_average = _to_float(((slice_scores.get("overall") or {}).get("overall_average")))
    sparse_average = _to_float(((slice_scores.get("sparse_data") or {}).get("overall_average")))
    sparse_calibration = _to_float(((slice_scores.get("sparse_data") or {}).get("calibration_average")))

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO eval_runs (
                run_key, source, eval_id, eval_run_id, eval_name, run_name,
                model, grading_model, dataset_path,
                static_count, production_count, total_count, ran_count, skipped_count,
                baseline_present, soft_gate_failed,
                overall_average, sparse_average, sparse_calibration_average,
                output_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_key) DO UPDATE SET
                source = excluded.source,
                eval_id = excluded.eval_id,
                eval_run_id = excluded.eval_run_id,
                eval_name = excluded.eval_name,
                run_name = excluded.run_name,
                model = excluded.model,
                grading_model = excluded.grading_model,
                dataset_path = excluded.dataset_path,
                static_count = excluded.static_count,
                production_count = excluded.production_count,
                total_count = excluded.total_count,
                ran_count = excluded.ran_count,
                skipped_count = excluded.skipped_count,
                baseline_present = excluded.baseline_present,
                soft_gate_failed = excluded.soft_gate_failed,
                overall_average = excluded.overall_average,
                sparse_average = excluded.sparse_average,
                sparse_calibration_average = excluded.sparse_calibration_average,
                output_json = excluded.output_json
            """,
            (
                run_key,
                source,
                eval_id,
                eval_run_id,
                eval_name,
                run_name,
                model,
                grading_model,
                dataset_path,
                _to_int(dataset_info.get("static_count"), 0),
                _to_int(dataset_info.get("production_count"), 0),
                _to_int(dataset_info.get("total_count"), 0),
                _to_int(dataset_info.get("ran_count"), 0),
                _to_int(dataset_info.get("skipped_count"), 0),
                bool(baseline.get("baseline_present")),
                bool(baseline.get("soft_gate_failed")),
                overall_average,
                sparse_average,
                sparse_calibration,
                _json_dump(output_payload),
            ),
        )

        for case in output_payload.get("results", []) or []:
            conn.execute(
                """
                INSERT INTO eval_case_results (
                    run_key, case_id, status, tags_json, scores_json,
                    criterion_pass_json, deterministic_json,
                    anomaly_count, model_all_pass
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_key, case_id) DO UPDATE SET
                    status = excluded.status,
                    tags_json = excluded.tags_json,
                    scores_json = excluded.scores_json,
                    criterion_pass_json = excluded.criterion_pass_json,
                    deterministic_json = excluded.deterministic_json,
                    anomaly_count = excluded.anomaly_count,
                    model_all_pass = excluded.model_all_pass
                """,
                (
                    run_key,
                    str(case.get("id") or "unknown"),
                    case.get("status"),
                    _json_dump(case.get("tags", [])),
                    _json_dump(case.get("scores", {})),
                    _json_dump(case.get("criterion_pass", {})),
                    _json_dump(case.get("deterministic", {})),
                    _to_int(case.get("anomaly_count"), 0),
                    bool(case.get("model_all_pass")),
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return run_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Run weekly summary evals against the OpenAI eval platform.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/weekly_summary_dataset_v2.jsonl"),
        help="Path to the JSONL dataset.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Model to generate summaries (defaults to OPENAI_MODEL or gpt-4.1-mini).",
    )
    parser.add_argument(
        "--grading-model",
        type=str,
        default="",
        help="Model to use for grading (defaults to OPENAI_EVAL_MODEL or OPENAI_MODEL).",
    )
    parser.add_argument(
        "--eval-name",
        type=str,
        default="weekly-summary-markdown-eval-v2",
        help="Name of the eval group.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="weekly-summary-run-v2",
        help="Name of this eval run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/weekly_summary_eval_results.json"),
        help="Where to write the per-case scoring output.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional baseline results JSON to compare against.",
    )
    parser.add_argument(
        "--soft-gate",
        action="store_true",
        help="Exit with non-zero status when regression guard conditions are hit.",
    )
    parser.add_argument(
        "--max-overall-drop",
        type=float,
        default=0.5,
        help="Maximum allowed overall average drop vs baseline.",
    )
    parser.add_argument(
        "--max-sparse-drop",
        type=float,
        default=0.5,
        help="Maximum allowed sparse-data slice average drop vs baseline.",
    )
    parser.add_argument(
        "--min-critical-score",
        type=float,
        default=3.0,
        help="Minimum average score allowed for critical criteria.",
    )
    parser.add_argument(
        "--min-sparse-calibration",
        type=float,
        default=3.5,
        help="Minimum sparse-data calibration average score.",
    )
    parser.add_argument(
        "--include-production",
        action="store_true",
        help="Include recent production runs stored in SQLite analysis_runs.",
    )
    parser.add_argument(
        "--production-only",
        action="store_true",
        help="Run evals only against production runs (skip static dataset).",
    )
    parser.add_argument(
        "--production-limit",
        type=int,
        default=20,
        help="Maximum number of recent production runs to include.",
    )
    parser.add_argument(
        "--production-since-hours",
        type=int,
        default=168,
        help="How far back to look for production runs (hours).",
    )
    parser.add_argument(
        "--grader-only",
        action="store_true",
        help="Use pre-existing output_text from dataset/production rows when available.",
    )
    parser.add_argument(
        "--persist-results",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Persist aggregate + per-case eval results into eval_runs/eval_case_results tables.",
    )

    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.openai_model or "gpt-4.1-mini"
    grading_model = (
        args.grading_model
        or os.getenv("OPENAI_EVAL_MODEL")
        or settings.openai_model
        or "gpt-4.1-mini"
    )

    include_production = args.include_production or args.production_only

    dataset: List[Dict[str, Any]] = []
    if args.production_only:
        static_dataset: List[Dict[str, Any]] = []
    elif args.dataset.exists():
        static_dataset = load_dataset(args.dataset)
    elif include_production:
        static_dataset = []
    else:
        raise SystemExit(f"Dataset file does not exist: {args.dataset}")
    dataset.extend(static_dataset)

    production_dataset: List[Dict[str, Any]] = []
    if include_production:
        production_dataset = load_production_dataset(
            limit=args.production_limit,
            since_hours=args.production_since_hours,
        )
        dataset.extend(production_dataset)

    if not dataset:
        raise SystemExit("No eval items were loaded (static dataset + production dataset are both empty).")

    seen_ids = set()
    deduped_dataset: List[Dict[str, Any]] = []
    for item in dataset:
        case_id = item.get("id")
        if case_id in seen_ids:
            continue
        seen_ids.add(case_id)
        deduped_dataset.append(item)
    dataset = deduped_dataset

    for item in dataset:
        validate_dataset_item(item)

    client = OpenAI()

    outputs: List[Dict[str, Any]] = []
    skipped_items: List[str] = []
    for item in dataset:
        precomputed_summary = str(item.get("output_text", "") or "").strip()
        if args.grader_only and precomputed_summary:
            summary = precomputed_summary
        elif args.grader_only and not precomputed_summary:
            skipped_items.append(str(item.get("id") or "unknown"))
            continue
        else:
            summary = generate_summary(
                client,
                model,
                item["metrics"],
                item.get("anomalies", []),
                item.get("context", {}),
            )
        eval_item = prepare_eval_item(item, summary)
        outputs.append({"item": eval_item, "summary": summary})

    if not outputs:
        raise SystemExit("No eval items to run after filtering (grader-only likely skipped all items).")

    eval_obj = client.post(
        "/evals",
        cast_to=object,
        body={
            "name": args.eval_name,
            "data_source_config": {
                "type": "custom",
                "item_schema": build_eval_schema(),
            },
            "testing_criteria": build_grading_criteria(grading_model),
        },
    )
    if not isinstance(eval_obj, dict) or "id" not in eval_obj:
        raise RuntimeError("Unexpected eval create response shape.")
    eval_id = eval_obj["id"]

    run = client.post(
        f"/evals/{eval_id}/runs",
        cast_to=object,
        body={
            "name": args.run_name,
            "data_source": {
                "type": "jsonl",
                "source": {
                    "type": "file_content",
                    "content": [{"item": entry["item"]} for entry in outputs],
                },
            },
        },
    )
    if not isinstance(run, dict) or "id" not in run:
        raise RuntimeError("Unexpected eval run create response shape.")
    run_id = run["id"]

    run_state = wait_for_run(client, eval_id, run_id)
    output_items = fetch_output_items(client, eval_id, run_id)

    case_results = build_case_results(output_items)
    slice_scores = compute_slice_scores(case_results)

    baseline_payload = _load_baseline(args.baseline)
    baseline_comparison = compare_with_baseline(
        slice_scores=slice_scores,
        baseline_payload=baseline_payload,
        max_overall_drop=args.max_overall_drop,
        max_sparse_drop=args.max_sparse_drop,
        min_critical_score=args.min_critical_score,
        min_sparse_calibration=args.min_sparse_calibration,
    )

    output_payload = {
        "eval_id": eval_id,
        "run_id": run_id,
        "run_status": run_state.get("status"),
        "report_url": run_state.get("report_url"),
        "dataset_info": {
            "static_count": len(static_dataset),
            "production_count": len(production_dataset),
            "total_count": len(dataset),
            "ran_count": len(outputs),
            "skipped_count": len(skipped_items),
            "skipped_ids": skipped_items,
        },
        "criteria": ALL_CRITERIA,
        "critical_criteria": CRITICAL_CRITERIA,
        "calibration_criteria": CALIBRATION_CRITERIA,
        "results": case_results,
        "slice_scores": slice_scores,
        "baseline_comparison": baseline_comparison,
    }

    if args.persist_results:
        persisted_run_key = persist_eval_results_to_db(
            output_payload,
            model=model,
            grading_model=grading_model,
            eval_name=args.eval_name,
            run_name=args.run_name,
            dataset_path=str(args.dataset),
            source="weekly_summary_eval_v2",
        )
        output_payload["persisted_run_key"] = persisted_run_key

    args.output.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(json.dumps(output_payload, indent=2))

    if args.soft_gate and baseline_comparison.get("soft_gate_failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
