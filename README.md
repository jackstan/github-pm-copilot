# 🚀 GitHub Engineering Health Copilot

An AI-powered engineering insights tool that analyzes a GitHub repository’s activity and produces **concise, EM/PM-ready weekly summaries**, **trend visualizations**, and **data-backed recommendations**.

It combines GitHub API ingestion, engineering metrics, anomaly detection, and an LLM agent to help teams quickly understand delivery performance, flow health, and quality trends.

#### Current Deployment: (https://github-pm-copilot.onrender.com/)
---

## 📌 What This Tool Does

### **Automated GitHub Data Ingestion**
Pulls live data for any public repo:
- Pull Requests (created/closed/merged, size, labels)
- Reviews & CI statuses
- Issues (including bug classification)
- Commits & contributors
- Releases / tags

Ingestion is incremental with checkpointed upserts:
- New/changed rows are refreshed from recent windows.
- Historical rows are retained when unchanged.
- Repeat runs can reuse fresh local data unless **Force refresh from GitHub** is selected.

### **Engineering Health Metrics (Weekly)**
- **Throughput:** merged PRs/week  
- **Lead Time:** p50 & p90  
- **WIP PRs:** open PRs at week end  
- **Aging PRs:** open > 7 days  
- **Bug Health:** open bugs, new vs closed bugs, net bug delta  
- **Team Activity:** commits/week, active contributors  

### **Anomaly Detection**
Flags unusual changes in:
- Lead time  
- Throughput  
- WIP PR count  
- Bug backlog  
- Contributor/commit volume  

### **AI-Generated Weekly Summary**
LLM produces a clear, executive-ready report:
- Bullet headline metrics  
- High-level interpretation  
- Notable anomalies  
- Drivers (e.g., PR size, CI failures, review delays, releases)  
- Actionable recommendations  

If no OpenAI API key is present, the system falls back to deterministic summaries.

### **Interactive Q&A**
Ask follow-up questions:
- “Why did lead time increase this week?”  
- “Where is delivery risk coming from?”  
- “What explains the bug backlog trend?”  
- “How healthy is our flow of work?”  

The agent answers using retrieved metrics, context, and anomalies.

### **Streamlit UI**
- Enter any public GitHub repo (`owner/repo`)  
- Choose a lookback window  
- View weekly charts  
- Read the AI-generated summary  
- Ask follow-up questions in a chat-like panel  

---

## 🧠 Architecture Overview

**UI Layer (Streamlit)**  
→ Repo input, analysis button, charts, summary, Q&A

**Orchestrator**  
→ Ingestion → metrics → anomalies → context → LLM agent

**Data Layer (SQLite)**  
→ Issues, PRs, commits, reviews, CI runs, releases

**Analytics Layer**  
→ Weekly metrics + anomaly detection

**Context Retrieval**  
→ Recent PRs, CI events, reviews, releases, history window

**LLM Agents**  
→ Weekly summary agent  
→ Q&A agent  
→ Deterministic fallback logic

Uses **structured retrieval-augmented generation (RAG)** to ground LLM outputs in real engineering data.

## ⚙️ Runtime Settings

- `DATABASE_URL`: Postgres connection string. When set, app uses Postgres.
- `ENG_HEALTH_DB_PATH`: SQLite database path fallback (default `data/eng_health.db`) when `DATABASE_URL` is not set.
- `INGEST_FRESHNESS_MINUTES`: Skip GitHub refetch if the repo was synced recently (default `30`).
- `INGEST_OVERLAP_HOURS`: Overlap window for incremental sync to catch late updates (default `24`).
- `WEEKLY_SUMMARY_CAPTURE=1`: Optional JSONL input capture for prompt/debug workflows.

## 🗄️ Render Postgres Setup

1. Create a Render Postgres instance (for example `Basic-256mb`).
2. In your web service environment variables, set:
   - `DATABASE_URL` = Render Postgres internal connection string.
3. Redeploy the web service.

Notes:
- No manual migration step is required for this project right now; tables are created on startup if missing.
- If `DATABASE_URL` is set, SQLite is ignored.
- For local development without Postgres, leave `DATABASE_URL` empty and use SQLite.

## 🔐 Security Hygiene

- Never commit real credentials (GitHub tokens, OpenAI keys, database URLs) into tracked files.
- Keep secrets only in environment variables (`.env` locally, Render environment settings in production).
- `.env` and generated eval outputs are intentionally git-ignored; keep using `.env.example` for placeholders only.
- If a credential is ever exposed, rotate it immediately and invalidate the old value.

---
# 📅 Product Roadmap

## **Short-Term Enhancements**
**Incremental ingestion & faster compute**  
Optimize ingestion to only fetch deltas.  
_PM actions: Benchmark run times, validate reliability across multiple repos._

**CI & review cycle analysis**  
Add CI pass-rate trends, flakiness detection, review latency, and PR size impact.  
_PM actions: Interview engineers on bottlenecks, identify key failure modes, define metric thresholds._

**Improved anomaly detection**  
Introduce sliding windows, confidence scoring, clustered anomalies.  
_PM actions: Create LLM + rule-based eval set to measure precision/recall of anomaly surfacing._

---

## **Mid-Term Enhancements**
**Multi-agent reasoning pipeline**  
Analyst Agent → Reviewer Agent → PM Agent for richer causal explanations.  
_PM actions: Run user testing with PMs/EMs to validate usefulness of multi-layer explanations._

**Agentic tool use (LLM-triggered GitHub fetches)**  
Allow the agent to request additional data on demand (e.g., stale PRs, CI logs).  
_PM actions: Conduct workflow mapping with engineers to ensure tool fetches align with real debugging processes._

---

## **Long-Term Enhancements**
**Cross-repo organizational dashboard**  
Roll up metrics across teams; highlight at-risk repos; exec-level ops overview.  
_PM actions: Partner with EM/Director-level users to define top cross-repo indicators._

**Semantic vector RAG for thematic analysis**  
Cluster issues/PRs, detect recurring quality themes, surface hotspots.  
_PM actions: Validate semantic clustering on a representative corpus; run PM/EM scoring of insight quality._

**GitHub App integration (OAuth & Slack digests)**  
Automated weekly summaries, notifications, and seamless repo selection.  
_PM actions: Define onboarding flow, run usability tests, validate digest usefulness with small pilot teams._

---

## 🧭 PM Responsibilities (Ongoing)
- **LLM evaluation plan:** Build a small but diverse dataset of expected summaries/Q&A answers to measure accuracy, grounding, and safety.  
- **User interviews:** Talk to PMs, EMs, and senior engineers to understand how they measure delivery health and what insights they would trust.  
- **Weekly dogfooding:** Use the tool on internal repos to identify friction points, missing context, and false positives.  
- **Metric validation:** Review whether current metrics reflect actual engineering behavior; refine definitions with engineers.  
- **Success criteria:** Define measurable outcomes (e.g., “teams use weekly summary in planning,” “early detection of long-tail PRs”).  

---
