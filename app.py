import sys
from pathlib import Path

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

st.set_page_config(page_title="GitHub PM Copilot", layout="wide")

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

if st.sidebar.button("Run analysis"):
    with st.spinner("Analyzing repo activity..."):
        summary = run_full_analysis(owner, repo, days_back=days_back)
    st.session_state.setdefault("chat_history", [])
    st.session_state["chat_history"].append(
        {"role": "assistant", "content": summary}
    )

st.title("GitHub PM Copilot (Eng Health)")

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
