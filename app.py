import sys
from pathlib import Path
import pandas as pd
import altair as alt
import streamlit as st

# Make `src` importable
ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from eng_health_copilot.orchestrator import (
    run_full_analysis,
    answer_user_question,
)
from eng_health_copilot.query import get_weekly_metrics_history
st.set_page_config(page_title="GitHub PM Copilot", layout="wide")

# Session state init
if "has_run_analysis" not in st.session_state:
    st.session_state["has_run_analysis"] = False
if "last_analyzed_repo" not in st.session_state:
    st.session_state["last_analyzed_repo"] = None
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# Sidebar inputs
st.sidebar.title("Repo Settings")
owner = st.sidebar.text_input("Owner", value="pallets")
repo = st.sidebar.text_input("Repo", value="flask")
days_back = st.sidebar.number_input(
    "Days back",
    min_value=7,
    max_value=365,
    value=90,
    step=7,
)

current_repo = f"{owner}/{repo}"


if st.sidebar.button("Run analysis"):
    with st.spinner("Analyzing repo activity..."):
        summary = run_full_analysis(owner, repo, days_back=days_back)

    st.session_state["has_run_analysis"] = True
    st.session_state["last_analyzed_repo"] = current_repo

    # Start a fresh chat each time analysis is run
    st.session_state["chat_history"] = [
        {"role": "assistant", "content": summary}
    ]
    


st.title("GitHub PM Copilot (Eng Health)")
st.subheader("Weekly Metrics (last few weeks)")

if (st.session_state.get("has_run_analysis") and st.session_state.get("last_analyzed_repo") == current_repo):
    history_df = get_weekly_metrics_history(owner, repo)

    if not history_df.empty:
        history_df["week_start"] = pd.to_datetime(history_df["week_start"])
        history_df = history_df.sort_values("week_start")

        # Common x-axis zoom/scroll selection for all charts (only x)
        x_zoom = alt.selection_interval(bind="scales", encodings=["x"])

        # --- PR throughput chart ---
        st.caption("PR throughput (merged PRs per week)")
        throughput_data = history_df[["week_start", "pr_throughput"]]

        throughput_chart = (
            alt.Chart(throughput_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("pr_throughput:Q", title="Merged PRs"),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(throughput_chart, use_container_width=True)

        # --- Lead time chart (p50 & p90) ---
        st.caption("Lead time (days) – p50 and p90")
        lead_data = history_df[["week_start", "pr_lead_time_p50", "pr_lead_time_p90"]].melt(
            "week_start",
            ["pr_lead_time_p50", "pr_lead_time_p90"],
            var_name="metric",
            value_name="value",
        )

        lead_chart = (
            alt.Chart(lead_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("value:Q", title="Lead time (days)"),
                color=alt.Color(
                    "metric:N",
                    title="Metric",
                    scale=alt.Scale(
                        domain=["pr_lead_time_p50", "pr_lead_time_p90"],
                        range=["#1f77b4", "#ff7f0e"],
                    ),
                ),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(lead_chart, use_container_width=True)

        # --- Open bugs + WIP PRs chart ---
        st.caption("Open bugs and WIP PRs")
        bugs_wip_data = history_df[["week_start", "open_bugs_count", "wip_prs"]].melt(
            "week_start",
            ["open_bugs_count", "wip_prs"],
            var_name="metric",
            value_name="value",
        )

        bugs_wip_chart = (
            alt.Chart(bugs_wip_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("value:Q", title="Count"),
                color=alt.Color(
                    "metric:N",
                    title="Metric",
                    scale=alt.Scale(
                        domain=["open_bugs_count", "wip_prs"],
                        range=["#d62728", "#2ca02c"],
                    ),
                ),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(bugs_wip_chart, use_container_width=True)
    else:
        st.info("No weekly metrics found yet. Try running an analysis.")
else:
    st.info("Run an analysis from the sidebar to see weekly metrics and charts.")



if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# Render chat so far
for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask about repo health, trends, or metrics...")
if prompt:
    st.session_state["chat_history"].append(
        {"role": "user", "content": prompt}
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = answer_user_question(owner, repo, prompt)
            st.markdown(answer)

    st.session_state["chat_history"].append(
        {"role": "assistant", "content": answer}
    )
