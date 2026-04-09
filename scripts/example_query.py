"""Example: query the Datons ESIOS Data API from Python.

Run:
    uv run scripts/example_query.py
"""

from dotenv import load_dotenv

from datons import Client

load_dotenv()

client = Client()  # reads DATONS_API_KEY from .env or environment

# -- 1. Explore what's available -----------------------------------------------

# Dataset metadata (schema, programs, global stats)
meta = client.esios.metadata(lang="en", detail="summary")
print(f"Table: {meta.schema_info.table}")
print(f"Total rows: {meta.global_stats.total_rows:,}")
print(f"Unique units: {meta.global_stats.unique_units}")
print(f"Date range: {meta.global_stats.date_min} → {meta.global_stats.date_max}")
print()

# Available programs
print("Programs:")
for p in meta.programs:
    print(f"  {p.code:6s}  {p.name}")
print()

# Search for a unit by name
dims = client.esios.dimensions("unit", detail="summary", q="BRUC")
print(f"Units matching 'BRUC': {dims.values}")

# Look up which company and technology a unit belongs to
df = client.esios.query(
    """
    SELECT DISTINCT unit, unit_name, company_name, technology, unit_type, power
    FROM operational_data
    WHERE unit = 'BRUC'
    """,
    backend="pandas",
)
print(f"\nUnit details:\n{df.to_string(index=False)}")

# -- 2. Aggregated queries (up to 10,000 rows) --------------------------------

# Daily revenue for a unit
df_daily = client.esios.query(
    """
    SELECT
        toDate(datetime) AS date,
        program,
        sum(energy) AS total_energy,
        avg(price) AS avg_price,
        sum(energy * price) AS revenue
    FROM operational_data
    WHERE unit = 'BRUC'
      AND datetime >= toDateTime('2025-01-01 00:00:00')
      AND datetime <  toDateTime('2025-04-01 00:00:00')
    GROUP BY date, program
    ORDER BY date, program
    """,
    backend="pandas",
)
print(f"\nDaily aggregation: {len(df_daily)} rows")
print(df_daily.head())

# Indicator time series (day-ahead price, daily)
df_price = client.esios.query(
    """
    SELECT
        toDate(datetime) AS date,
        geo_name,
        avg(value) AS avg_value,
        min(value) AS min_value,
        max(value) AS max_value
    FROM esios_indicators
    WHERE indicator_id = 1001
      AND datetime >= toDateTime('2025-01-01 00:00:00')
      AND datetime <  toDateTime('2025-04-01 00:00:00')
    GROUP BY date, geo_name
    ORDER BY date, geo_name
    """,
    backend="pandas",
)
print(f"\nDay-ahead price by country: {len(df_price)} rows, geos: {sorted(df_price['geo_name'].unique())}")
print(df_price.head())
