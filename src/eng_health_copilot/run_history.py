import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .db import get_db


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, default=str, sort_keys=True)


def build_input_hash(
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    material = {
        "metrics": metrics or {},
        "anomalies": anomalies or [],
        "context": context or {},
    }
    digest = hashlib.sha256(_json_dumps(material).encode("utf-8")).hexdigest()
    return digest


def record_analysis_run(
    run_id: str,
    repo_owner: str,
    repo_name: str,
    days_back: int,
    started_at: str,
    completed_at: Optional[str],
    status: str,
    duration_ms: Optional[int],
    model: Optional[str],
    temperature: Optional[float],
    data_sufficiency_level: Optional[str],
    input_hash: Optional[str],
    metrics: Optional[Dict[str, Any]],
    anomalies: Optional[List[Dict[str, Any]]],
    context: Optional[Dict[str, Any]],
    summary_markdown: Optional[str],
    error_text: Optional[str],
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO analysis_runs (
                run_id,
                repo_owner,
                repo_name,
                days_back,
                started_at,
                completed_at,
                status,
                duration_ms,
                model,
                temperature,
                data_sufficiency_level,
                input_hash,
                metrics_json,
                anomalies_json,
                context_json,
                summary_markdown,
                error_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                repo_owner = excluded.repo_owner,
                repo_name = excluded.repo_name,
                days_back = excluded.days_back,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                status = excluded.status,
                duration_ms = excluded.duration_ms,
                model = excluded.model,
                temperature = excluded.temperature,
                data_sufficiency_level = excluded.data_sufficiency_level,
                input_hash = excluded.input_hash,
                metrics_json = excluded.metrics_json,
                anomalies_json = excluded.anomalies_json,
                context_json = excluded.context_json,
                summary_markdown = excluded.summary_markdown,
                error_text = excluded.error_text
            """,
            (
                run_id,
                repo_owner,
                repo_name,
                int(days_back),
                started_at,
                completed_at or _utc_now_iso(),
                status,
                duration_ms,
                model,
                temperature,
                data_sufficiency_level,
                input_hash,
                _json_dumps(metrics or {}),
                _json_dumps(anomalies or []),
                _json_dumps(context or {}),
                summary_markdown or "",
                error_text,
            ),
        )
        conn.commit()
    finally:
        conn.close()
