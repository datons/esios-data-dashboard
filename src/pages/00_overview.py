from __future__ import annotations

from datetime import date, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
    get_api_key,
    run_query,
)


PLOTLY_LAYOUT = dict(
    margin=dict(l=0, r=0, t=36, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def main() -> None:
    st.title("Market overview")

    api_key = get_api_key()
    if not api_key:
        st.error("Missing DATONS_API_KEY. Add it to your .env file.")
        st.stop()

    with st.sidebar:
        st.header("Date range")
        start_date = st.date_input("Start", value=date.today() - timedelta(days=30))
        end_date = st.date_input("End", value=date.today())

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        st.stop()

    start = start_date.isoformat()
    end = end_date.isoformat()

    # Adaptive resolution
    days = (end_date - start_date).days
    if days <= 30:
        time_expr, time_alias = "toStartOfHour(datetime)", "hour"
    else:
        time_expr, time_alias = "toDate(datetime)", "date"

    # --- Queries ---

    price_sql = f"""
SELECT
    {time_expr} AS {time_alias},
    geo_name,
    avg(value) AS avg_price
FROM esios_indicators
WHERE indicator_id = 600
  AND geo_id = 3
  AND datetime >= toDateTime('{start} 00:00:00')
  AND datetime <  toDateTime('{end} 23:59:59')
GROUP BY {time_alias}, geo_name
ORDER BY {time_alias}
""".strip()

    demand_sql = f"""
SELECT
    {time_expr} AS {time_alias},
    avg(value) AS avg_demand
FROM esios_indicators
WHERE indicator_id = 10033
  AND geo_id = 8741
  AND datetime >= toDateTime('{start} 00:00:00')
  AND datetime <  toDateTime('{end} 23:59:59')
GROUP BY {time_alias}
ORDER BY {time_alias}
""".strip()

    renewables_sql = f"""
SELECT
    toDate(datetime) AS date,
    sumIf(value, indicator_id IN (10034, 10035)) AS renewable_mw,
    sumIf(value, indicator_id = 10033) AS demand_mw
FROM esios_indicators
WHERE indicator_id IN (10033, 10034, 10035)
  AND geo_id = 8741
  AND datetime >= toDateTime('{start} 00:00:00')
  AND datetime <  toDateTime('{end} 23:59:59')
GROUP BY date
ORDER BY date
""".strip()

    tech_mix_sql = f"""
SELECT
    technology,
    sum(energy) AS total_mwh
FROM operational_data
WHERE program = 'PDBF'
  AND datetime >= toDateTime('{start} 00:00:00')
  AND datetime <  toDateTime('{end} 23:59:59')
  AND technology IS NOT NULL
  AND energy > 0
GROUP BY technology
ORDER BY total_mwh DESC
LIMIT 15
""".strip()

    with st.expander("SQL queries"):
        for label, sql in [("Spot price", price_sql), ("Demand", demand_sql), ("Renewables", renewables_sql), ("Tech mix", tech_mix_sql)]:
            st.caption(label)
            st.code(sql, language="sql")

    with st.spinner("Loading market data..."):
        try:
            df_price = run_query(api_key, price_sql)
            df_demand = run_query(api_key, demand_sql)
            df_renewables = run_query(api_key, renewables_sql)
            df_tech = run_query(api_key, tech_mix_sql)
        except AuthenticationError:
            st.error("Invalid DATONS_API_KEY.")
            st.stop()

    # --- KPIs ---

    import pandas as pd

    if len(df_price) == 0 and len(df_demand) == 0:
        st.warning("No data for the selected date range. The dataset covers 2023-01-01 to 2025-12-11.")
        st.stop()

    for col in ("avg_price",):
        if col in df_price.columns:
            df_price[col] = pd.to_numeric(df_price[col], errors="coerce")
    for col in ("avg_demand",):
        if col in df_demand.columns:
            df_demand[col] = pd.to_numeric(df_demand[col], errors="coerce")
    for col in ("renewable_mw", "demand_mw"):
        if col in df_renewables.columns:
            df_renewables[col] = pd.to_numeric(df_renewables[col], errors="coerce")
    for col in ("total_mwh",):
        if col in df_tech.columns:
            df_tech[col] = pd.to_numeric(df_tech[col], errors="coerce")

    avg_price = float(df_price["avg_price"].mean()) if len(df_price) else 0
    avg_demand = float(df_demand["avg_demand"].mean()) if len(df_demand) else 0
    renewable_pct = 0.0
    if len(df_renewables) and df_renewables["demand_mw"].sum() > 0:
        renewable_pct = float(df_renewables["renewable_mw"].sum() / df_renewables["demand_mw"].sum() * 100)

    c1, c2, c3 = st.columns(3)
    c1.metric("Avg spot price", f"€{avg_price:,.2f}/MWh")
    c2.metric("Avg demand", f"{avg_demand:,.0f} MW")
    c3.metric("Wind+Solar share", f"{renewable_pct:.1f}%")

    # --- Charts ---

    time_col = time_alias

    # Spot price
    if len(df_price) == 0:
        st.info("No price data for the selected range.")
        st.stop()

    df_price[time_col] = pd.to_datetime(df_price[time_col], utc=True)
    fig_price = px.line(
        df_price, x=time_col, y="avg_price",
        title="Spot price (PVPC) — Península",
    )
    fig_price.update_traces(line_color="#2563eb", line_width=1.5)
    fig_price.update_layout(xaxis_title="", yaxis_title="€/MWh", **PLOTLY_LAYOUT)
    st.plotly_chart(fig_price, use_container_width=True)

    # Demand + Renewables side by side
    left, right = st.columns(2)

    with left:
        df_demand[time_col] = pd.to_datetime(df_demand[time_col], utc=True)
        fig_demand = px.area(
            df_demand, x=time_col, y="avg_demand",
            title="Electricity demand — Península",
        )
        fig_demand.update_traces(line_color="#2563eb", fillcolor="rgba(37, 99, 235, 0.12)")
        fig_demand.update_layout(xaxis_title="", yaxis_title="MW", **PLOTLY_LAYOUT)
        st.plotly_chart(fig_demand, use_container_width=True)

    with right:
        df_renewables["date"] = pd.to_datetime(df_renewables["date"], utc=True)
        df_renewables["renewable_pct"] = df_renewables["renewable_mw"] / df_renewables["demand_mw"].replace(0, float("nan")) * 100
        fig_ren = px.bar(
            df_renewables, x="date", y="renewable_pct",
            title="Daily wind+solar share",
            color_discrete_sequence=["#16a34a"],
        )
        fig_ren.update_layout(xaxis_title="", yaxis_title="%", **PLOTLY_LAYOUT)
        st.plotly_chart(fig_ren, use_container_width=True)

    # Technology mix
    if len(df_tech) > 0:
        fig_tech = px.bar(
            df_tech, x="technology", y="total_mwh",
            title="Day-ahead energy by technology (PDBF)",
            text_auto=".2s",
            color_discrete_sequence=["#2563eb"],
        )
        fig_tech.update_layout(xaxis_title="", yaxis_title="MWh", xaxis_tickangle=-45, **PLOTLY_LAYOUT)
        st.plotly_chart(fig_tech, use_container_width=True)

    # --- Data ---

    with st.expander("Price data"):
        st.dataframe(df_price, use_container_width=True, height=300)


main()
