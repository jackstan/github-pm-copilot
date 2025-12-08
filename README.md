# GitHub PM Copilot (Engineering Health)

An experiment in building a PM-facing "engineering health" copilot on top of GitHub repo activity.

The app:

- Ingests issues, pull requests, and commits from a GitHub repo
- Stores them in a local SQLite database (`data/eng_health.db`)
- Computes simple weekly metrics (throughput, lead time, open bugs, WIP PRs)
- Exposes a **chat UI** where you can:
  - Run an analysis for a repo
  - Ask follow-up questions about the metrics

## Setup

1. **Clone the repo**

```bash
git clone https://github.com/jackstan/github-pm-copilot.git
cd github-pm-copilot
