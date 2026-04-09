# ESIOS Data Dashboard — Technical Reference

> Setup, pages, and general info → see [README.md](README.md)

## API query limits (critical)

| Type | Detection | Max rows | When to use |
|------|-----------|----------|-------------|
| **Raw** (no `GROUP BY`) | `query_type: "raw"` | **50** | Quick peek at individual records |
| **Aggregated** (with `GROUP BY`) | `query_type: "aggregated"` | **10,000** | Time series, summaries, analytics |

**All meaningful queries MUST use `GROUP BY`.** A raw query silently truncates to 50 rows.

## Tables

### `operational_data` (~1.3B rows)

I90 settlement data: energy dispatched and price per unit, program, and hour.

| Column | Type | Description |
|--------|------|-------------|
| `unit` | String | Generation unit code (e.g., `BRUC`, `CTGN1`) |
| `datetime` | DateTime (Europe/Madrid) | Settlement period |
| `program` | String | Market program (see below) |
| `energy` | Float64 | MWh (negative = consumption/purchase) |
| `price` | Float64 | €/MWh |
| `unit_name` | Nullable(String) | Human-readable unit name |
| `company_name` | String | Owner company |
| `company_code` | String | Company code |
| `technology` | String | Generation technology (Solar PV, Nuclear, Ciclo Combinado...) |
| `unit_type` | String | Generation, Consumption, etc. |
| `power` | Nullable(Float64) | Installed capacity (MW) |
| `sign` | Nullable(String) | Subir/Bajar — only in balance programs |
| `redispatch` | Nullable(String) | Redispatch mechanism type |
| `session` | Nullable(String) | Intraday session number |
| `offer_type` | Nullable(String) | Offer type |
| `source_interval` | String | Data resolution (`1h` or `15min`) |

**Market programs:**

| Code | Name | Description |
|------|------|-------------|
| PDBF | Programa Diario Base | Day-ahead market schedule |
| PDVP | Programa Diario Viable | After resolving day-ahead constraints |
| PHF1–PHF7 | Sesiones intradiarias | Intraday sessions 1 through 7 |
| BS | Balance de servicios | Balance services |
| RR | Reserva de reemplazo | Replacement reserve |
| BT | Balance en tiempo real | Real-time balance |
| RTR | Restricciones técnicas TR | Real-time technical constraints |

### `esios_indicators` (~192M rows)

ESIOS public indicators: PVPC, day-ahead price, demand, renewable generation, etc.

| Column | Type | Description |
|--------|------|-------------|
| `indicator_id` | UInt32 | ESIOS indicator number |
| `datetime` | DateTime (Europe/Madrid) | Timestamp |
| `value` | Float64 | Indicator value |
| `indicator_name` | String | Human-readable name (in Spanish) |
| `geo_id` | UInt32 | Geography ID |
| `geo_name` | String | Geography name (Península, Baleares, Canarias, España, Alemania...) |
| `unit` | String | Measurement unit (€/MWh, MW, MWh...) |
| `magnitude` | String | What it measures (Energía, Precio €/MWh...) |
| `frequency` | String | Original resolution (Quince minutos, Hora...) |

**Important:** Different indicators have different geographies AND different units. Always `GROUP BY geo_name` when querying all geographies. Common geo_ids: 3 = España (prices), 8741 = Península (demand, generation).

**Common indicators:**

| ID | Name | Unit | geo_id |
|----|------|------|--------|
| 600 | PVPC | €/MWh | 3 |
| 1001 | Day-ahead price | €/MWh | 3 |
| 10033 | Demand | MW | 8741 |
| 10034 | Wind generation | MW | 8741 |
| 10035 | Solar PV generation | MW | 8741 |

### `operational_data_15min` (~2.3B rows)

Same as `operational_data` but at 15-minute resolution. Use only when sub-hourly granularity is needed.

## Discovering units, companies, and technologies

