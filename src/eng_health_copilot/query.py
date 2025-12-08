from typing import Optional, Dict, Any

import pandas as pd

from .db import get_db


def get_last_weekly_metrics(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT *
        FROM weekly_metrics
        WHERE repo_owner = ?
          AND repo_name = ?
        ORDER BY week_end DESC
        LIMIT 1
        """,
        conn,
        params=(owner, repo),
    )
    conn.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()
