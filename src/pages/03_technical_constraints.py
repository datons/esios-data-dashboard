from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
	TOP_CONSTRAINT_TECHNOLOGIES,
	build_constraints_daily_sql,
	build_constraints_summary_sql,
	get_api_key,
	run_query,
)


PLOTLY_LAYOUT = dict(
	margin=dict(l=0, r=0, t=36, b=0),
	legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def main() -> None:
	st.title("Technical constraints by technology")

	api_key = get_api_key()
	if not api_key:
		st.error("Missing DATONS_API_KEY. Add it to your .env file.")
		st.stop()

	with st.sidebar:
		st.header("Filters")
		start_date = st.date_input("Start date", value=date(2026, 1, 1))
		end_date = st.date_input("End date", value=date(2026, 2, 28))
		direction = st.selectbox("Direction", ["All", "Bajar", "Subir"])

	if start_date > end_date:
		st.error("Start date must be before or equal to end date.")
		st.stop()

	summary_sql = build_constraints_summary_sql(start_date, end_date)
	daily_sql = build_constraints_daily_sql(start_date, end_date)

	with st.expander("SQL queries"):
		st.caption("Summary")
		st.code(summary_sql, language="sql")
		st.caption("Daily")
		st.code(daily_sql, language="sql")

	with st.spinner("Loading constraint data..."):
		try:
			df_summary = run_query(api_key, summary_sql)
			df_daily = run_query(api_key, daily_sql)
		except AuthenticationError:
			st.error("Invalid DATONS_API_KEY.")
			st.stop()

	if len(df_summary) == 0:
		st.warning("No constraint data for the selected period.")
		st.stop()

	# Clean up
	df_summary["total_mwh"] = pd.to_numeric(df_summary["total_mwh"], errors="coerce").fillna(0.0)
	df_summary["avg_price"] = pd.to_numeric(df_summary["avg_price"], errors="coerce").fillna(0.0)
	df_summary["records"] = pd.to_numeric(df_summary["records"], errors="coerce").fillna(0).astype(int)
	df_summary["technology"] = df_summary["technology"].fillna("Unknown")

	df_daily["total_mwh"] = pd.to_numeric(df_daily["total_mwh"], errors="coerce").fillna(0.0)
	df_daily["date"] = pd.to_datetime(df_daily["date"], utc=True)
	df_daily["technology"] = df_daily["technology"].fillna("Unknown")

	# Filter direction
	if direction != "All":
		df_summary = df_summary[df_summary["sign"] == direction]
		df_daily = df_daily[df_daily["sign"] == direction]

	if len(df_summary) == 0:
		st.warning("No constraint data for the selected direction.")
		st.stop()

	# -- KPIs ------------------------------------------------------------------

	total_curtailed = float(df_summary.loc[df_summary["sign"] == "Bajar", "total_mwh"].sum()) if direction != "Subir" else 0.0
	total_raised = float(df_summary.loc[df_summary["sign"] == "Subir", "total_mwh"].sum()) if direction != "Bajar" else 0.0
	n_technologies = df_summary["technology"].nunique()
	total_records = int(df_summary["records"].sum())

	c1, c2, c3, c4 = st.columns(4)
	c1.metric("Curtailed (Bajar)", f"{total_curtailed:,.0f} MWh")
	c2.metric("Raised (Subir)", f"{total_raised:,.0f} MWh")
	c3.metric("Technologies", n_technologies)
	c4.metric("Records", f"{total_records:,}")

	# -- Bar chart: ranking by technology --------------------------------------

	df_tech = (
		df_summary
		.groupby(["technology", "sign"], as_index=False)["total_mwh"]
		.sum()
	)
	df_tech["abs_mwh"] = df_tech["total_mwh"].abs()
	df_tech = df_tech.sort_values("abs_mwh", ascending=True)

	fig = px.bar(
		df_tech,
		y="technology",
		x="total_mwh",
		color="sign",
		orientation="h",
		title="Constraint volume by technology (MWh)",
		color_discrete_map={"Bajar": "#ef4444", "Subir": "#22c55e"},
		barmode="relative",
	)
	fig.update_layout(
		yaxis_title="",
		xaxis_title="MWh",
		height=max(400, len(df_tech["technology"].unique()) * 28),
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, width="stretch")

	# -- Time series: daily constraints by top technologies --------------------

	top_techs = (
		df_daily
		.groupby("technology")["total_mwh"]
		.apply(lambda s: s.abs().sum())
		.nlargest(8)
		.index.tolist()
	)

	df_ts = df_daily[df_daily["technology"].isin(top_techs)].copy()
	# Net position per day per technology
	df_ts_net = df_ts.groupby(["date", "technology"], as_index=False)["total_mwh"].sum()

	fig = px.line(
		df_ts_net,
		x="date",
		y="total_mwh",
		color="technology",
		title="Daily net constraint volume — top 8 technologies",
	)
	fig.update_layout(
		xaxis_title="",
		yaxis_title="MWh",
		height=450,
		**PLOTLY_LAYOUT,
	)
	st.plotly_chart(fig, width="stretch")

	# -- Stacked area: Bajar only (curtailment share) --------------------------

	df_bajar = df_daily[df_daily["sign"] == "Bajar"].copy()
	if len(df_bajar) > 0:
		df_bajar["total_mwh"] = df_bajar["total_mwh"].abs()
		df_bajar_top = df_bajar[df_bajar["technology"].isin(top_techs)]
		df_area = df_bajar_top.groupby(["date", "technology"], as_index=False)["total_mwh"].sum()

		fig = px.area(
			df_area,
			x="date",
			y="total_mwh",
			color="technology",
			title="Daily curtailment by technology (absolute MWh)",
		)
		fig.update_layout(
			xaxis_title="",
			yaxis_title="MWh",
			height=450,
			**PLOTLY_LAYOUT,
		)
		st.plotly_chart(fig, width="stretch")

	# -- Correlation heatmap ---------------------------------------------------

	st.subheader("Correlation heatmap")
	st.caption("Daily curtailment volumes — Pearson correlation between technologies")

	# Pivot: rows = dates, columns = technologies, values = abs(total_mwh) for Bajar
	df_corr_src = df_daily[df_daily["sign"] == "Bajar"].copy()
	df_corr_src["total_mwh"] = df_corr_src["total_mwh"].abs()
	df_corr_src = df_corr_src.groupby(["date", "technology"], as_index=False)["total_mwh"].sum()

	# Keep technologies with enough data points
	tech_counts = df_corr_src.groupby("technology")["date"].nunique()
	min_days = max(5, len(df_corr_src["date"].unique()) * 0.3)
	valid_techs = tech_counts[tech_counts >= min_days].index.tolist()

	# Further filter to top 12 by volume for readability
	top_corr = (
		df_corr_src[df_corr_src["technology"].isin(valid_techs)]
		.groupby("technology")["total_mwh"]
		.sum()
		.nlargest(12)
		.index.tolist()
	)

	pivot = (
		df_corr_src[df_corr_src["technology"].isin(top_corr)]
		.pivot_table(index="date", columns="technology", values="total_mwh", fill_value=0)
	)

	if pivot.shape[1] >= 2:
		corr = pivot.corr()

		# Mask upper triangle
		mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
		corr_masked = corr.where(~mask)

		fig = go.Figure(data=go.Heatmap(
			z=corr_masked.values,
			x=corr.columns.tolist(),
			y=corr.index.tolist(),
			colorscale="RdBu_r",
			zmin=-1,
			zmax=1,
			text=corr.round(2).values,
			texttemplate="%{text}",
			textfont=dict(size=10),
			hoverongaps=False,
		))
		fig.update_layout(
			height=max(450, len(top_corr) * 40),
			xaxis=dict(tickangle=-45),
			margin=dict(l=0, r=0, t=10, b=0),
		)
		st.plotly_chart(fig, width="stretch")
	else:
		st.info("Not enough technologies with data for correlation analysis.")

	# -- Summary table ---------------------------------------------------------

	with st.expander("Summary table", expanded=True):
		df_table = (
			df_summary
			.groupby(["technology", "sign"], as_index=False)
			.agg({"total_mwh": "sum", "records": "sum", "avg_price": "mean"})
			.sort_values("total_mwh")
		)
		st.dataframe(
			df_table.style.format({
				"total_mwh": "{:,.0f}",
				"avg_price": "€{:,.2f}",
				"records": "{:,}",
			}),
			width="stretch",
		)


main()