```python
from datons import Client
client = Client()  # reads DATONS_API_KEY from env

client.esios.dimensions("unit", detail="summary", q="BRUC")     # → ['BRUC', 'SHEPV08']
client.esios.dimensions("company", detail="summary")             # → 695 companies
client.esios.dimensions("technology", detail="summary")          # → 77 technologies
client.esios.metadata(lang="es", detail="full")                  # schema, programs, stats
```

## ClickHouse SQL specifics

- Time bucketing: `toDate()`, `toStartOfHour()`, `toStartOfMonth()`
- Division safety: `nullIf(sum(energy), 0)` to avoid division by zero
- Datetime filters: `toDateTime('2025-01-01 00:00:00')` format
- Count: `count()` without arguments (not `count(*)`)
- Adaptive resolution: ≤30 days → `toStartOfHour()`, >30 days → `toDate()`

## Query templates

**Time series (operational):**
```sql
SELECT toDate(datetime) AS date, program, sum(energy) AS total_energy, avg(price) AS avg_price, sum(energy * price) AS revenue
FROM operational_data
WHERE unit = '{unit}' AND datetime >= toDateTime('{start} 00:00:00') AND datetime < toDateTime('{end} 23:59:59')
GROUP BY date, program ORDER BY date, program
```

**Captured price vs market:**
```sql
SELECT toDate(datetime) AS date, sum(energy * price) / nullIf(sum(energy), 0) AS captured_price, avg(price) AS market_price
FROM operational_data WHERE unit = '{unit}' ...
GROUP BY date ORDER BY date
```

**Indicator with geographies:**
```sql
SELECT toStartOfHour(datetime) AS hour, geo_name, avg(value) AS avg_value
FROM esios_indicators WHERE indicator_id = {id} ...
GROUP BY hour, geo_name ORDER BY hour, geo_name
```

## File structure

```
├── README.md                   # Setup and overview (for humans)
├── CLAUDE.md                   # Technical reference (for AI chat)
├── pyproject.toml
├── .env.example
├── scripts/
│   └── example_query.py
└── src/
    ├── app.py                  # Streamlit entrypoint
    ├── lib/
    │   ├── __init__.py
    │   ├── client.py           # API client: run_query, load_units_enriched
    │   ├── queries.py          # SQL builders (always with GROUP BY)
    │   └── formatting.py       # format_currency
    └── pages/
        ├── 00_overview.py      # Market overview
        ├── 01_indicators.py    # ESIOS indicator time series
        └── 02_operational_data.py  # Per-unit operational data
```

## Adding a new page

1. Create `src/pages/03_new_page.py`
2. Add query builders to `src/lib/queries.py` — always with `GROUP BY`
3. Use `_resolution(start, end)` for adaptive time bucketing
4. Use `_sanitize()` for any user-provided string in SQL
5. Show the SQL in an `st.expander` so analysts can learn
6. Use `use_container_width=True` on all charts
7. Register the page in `src/app.py` with `st.Page()` and an icon

## SDK reference

```python
from datons import Client
client = Client()                                            # reads DATONS_API_KEY
df = client.esios.query("SELECT ...", backend="pandas")      # → pandas DataFrame
df = client.esios.query("SELECT ...")                        # → polars DataFrame (default)
result = client.esios.query_raw("SELECT ...")                # → raw result with metadata
meta = client.esios.metadata(lang="es", detail="full")       # schema, programs, stats
client.esios.dimensions("unit", q="solar")                   # dimension lookup
```

## Common questions for the chat

- "Add a filter by technology to the operational data page"
- "Show the top 10 units with most revenue in the overview"
- "Add a comparison chart: nuclear vs wind generation over time"
- "Create a new page showing market share by company"
- "Add a download button to export the data as CSV"
- "Compare the captured price of two units side by side"

## How to modify the dashboard

**New filter:** `st.selectbox` in sidebar → pass to query builder → add `WHERE` clause.
**New metric:** compute from DataFrame → `st.metric()` in `st.columns()`.
**New chart:** `px.line`/`px.bar`/`px.area` with `use_container_width=True`. Show SQL in `st.expander`.
**New page:** `src/pages/03_name.py` → register in `src/app.py`.
