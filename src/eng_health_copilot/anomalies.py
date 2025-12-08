import pandas as pd
import numpy as np
from typing import Dict, List

def detect_anomalies(df: pd.DataFrame) -> List[Dict]:
    """
    Given a weekly metrics DataFrame, detect anomalies for the last week.
    Returns a list of anomaly messages (strings or dicts).
    """

    if df.empty or len(df) < 4:
        return []  # Not enough data for detection

    df = df.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df = df.sort_values("week_start")

    # Rolling stats
    window = 6  # last six weeks
    metrics = ["pr_throughput", "pr_lead_time_p90", "open_bugs_count", "wip_prs"]

    anomalies = []

    for metric in metrics:
        if metric not in df.columns:
            continue

        # Compute rolling mean and std (exclude the final week for comparison)
        df[f"{metric}_rolling_mean"] = df[metric].rolling(window=window, min_periods=3).mean()
        df[f"{metric}_rolling_std"] = df[metric].rolling(window=window, min_periods=3).std()

    # Focus on latest week
    latest = df.iloc[-1]

    for metric in metrics:
        mean = latest[f"{metric}_rolling_mean"]
        std = latest[f"{metric}_rolling_std"]
        value = latest[metric]

        # Can't detect if mean/std are missing
        if pd.isna(mean) or pd.isna(std) or std == 0:
            continue

        z = (value - mean) / std

        if z > 1.5:
            anomalies.append({
                "metric": metric,
                "type": "high",
                "value": float(value),
                "mean": float(mean),
                "z_score": float(z),
                "message": f"{metric} is unusually high this week (z={z:.2f})."
            })

        elif z < -1.5:
            anomalies.append({
                "metric": metric,
                "type": "low",
                "value": float(value),
                "mean": float(mean),
                "z_score": float(z),
                "message": f"{metric} is unusually low this week (z={z:.2f})."
            })

    return anomalies
