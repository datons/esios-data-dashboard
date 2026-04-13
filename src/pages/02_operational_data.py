from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
	DEFAULT_PROGRAMS,
	build_capture_sql,
	build_daily_sql,
	build_program_summary_sql,
	format_currency,
	get_api_key,
	load_units_enriched,
	run_query,
)


PLOTLY_LAYOUT = dict(
	margin=dict(l=0, r=0, t=36, b=0),
	legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def main() -> None:
	st.title("Operational data")

	api_key = get_api_key()
	if not api_key:
		st.error("Missing DATONS_API_KEY. Add it to your .env file.")
		st.stop()

	try:
		units_data = load_units_enriched(api_key)
	except AuthenticationError:
		st.error("Invalid DATONS_API_KEY.")
		st.stop()

	# Build searchable labels: "BRUC — PS HUELVA 2021 BRUC (Solar PV, IGNIS COMER ELECTRICA)"
	unit_labels = {}
	for u in units_data:
		code = u["unit"]
		parts = [u.get("unit_name") or ""]
		meta_parts = [p for p in [u.get("technology"), u.get("company_name")] if p]
		label = f"{code} — {parts[0]}" if parts[0] else code
		if meta_parts:
			label += f" ({', '.join(meta_parts)})"
		unit_labels[label] = code

	with st.sidebar:
		st.header("Filters")
		search = st.text_input("Search unit", placeholder="Type unit, company, or technology...")
		if search:
			q = search.lower()
			filtered = [l for l in sorted(unit_labels.keys()) if q in l.lower()]
		else:
			filtered = sorted(unit_labels.keys())

		if not filtered:
			st.warning(f"No units matching '{search}'")
			st.stop()

		import random
		default_idx = random.randint(0, len(filtered) - 1) if not search else 0

		selected_label = st.selectbox("Unit", filtered, index=default_idx)
		unit = unit_labels.get(selected_label, "")
		program = st.selectbox("Program", ["All"] + DEFAULT_PROGRAMS)
		start_date = st.date_input("Start date", value=date(2025, 1, 1))
		end_date = st.date_input("End date", value=date.today())

	if start_date > end_date:
		st.error("Start date must be before or equal to end date.")
		st.stop()

	# Unit metadata card
	unit_info = next((u for u in units_data if u["unit"] == unit), None)
	if unit_info:
		cols = st.columns(4)
		cols[0].metric("Unit", unit_info.get("unit_name") or unit)
		cols[1].metric("Technology", unit_info.get("technology") or "—")
		cols[2].metric("Company", unit_info.get("company_name") or "—")
		cols[3].metric("Code", unit)

	program_value = None if program == "All" else program

	time_sql = build_daily_sql(unit, start_date, end_date, program_value)
	summary_sql = build_program_summary_sql(unit, start_date, end_date)
	capture_sql = build_capture_sql(unit, start_date, end_date)

	with st.expander("SQL queries"):
		for label, sql in [("Time series", time_sql), ("Summary", summary_sql), ("Capture", capture_sql)]:
			st.caption(label)
			st.code(sql, language="sql")

	with st.spinner("Loading operational data..."):
		try:
			df_time = run_query(api_key, time_sql)
			df_summary = run_query(api_key, summary_sql)
			df_capture = run_query(api_key, capture_sql)
		except AuthenticationError:
			st.error("Invalid DATONS_API_KEY.")
			st.stop()

	if len(df_time) == 0:
		st.warning("No rows returned for the selected filters.")
		st.stop()

	time_col = "hour" if "hour" in df_time.columns else "date"
	df_time[time_col] = pd.to_datetime(df_time[time_col], utc=True)
	for col in ("total_energy", "avg_price", "revenue"):
		df_time[col] = pd.to_numeric(df_time[col], errors="coerce").fillna(0.0)

	capture_time_col = "hour" if "hour" in df_capture.columns else "date"
	df_capture[capture_time_col] = pd.to_datetime(df_capture[capture_time_col], utc=True)
	for col in ("captured_price", "market_price"):
		df_capture[col] = pd.to_numeric(df_capture[col], errors="coerce").fillna(0.0)

	for col in ("total_energy", "avg_price", "revenue"):
		df_summary[col] = pd.to_numeric(df_summary[col], errors="coerce").fillna(0.0)

	# -- KPIs ------------------------------------------------------------------

	total_revenue = float(df_summary["revenue"].sum())
	total_energy = float(df_summary["total_energy"].sum())
	weighted_capture = total_revenue / total_energy if total_energy else 0.0
	avg_market = float(df_capture["market_price"].mean()) if len(df_capture) else 0.0

	c1, c2, c3, c4 = st.columns(4)
	c1.metric("Revenue", format_currency(total_revenue))
	c2.metric("Energy (MWh)", f"{total_energy:,.0f}")
	c3.metric("Market price", format_currency(avg_market))
	c4.metric("Captured price", format_currency(weighted_capture))

	# -- Charts ----------------------------------------------------------------

	left, right = st.columns(2)

	with left:
		fig = px.bar(
			df_summary.sort_values("revenue", ascending=False),
			x="program",
			y="revenue",
			title="Revenue by program",
			text_auto=".2s",
			color_discrete_sequence=["#2563eb"],
		)
		fig.update_layout(xaxis_title="", yaxis_title="€", **PLOTLY_LAYOUT)
		st.plotly_chart(fig, width="stretch")

	with right:
		daily_revenue = df_time.groupby(time_col, as_index=False)["revenue"].sum()
		fig = px.area(daily_revenue, x=time_col, y="revenue", title="Revenue over time")
		fig.update_traces(line_color="#2563eb", fillcolor="rgba(37, 99, 235, 0.12)")
		fig.update_layout(xaxis_title="", yaxis_title="€", **PLOTLY_LAYOUT)
		st.plotly_chart(fig, width="stretch")

	fig = go.Figure()
	fig.add_trace(go.Scatter(
		x=df_capture[capture_time_col], y=df_capture["captured_price"],
		mode="lines", name="Captured",
		line=dict(color="#2563eb", width=2),
	))
	fig.add_trace(go.Scatter(
		x=df_capture[capture_time_col], y=df_capture["market_price"],
		mode="lines", name="Market",
		line=dict(color="#9ca3af", dash="dot", width=1.5),
	))
	fig.update_layout(
		title="Captured price vs market price (€/MWh)",
		xaxis_title="", yaxis_title="€/MWh",
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, width="stretch")

	# -- Energy by program over time -------------------------------------------

	fig = px.line(
		df_time,
		x=time_col,
		y="total_energy",
		color="program",
		title="Energy by program over time (MWh)",
	)
	fig.update_layout(xaxis_title="", yaxis_title="MWh", **PLOTLY_LAYOUT)
	st.plotly_chart(fig, width="stretch")

	# -- Tables ----------------------------------------------------------------

	with st.expander("Program summary", expanded=True):
		st.dataframe(
			df_summary.style.format({
				"total_energy": "{:,.0f}",
				"avg_price": "€{:,.2f}",
				"revenue": "€{:,.0f}",
				"records": "{:,}",
			}),
			width="stretch",
		)

	with st.expander("Time series data"):
		st.dataframe(df_time, width="stretch", height=400)


main()
