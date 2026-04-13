from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
	DEFAULT_PROGRAMS,
	build_report_program_summary_sql,
	build_report_timeseries_sql,
	build_report_top_units_sql,
	format_currency,
	get_api_key,
	load_companies,
	load_units_enriched,
	run_query,
)


PLOTLY_LAYOUT = dict(
	margin=dict(l=0, r=0, t=36, b=0),
	legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def main() -> None:
	st.title("Program report")

	api_key = get_api_key()
	if not api_key:
		st.error("Missing DATONS_API_KEY. Add it to your .env file.")
		st.stop()

	try:
		units_data = load_units_enriched(api_key)
		companies = load_companies(api_key)
	except AuthenticationError:
		st.error("Invalid DATONS_API_KEY.")
		st.stop()

	# Build unit labels for multiselect
	unit_labels: dict[str, str] = {}
	for u in units_data:
		code = u["unit"]
		name = u.get("unit_name") or ""
		tech = u.get("technology") or ""
		label = f"{code} — {name}" if name else code
		if tech:
			label += f" ({tech})"
		unit_labels[label] = code

	# --- Sidebar filters ---

	with st.sidebar:
		st.header("Filters")
		mode = st.radio("Select by", ["Company", "Units"], horizontal=True)

		selected_units: list[str] | None = None
		selected_company: str | None = None

		if mode == "Company":
			import random
			selected_company = st.selectbox("Company", companies, index=random.randint(0, len(companies) - 1))
			if selected_company:
				company_units = [u["unit"] for u in units_data if u.get("company_name") == selected_company]
				st.caption(f"{len(company_units)} units in this company")
		else:
			search = st.text_input("Search units", placeholder="Type unit, company, or technology...")
			if search:
				q = search.lower()
				filtered = sorted(l for l in unit_labels if q in l.lower())
			else:
				filtered = sorted(unit_labels.keys())

			chosen_labels = st.multiselect("Units", filtered, max_selections=50)
			if not chosen_labels:
				st.info("Select at least one unit.")
				st.stop()
			selected_units = [unit_labels[l] for l in chosen_labels]

		start_date = st.date_input("Start date", value=date(2025, 1, 1))
		end_date = st.date_input("End date", value=date.today())

	if start_date > end_date:
		st.error("Start date must be before or equal to end date.")
		st.stop()

	# --- Build queries ---

	summary_sql = build_report_program_summary_sql(start_date, end_date, units=selected_units, company=selected_company)
	top_units_sql = build_report_top_units_sql(start_date, end_date, units=selected_units, company=selected_company)
	ts_sql = build_report_timeseries_sql(start_date, end_date, units=selected_units, company=selected_company)

	with st.expander("SQL queries"):
		for label, sql in [("Program summary", summary_sql), ("Top units", top_units_sql), ("Time series", ts_sql)]:
			st.caption(label)
			st.code(sql, language="sql")

	# --- Run queries ---

	with st.spinner("Loading report data..."):
		try:
			df_summary = run_query(api_key, summary_sql)
			df_top = run_query(api_key, top_units_sql)
			df_ts = run_query(api_key, ts_sql)
		except AuthenticationError:
			st.error("Invalid DATONS_API_KEY.")
			st.stop()

	if len(df_summary) == 0:
		st.warning("No data for the selected filters.")
		st.stop()

	# --- Coerce types ---

	for col in ("total_energy", "avg_price", "revenue"):
		df_summary[col] = pd.to_numeric(df_summary[col], errors="coerce").fillna(0.0)
		if col in df_top.columns:
			df_top[col] = pd.to_numeric(df_top[col], errors="coerce").fillna(0.0)

	time_col = "hour" if "hour" in df_ts.columns else "date"
	if len(df_ts):
		df_ts[time_col] = pd.to_datetime(df_ts[time_col], utc=True)
		for col in ("total_energy", "revenue"):
			df_ts[col] = pd.to_numeric(df_ts[col], errors="coerce").fillna(0.0)

	# --- KPIs ---

	total_revenue = float(df_summary["revenue"].sum())
	total_energy = float(df_summary["total_energy"].sum())
	num_programs = len(df_summary)
	num_units = len(df_top)

	c1, c2, c3, c4 = st.columns(4)
	c1.metric("Total revenue", format_currency(total_revenue))
	c2.metric("Total energy (MWh)", f"{total_energy:,.0f}")
	c3.metric("Programs", num_programs)
	c4.metric("Units", num_units)

	# --- Charts ---

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
		fig = px.bar(
			df_summary.sort_values("total_energy", ascending=False),
			x="program",
			y="total_energy",
			title="Energy by program (MWh)",
			text_auto=".2s",
			color_discrete_sequence=["#16a34a"],
		)
		fig.update_layout(xaxis_title="", yaxis_title="MWh", **PLOTLY_LAYOUT)
		st.plotly_chart(fig, width="stretch")

	# Revenue over time by program
	if len(df_ts):
		fig = px.area(
			df_ts,
			x=time_col,
			y="revenue",
			color="program",
			title="Revenue over time by program",
		)
		fig.update_layout(xaxis_title="", yaxis_title="€", **PLOTLY_LAYOUT)
		st.plotly_chart(fig, width="stretch")

	# Energy over time by program
	if len(df_ts):
		fig = px.line(
			df_ts,
			x=time_col,
			y="total_energy",
			color="program",
			title="Energy over time by program (MWh)",
		)
		fig.update_layout(xaxis_title="", yaxis_title="MWh", **PLOTLY_LAYOUT)
		st.plotly_chart(fig, width="stretch")

	# --- Top units table ---

	if len(df_top):
		st.subheader("Top units by revenue")
		st.dataframe(
			df_top.style.format({
				"total_energy": "{:,.0f}",
				"avg_price": "€{:,.2f}",
				"revenue": "€{:,.0f}",
			}),
			width="stretch",
		)

	# --- Program summary table ---

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


main()
