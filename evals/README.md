# Weekly Summary Evals (V2)

This folder contains the weekly-summary eval dataset and runner used to score output quality, sparse-data calibration, and regression risk over time.

## Contents

- `weekly_summary_dataset.jsonl` — Original lightweight dataset (legacy).
- `weekly_summary_dataset_v2.jsonl` — Expanded 18-case dataset with scenario tags and deterministic expectations.
- `run_weekly_summary_eval.py` — Runner that:
  - generates summaries with the same prompt-construction path as production,
  - can grade stored production summaries from SQLite (`analysis_runs`),
  - submits model-graded eval criteria,
  - applies deterministic checks,
  - computes per-slice metrics,
  - optionally compares vs baseline and applies a soft gate.
- `weekly_summary_eval_results.json` — Latest run output.

## Dataset V2 schema (per line)

Each JSONL item includes:

- `id` (string)
- `tags` (string array): scenario tags such as `sparse_data`, `normal_data`, `anomalous`, `ci_unstable`
- `metrics` (object)
- `anomalies` (array)
- `context` (object)
- `expected.summary_markdown` (string)
- `rubric` (object):
  - `format`
  - `grounding`
  - `actionable`
  - `uncertainty`
  - `hallucination`
  - `anomaly_handling`
  - `recommendation_relevance`
- `expectations` (object):
  - `must_mention` (string array)
  - `must_avoid` (string array)
  - `must_include_sections` (string array)
  - `confidence_level_expected` (`high` | `medium` | `low`)

## Grading criteria

The runner submits these model-graded criteria (1-5 each):

1. `format_correctness`
2. `grounding_to_metrics`
3. `actionable_recommendations`
4. `uncertainty_calibration`
5. `hallucination_guard`
6. `anomaly_handling`
7. `recommendation_relevance`

It also applies deterministic checks per case:

- section presence/order
- `must_mention` phrase checks
- `must_avoid` phrase checks
- confidence calibration expectation check
- metric conflict checks (e.g., positive bug delta with "backlog shrank")

## Slice reporting

`slice_scores` are reported for:

- `overall`
- `sparse_data`
- `normal_data`
- `anomalous`

Each slice includes:

- `avg_scores` per criterion
- `criterion_pass_rate`
- `model_all_pass_rate`
- `deterministic_pass_rate`
- `overall_average`
- `calibration_average`
- `critical_average`

## Running the eval

```bash
export OPENAI_API_KEY=your-key
export OPENAI_MODEL=gpt-4.1-mini
export OPENAI_EVAL_MODEL=gpt-4.1-mini

PYTHONPATH=src python3 evals/run_weekly_summary_eval.py \
  --dataset evals/weekly_summary_dataset_v2.jsonl \
  --model gpt-4.1-mini \
  --grading-model gpt-4.1-mini \
  --eval-name weekly-summary-markdown-eval-v2 \
  --run-name weekly-summary-run-v2 \
  --output evals/weekly_summary_eval_results.json
```

## Include production runs

You can include recent production summaries persisted in `analysis_runs`:

```bash
PYTHONPATH=src python3 evals/run_weekly_summary_eval.py \
  --production-only \
  --production-limit 20 \
  --production-since-hours 168 \
  --grader-only
```

Notes:

- `--grader-only` uses precomputed `output_text` where available (ideal for production rows).
- Use `--production-only` for a pure production-run eval slice.
- If production runs are in Postgres, set `DATABASE_URL`.
- If production runs are in SQLite, set `ENG_HEALTH_DB_PATH` when non-default.

## Soft gate + baseline workflow

Run with baseline comparison and soft gating:

```bash
PYTHONPATH=src python3 evals/run_weekly_summary_eval.py \
  --dataset evals/weekly_summary_dataset_v2.jsonl \
  --baseline evals/baseline_weekly_summary_eval_results.json \
  --soft-gate \
  --max-overall-drop 0.5 \
  --max-sparse-drop 0.5 \
  --min-critical-score 3.0 \
  --min-sparse-calibration 3.5
```

When `--soft-gate` is set, the runner exits non-zero if any soft-gate condition fails.

## CI example

```bash
PYTHONPATH=src python3 evals/run_weekly_summary_eval.py \
  --dataset evals/weekly_summary_dataset_v2.jsonl \
  --baseline evals/baseline_weekly_summary_eval_results.json \
  --soft-gate
```

## Triage flow when the gate fails

1. Check `baseline_comparison.soft_gate_reasons`.
2. Inspect `slice_scores` deltas (`overall` and `sparse_data` first).
3. Review failing cases in `results` with:
   - low criterion scores,
   - `model_all_pass = false`,
   - `deterministic.all_pass = false`.
4. Prioritize fixes in sparse-data calibration and grounding before re-running.
