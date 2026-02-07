import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from eng_health_copilot.config import get_settings
from eng_health_copilot.llm_client import build_weekly_summary_prompts

DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 900
POLL_INTERVAL_S = 2
TERMINAL_STATUSES = {"completed", "failed", "canceled", "cancelled"}


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                items.append(json.loads(line))
    return items


def generate_summary(
    client: OpenAI,
    model: str,
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    system_prompt, user_prompt, _payload = build_weekly_summary_prompts(metrics, anomalies, context)
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


def build_eval_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "metrics": {"type": "object"},
            "anomalies": {"type": "array"},
            "context": {"type": "object"},
            "expected": {"type": "object"},
            "rubric": {"type": "object"},
        },
        "required": ["id", "metrics", "anomalies", "context", "expected", "rubric"],
    }


def build_grading_criteria(grading_model: str) -> List[Dict[str, Any]]:
    return [
        {
            "type": "score_model",
            "name": "format_correctness",
            "model": grading_model,
            "range": [1, 5],
            "pass_threshold": 3,
            "sampling_params": {"temperature": 0},
            "input": [
                {
                    "role": "system",
                    "content": "You are a strict grader for markdown formatting and structure.",
                },
                {
                    "role": "user",
                    "content": (
                        "Score the output on format correctness (1-5). "
                        "Use this rubric: {{item.rubric.format}}\n\n"
                        "Model output:\n{{sample.output_text}}\n\n"
                        "Return only a single integer score from 1 to 5."
                    ),
                },
            ],
        },
        {
            "type": "score_model",
            "name": "grounding_to_metrics",
            "model": grading_model,
            "range": [1, 5],
            "pass_threshold": 3,
            "sampling_params": {"temperature": 0},
            "input": [
                {
                    "role": "system",
                    "content": "You are a strict grader for data grounding and factuality.",
                },
                {
                    "role": "user",
                    "content": (
                        "Score grounding to provided metrics and context (1-5). "
                        "Use this rubric: {{item.rubric.grounding}}\n\n"
                        "Model output:\n{{sample.output_text}}\n\n"
                        "Return only a single integer score from 1 to 5."
                    ),
                },
            ],
        },
        {
            "type": "score_model",
            "name": "actionable_recommendations",
            "model": grading_model,
            "range": [1, 5],
            "pass_threshold": 3,
            "sampling_params": {"temperature": 0},
            "input": [
                {
                    "role": "system",
                    "content": "You are a strict grader for actionable, concrete recommendations.",
                },
                {
                    "role": "user",
                    "content": (
                        "Score actionability of recommendations (1-5). "
                        "Use this rubric: {{item.rubric.actionable}}\n\n"
                        "Model output:\n{{sample.output_text}}\n\n"
                        "Return only a single integer score from 1 to 5."
                    ),
                },
            ],
        },
    ]


def wait_for_run(client: OpenAI, eval_id: str, run_id: str) -> Dict[str, Any]:
    while True:
        run = client.evals.runs.retrieve(eval_id=eval_id, run_id=run_id)
        if run.status in TERMINAL_STATUSES:
            return run.model_dump()
        time.sleep(POLL_INTERVAL_S)


def fetch_output_items(client: OpenAI, eval_id: str, run_id: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = client.evals.runs.output_items.list(eval_id=eval_id, run_id=run_id, limit=100)
    items.extend([entry.model_dump() for entry in page.data])
    while page.has_next_page():
        page = page.get_next_page()
        items.extend([entry.model_dump() for entry in page.data])
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Run weekly summary evals against the OpenAI eval platform.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/weekly_summary_dataset.jsonl"),
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
        default="weekly-summary-markdown-eval",
        help="Name of the eval group.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="weekly-summary-run",
        help="Name of this eval run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/weekly_summary_eval_results.json"),
        help="Where to write the per-case scoring output.",
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

    dataset = load_dataset(args.dataset)
    if not dataset:
        raise SystemExit(f"Dataset {args.dataset} is empty.")

    client = OpenAI()

    outputs: List[Dict[str, Any]] = []
    for item in dataset:
        summary = generate_summary(
            client,
            model,
            item["metrics"],
            item.get("anomalies", []),
            item.get("context", {}),
        )
        outputs.append({"item": item, "summary": summary})

    eval_obj = client.evals.create(
        name=args.eval_name,
        data_source_config={
            "type": "custom",
            "item_schema": build_eval_schema(),
            "include_sample_schema": True,
        },
        testing_criteria=build_grading_criteria(grading_model),
    )

    run = client.evals.runs.create(
        eval_id=eval_obj.id,
        name=args.run_name,
        data_source={
            "type": "jsonl",
            "source": {
                "type": "file_content",
                "content": [
                    {"item": entry["item"], "sample": {"output_text": entry["summary"]}}
                    for entry in outputs
                ],
            },
        },
    )

    run_state = wait_for_run(client, eval_obj.id, run.id)
    output_items = fetch_output_items(client, eval_obj.id, run.id)

    per_case_scores: List[Dict[str, Any]] = []
    for output_item in output_items:
        datasource_item = output_item.get("datasource_item", {})
        case_id = datasource_item.get("id", "unknown")
        results = output_item.get("results", [])
        scores = {result["name"]: result.get("score") for result in results}
        per_case_scores.append(
            {
                "id": case_id,
                "scores": scores,
                "status": output_item.get("status"),
            }
        )

    output_payload = {
        "eval_id": eval_obj.id,
        "run_id": run.id,
        "run_status": run_state.get("status"),
        "report_url": run_state.get("report_url"),
        "results": per_case_scores,
    }

    args.output.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(json.dumps(output_payload, indent=2))


if __name__ == "__main__":
    main()
