from typing import Any, Callable, Dict, List, Optional

from .ingest import run_ingest
from .metrics import recompute_weekly_metrics
from .anomalies import detect_anomalies
from .query import (
    get_weekly_metrics_history,
    get_last_weekly_metrics,
    get_llm_context,
)
from .agents import generate_weekly_summary, answer_question_with_metrics


def run_full_analysis(
    owner: str,
    repo: str,
    days_back: int = 90,
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

    lookback_days = days_back
    _status("Ingesting GitHub data…", 0.1)
    run_ingest(owner, repo, lookback_days)

    _status("Recomputing weekly metrics…", 0.4)
    latest_metrics: Dict[str, Any] = recompute_weekly_metrics(owner, repo, weeks_back=12)
    _status("Scanning for anomalies…", 0.6)
    history_df = get_weekly_metrics_history(owner, repo)
    anomalies: List[Dict[str, Any]] = detect_anomalies(history_df) if not history_df.empty else []

    _status("Building LLM context…", 0.8)
    llm_context = get_llm_context(owner, repo, weeks_back=12)

    _status("Drafting weekly summary…", 0.9)
    summary = generate_weekly_summary(latest_metrics, anomalies, llm_context)
    return summary


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
