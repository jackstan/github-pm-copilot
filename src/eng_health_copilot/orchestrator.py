import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .config import get_settings
from .ingest import run_ingest
from .metrics import recompute_weekly_metrics
from .anomalies import detect_anomalies
from .query import (
    get_weekly_metrics_history,
    get_last_weekly_metrics,
    get_llm_context,
)
from .agents import generate_weekly_summary, answer_question_with_metrics
from .agents import compute_data_sufficiency
from .run_history import build_input_hash, record_analysis_run


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_full_analysis(
    owner: str,
    repo: str,
    days_back: int = 90,
    force_refresh: bool = False,
    on_status: Optional[Callable[[str, float], None]] = None,
) -> str:
    """
    Full pipeline:
      - Ingest fresh data from GitHub
      - Recompute weekly metrics
      - Detect anomalies
      - Build LLM context
      - Generate a weekly summary for the chat UI
    """
    def _status(label: str, progress: float) -> None:
        if on_status:
            on_status(label, progress)

    run_id = f"analysis_{uuid4().hex}"
    started_at = _utc_now_iso()
    started_perf = time.perf_counter()

    latest_metrics: Dict[str, Any] = {}
    anomalies: List[Dict[str, Any]] = []
    llm_context: Dict[str, Any] = {}
    summary = ""
    status = "failed"
    error_text: Optional[str] = None

    try:
        lookback_days = days_back
        weeks_back = max(12, (max(1, int(days_back)) + 6) // 7)
        _status("Ingesting GitHub data…", 0.1)
        ingest_result = run_ingest(owner, repo, lookback_days, force_refresh=force_refresh)
        if ingest_result.get("skipped"):
            _status("Using recently ingested data cache…", 0.25)

        _status("Recomputing weekly metrics…", 0.4)
        latest_metrics = recompute_weekly_metrics(owner, repo, weeks_back=weeks_back)
        _status("Scanning for anomalies…", 0.6)
        history_df = get_weekly_metrics_history(owner, repo)
        anomalies = detect_anomalies(history_df) if not history_df.empty else []

        _status("Building LLM context…", 0.8)
        llm_context = get_llm_context(owner, repo, weeks_back=weeks_back)

        _status("Drafting weekly summary…", 0.9)
        summary = generate_weekly_summary(latest_metrics, anomalies, llm_context)
        status = "completed"
        return summary
    except Exception as exc:
        error_text = str(exc)
        raise
    finally:
        completed_at = _utc_now_iso()
        duration_ms = int((time.perf_counter() - started_perf) * 1000)
        settings = get_settings()
        model = settings.openai_model or "gpt-4.1-mini"
        suff = compute_data_sufficiency(latest_metrics, llm_context) if latest_metrics else {}
        suff_level = suff.get("level")
        input_hash = (
            build_input_hash(latest_metrics, anomalies, llm_context)
            if latest_metrics or anomalies or llm_context
            else None
        )
        try:
            record_analysis_run(
                run_id=run_id,
                repo_owner=owner,
                repo_name=repo,
                days_back=days_back,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                duration_ms=duration_ms,
                model=model,
                temperature=0.3,
                data_sufficiency_level=suff_level,
                input_hash=input_hash,
                metrics=latest_metrics,
                anomalies=anomalies,
                context=llm_context,
                summary_markdown=summary,
                error_text=error_text,
            )
        except Exception as log_exc:
            print(f"[orchestrator] Failed to persist analysis run {run_id}: {log_exc}")


def answer_user_question(owner: str, repo: str, question: str) -> str:
    """
    Handle a follow-up question in the chat UI.

    Loads the latest metrics + anomalies + rich context and passes
    them through to the Q&A agent.
    """
    latest_metrics = get_last_weekly_metrics(owner, repo)
    if latest_metrics is None:
        return (
            "I don't have any metrics yet for this repo. "
            "Run an analysis from the sidebar first."
        )

    history_df = get_weekly_metrics_history(owner, repo)
    anomalies: List[Dict[str, Any]] = detect_anomalies(history_df) if not history_df.empty else []

    llm_context = get_llm_context(owner, repo, weeks_back=12)

    return answer_question_with_metrics(
        question=question,
        metrics=latest_metrics,
        anomalies=anomalies,
        context=llm_context,
    )
