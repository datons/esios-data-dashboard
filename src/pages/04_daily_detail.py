from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
	DEFAULT_PROGRAMS,
	build_hourly_detail_sql,
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
	st.title("Daily detail")

	api_key = get_api_key()
	if not api_key:
		st.error("Missing DATONS_API_KEY. Add it to your .env file.")
		st.stop()

	try:
		units_data = load_units_enriched(api_key)
	except AuthenticationError:
		st.error("Invalid DATONS_API_KEY.")
		st.stop()

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

		default_idx = 0
		if not search:
			default_label = next((l for l in filtered if l.startswith("BRUC ")), None)
			if default_label:
				default_idx = filtered.index(default_label)

		selected_label = st.selectbox("Unit", filtered, index=default_idx)
		unit = unit_labels.get(selected_label, "BRUC")
		selected_day = st.date_input("Day", value=date(2025, 6, 15))

	# Unit metadata
	unit_info = next((u for u in units_data if u["unit"] == unit), None)
	if unit_info:
		cols = st.columns(4)
		cols[0].metric("Unit", unit_info.get("unit_name") or unit)
		cols[1].metric("Technology", unit_info.get("technology") or "—")
		cols[2].metric("Company", unit_info.get("company_name") or "—")
		cols[3].metric("Day", selected_day.strftime("%a %d %b %Y"))

	sql = build_hourly_detail_sql(unit, selected_day)

	with st.expander("SQL query"):
		st.code(sql, language="sql")

	with st.spinner("Loading hourly data..."):
		try:
			df = run_query(api_key, sql)
		except AuthenticationError:
			st.error("Invalid DATONS_API_KEY.")
			st.stop()

	if len(df) == 0:
		st.warning("No data for the selected unit and day.")
		st.stop()

	df["hour"] = pd.to_datetime(df["hour"])
	for col in ("total_energy", "avg_price", "revenue"):
		df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

	# Hour label for x-axis (0h, 1h, ..., 23h)
	df["hour_label"] = df["hour"].dt.strftime("%Hh")

	# -- KPIs ------------------------------------------------------------------

	total_energy = float(df["total_energy"].sum())
	total_revenue = float(df["revenue"].sum())
	weighted_price = total_revenue / total_energy if total_energy else 0.0
	n_programs = df["program"].nunique()

	c1, c2, c3, c4 = st.columns(4)
	c1.metric("Energy (MWh)", f"{total_energy:,.0f}")
	c2.metric("Revenue", format_currency(total_revenue))
	c3.metric("Avg captured price", format_currency(weighted_price))
	c4.metric("Programs", n_programs)

	# -- Energy by program (stacked bar) ---------------------------------------

	fig = px.bar(
		df,
		x="hour_label",
		y="total_energy",
		color="program",
		title="Hourly energy by program (MWh)",
		barmode="relative",
	)
	fig.update_layout(
		xaxis_title="",
		yaxis_title="MWh",
		xaxis=dict(dtick=1),
		height=400,
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, use_container_width=True)

	# -- Price by program (lines) ----------------------------------------------

	fig = px.line(
		df,
		x="hour_label",
		y="avg_price",
		color="program",
		title="Hourly price by program (€/MWh)",
		markers=True,
	)
	fig.update_layout(
		xaxis_title="",
		yaxis_title="€/MWh",
		xaxis=dict(dtick=1),
		height=400,
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, use_container_width=True)

	# -- Revenue by program (stacked bar) --------------------------------------

	fig = px.bar(
		df,
		x="hour_label",
		y="revenue",
		color="program",
		title="Hourly revenue by program (€)",
		barmode="relative",
	)
	fig.update_layout(
		xaxis_title="",
		yaxis_title="€",
		xaxis=dict(dtick=1),
		height=400,
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, use_container_width=True)

	# -- Table -----------------------------------------------------------------

	with st.expander("Hourly data table", expanded=True):
		# Pivot: hours as rows, programs as columns, energy as values
		pivot_energy = df.pivot_table(
			index="hour_label",
			columns="program",
			values="total_energy",
			fill_value=0,
			aggfunc="sum",
		)
		pivot_energy["Total"] = pivot_energy.sum(axis=1)

		st.caption("Energy (MWh)")
		st.dataframe(
			pivot_energy.style.format("{:,.1f}"),
			use_container_width=True,
		)

	with st.expander("Price table"):
		pivot_price = df.pivot_table(
			index="hour_label",
			columns="program",
			values="avg_price",
			fill_value=0,
			aggfunc="mean",
		)

		st.caption("Average price (€/MWh)")
		st.dataframe(
			pivot_price.style.format("€{:,.2f}"),
			use_container_width=True,
		)

	with st.expander("Raw data"):
		st.dataframe(df, use_container_width=True, height=400)


main()
