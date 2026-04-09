# ESIOS Data Dashboard

Interactive dashboard for the Spanish electricity market built with [Streamlit](https://streamlit.io/) and the [Datons](https://datons.com) ESIOS Data API.

## Quick start

```bash
# 1. Download and install
git clone https://github.com/datons/esios-data-dashboard.git
cd esios-data-dashboard
uv sync
```

Or [download as ZIP](https://github.com/datons/esios-data-dashboard/archive/refs/heads/main.zip), unzip, and run `uv sync` inside the folder.

```bash
# 2. Add your API key
cp .env.example .env
# Edit .env and paste your key
```

Get your free API key at [datons.com/account/api-keys](https://datons.com/account/api-keys).

```bash
# 3. Run the dashboard
uv run streamlit run src/app.py
```

Open [localhost:8501](http://localhost:8501).

## Pages

| Page | Description |
|------|-------------|
| **Market overview** | Spot price, demand, renewable share, technology mix |
| **Indicators** | ESIOS time series (PVPC, demand, wind, solar…) with geography filter |
| **Operational data** | Per-unit revenue, energy, captured price by market program |

## AI chat integration (MCP)

This repo includes MCP configs for both **VS Code** and **Claude Code**, so you can query the API conversationally:

- **VS Code**: The `.vscode/mcp.json` config supports OAuth (no key needed) or API key auth
- **Claude Code**: The `.mcp.json` config reads `DATONS_API_KEY` from your environment

Example questions you can ask the AI chat:
- "What was the day-ahead price in Spain yesterday?"
- "Show me BRUC's revenue by program for January 2025"
- "Add a filter by technology to the operational data page"

## Extending the dashboard

Use the AI chat in VS Code or Claude Code to modify the dashboard. Examples:

- "Add a comparison chart: nuclear vs wind generation"
- "Create a new page showing market share by company"
- "Add a download button to export data as CSV"

See [CLAUDE.md](CLAUDE.md) for the full technical reference (tables, SQL patterns, SDK reference).

## Stack

- **[uv](https://docs.astral.sh/uv/)** — dependency management
- **[Streamlit](https://streamlit.io/)** — dashboard framework
- **[Plotly](https://plotly.com/python/)** — interactive charts
- **[datons](https://pypi.org/project/datons/)** — Python SDK for the ESIOS Data API
