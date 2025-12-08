from typing import List, Dict

import pandas as pd
import numpy as np


def detect_anomalies(df: pd.DataFrame) -> List[Dict]:
    """
    Given a weekly metrics DataFrame, detect anomalies for the last week.
    Focus on:
      - pr_throughput (drop)
      - pr_lead_time_p90 (jump)
      - open_bugs_count (spike)
      - wip_prs (spike)
      - net_bug_delta positive streaks
    """
    if df.empty or len(df) < 4:
        return []  # Not enough history

    df = df.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df = df.sort_values("week_start")

    window = 6
    core_metrics = ["pr_throughput", "pr_lead_time_p90", "open_bugs_count", "wip_prs"]

    # Rolling stats for core metrics
    for metric in core_metrics:
        if metric not in df.columns:
            continue
        df[f"{metric}_rolling_mean"] = df[metric].rolling(window=window, min_periods=3).mean()
        df[f"{metric}_rolling_std"] = df[metric].rolling(window=window, min_periods=3).std()

    anomalies: List[Dict] = []

    latest = df.iloc[-1]

    # Z-score based anomalies for core metrics
    for metric in core_metrics:
        mean_col = f"{metric}_rolling_mean"
        std_col = f"{metric}_rolling_std"

        if mean_col not in latest or std_col not in latest:
            continue

        mean = latest[mean_col]
        std = latest[std_col]
        value = latest[metric]

        if pd.isna(mean) or pd.isna(std) or std == 0:
            continue

        z = (value - mean) / std

        # For throughput, a big negative Z is bad (drop)
        if metric == "pr_throughput":
            if z < -1.5:
                anomalies.append({
                    "metric": metric,
                    "type": "low",
                    "value": float(value),
                    "mean": float(mean),
                    "z_score": float(z),
                    "message": f"PR throughput is lower than usual this week (z={z:.2f}).",
                })
        # For the others, a big positive Z is bad (spike)
        else:
            if z > 1.5:
                label_map = {
                    "pr_lead_time_p90": "Lead time p90",
                    "open_bugs_count": "Open bugs",
                    "wip_prs": "WIP PRs",
                }
                nice_name = label_map.get(metric, metric)
                anomalies.append({
                    "metric": metric,
                    "type": "high",
                    "value": float(value),
                    "mean": float(mean),
                    "z_score": float(z),
                    "message": f"{nice_name} is higher than usual this week (z={z:.2f}).",
                })

    # Net bug delta streak: are we adding bugs faster than closing them for several weeks?
    if "net_bug_delta" in df.columns:
        # Consider last 4 weeks including latest
        recent = df.tail(4)
        recent_deltas = recent["net_bug_delta"].fillna(0)

        # Positive streak: all last 3 weeks (excluding latest) are >= 0 and latest > 0
        if len(recent_deltas) == 4:
            prev3 = recent_deltas.iloc[0:3]
            last = recent_deltas.iloc[3]
            if (prev3 >= 0).all() and last > 0:
                anomalies.append({
                    "metric": "net_bug_delta",
                    "type": "high",
                    "value": float(last),
                    "mean": float(prev3.mean()),
                    "z_score": None,
                    "message": (
                        "Bug backlog has been growing for several weeks in a row "
                        f"(latest net bug delta = +{int(last)})."
                    ),
                })

    return anomalies
