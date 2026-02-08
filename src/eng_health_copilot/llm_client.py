import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .config import get_settings

_client: Optional[OpenAI] = None


def _get_client() -> Optional[OpenAI]:
    """Return a cached OpenAI client, or None if no API key is configured."""
    global _client
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client

def _capture_weekly_summary_inputs(
    capture_path: Path,
    model: str,
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> None:
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "task": "weekly_summary",
        "model": model,
        "metrics": metrics,
        "anomalies": anomalies,
        "context": context,
    }
    with capture_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")

def build_weekly_summary_prompts(
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> tuple[str, str, Dict[str, Any]]:
    settings = get_settings()
    model = settings.openai_model or "gpt-4.1-mini"

    payload = {
        "latest_metrics": metrics,
        "anomalies": anomalies,
        "context": context,
    }

    data_sufficiency = context.get("data_sufficiency") or {}
    data_sufficiency_level = data_sufficiency.get("level")
    low_data_instruction = ""
    if data_sufficiency_level == "low":
        low_data_instruction = (
            "Data sufficiency is LOW. Explicitly call out limited confidence, avoid strong trend claims, "
            "and prioritize instrumentation/repo-hygiene recommendations.\n\n"
        )

    if settings.weekly_summary_capture_enabled:
        _capture_weekly_summary_inputs(
            settings.weekly_summary_capture_path,
            model,
            metrics,
            anomalies,
            context,
        )

    system_prompt = (
        "You are an experienced engineering manager and product-minded PM. "
        "Given repository metrics and context, you write concise, executive-ready "
        "weekly engineering health summaries. You focus on delivery, quality, WIP, "
        "and risk, and propose pragmatic recommendations."
    )

    user_prompt = (
        "Here is the weekly engineering data for a GitHub repo.\n\n"
        "You must respond with a short markdown report in this structure:\n\n"
        "### Weekly Engineering Summary\n"
        "- Bullet list of key headline metrics (throughput, lead time, bugs, WIP, commits)\n\n"
        "### High-level read\n"
        "- 3–6 bullets explaining what happened this week, in plain language\n\n"
        "### Notable anomalies vs recent history (if any)\n"
        "- Bullets describing anomalies and their likely meaning\n\n"
        "### Additional context and recommendations\n"
        "- What might be driving this (CI, large PRs, reviews, releases)\n"
        "- 3–5 concrete recommendations for the team (e.g., reduce WIP, tackle aging PRs, limit PR size)\n\n"
        "Use any `context.data_sufficiency` information to calibrate confidence and recommendations.\n"
        f"{low_data_instruction}"
        "Be direct, non-fluffy, and assume the reader is a busy PM or EM.\n\n"
        f"Data JSON:\n```json\n{json.dumps(payload, default=str)}\n```"
    )

    return system_prompt, user_prompt, payload


def generate_weekly_summary_llm(
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Use OpenAI to produce a PM-facing weekly eng health summary.

    Returns the text, or None if no client / error.
    """
    client = _get_client()
    if client is None:
        return None

    settings = get_settings()
    model = settings.openai_model or "gpt-4.1-mini"

    system_prompt, user_prompt, _payload = build_weekly_summary_prompts(
        metrics,
        anomalies,
        context,
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=900,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[llm] Error generating weekly summary: {e}")
        return None


def answer_question_llm(
    question: str,
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Use OpenAI to answer a follow-up question about repo health.

    Returns the text, or None if no client / error.
    """
    client = _get_client()
    if client is None:
        return None

    settings = get_settings()
    model = settings.openai_model or "gpt-4.1-mini"

    payload = {
        "question": question,
        "latest_metrics": metrics,
        "anomalies": anomalies,
        "context": context,
    }

    system_prompt = (
        "You are an engineering health copilot for a PM or EM. "
        "You answer questions about a repository's delivery, quality, and WIP "
        "using provided metrics and context. You are concrete, data-grounded, "
        "and non-fluffy."
    )

    user_prompt = (
        "Answer the user's question about this repo's engineering health in a short, "
        "direct markdown response. Reference specific metrics or patterns when useful, "
        "and propose clear next steps when relevant.\n\n"
        f"User question:\n{question}\n\n"
        f"Data JSON:\n```json\n{json.dumps(payload, default=str)}\n```"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[llm] Error answering question: {e}")
        return None
