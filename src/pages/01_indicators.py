from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datons.exceptions import AuthenticationError

from lib import (
	COMMON_INDICATORS,
	build_indicator_geo_sql,
	build_indicator_meta_sql,
	build_indicator_sql,
	get_api_key,
	load_indicators,
	normalize_query_result,
	run_query,
)


PLOTLY_LAYOUT = dict(
	margin=dict(l=0, r=0, t=36, b=0),
	legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def load_geos(token: str, indicator_id: int) -> pd.DataFrame:
	sql = build_indicator_geo_sql(indicator_id)
	return normalize_query_result(run_query(token, sql))


def load_meta(token: str, indicator_id: int) -> dict:
	sql = build_indicator_meta_sql(indicator_id)
	df = normalize_query_result(run_query(token, sql))
	if len(df) == 0:
		return {"indicator_name": f"Indicator {indicator_id}", "unit": "", "magnitude": ""}
	row = df.iloc[0]
	return {
		"indicator_name": str(row.get("indicator_name", "")),
		"unit": str(row.get("unit", "")),
		"magnitude": str(row.get("magnitude", "")),
	}


@st.cache_data(ttl=600)
def load_indicator_frame(token: str, sql: str) -> pd.DataFrame:
	return normalize_query_result(run_query(token, sql))


def main() -> None:
	st.title("ESIOS indicators")

	api_key = get_api_key()
	if not api_key:
		st.error("Missing DATONS_API_KEY. Add it to your .env file.")
		st.stop()

	with st.sidebar:
		st.header("Indicator")

		indicators = load_indicators(api_key)
		# Build lookup: id → name, with common indicators first
		common_ids = {iid for iid, _ in COMMON_INDICATORS}
		indicator_options = [ind for ind in indicators if ind["id"] in common_ids] + \
			[ind for ind in indicators if ind["id"] not in common_ids]

		selected = st.selectbox(
			"Search indicator",
			options=indicator_options,
			format_func=lambda ind: f"{ind['name']} ({ind['id']})",
			index=0,
		)
		indicator_id = selected["id"]

		start_date = st.date_input("Start date", value=date(2025, 1, 1))
		end_date = st.date_input("End date", value=date.today())

	if start_date > end_date:
		st.error("Start date must be before or equal to end date.")
		st.stop()

	try:
		geos = load_geos(api_key, int(indicator_id))
		meta = load_meta(api_key, int(indicator_id))
	except AuthenticationError:
		st.error("Invalid DATONS_API_KEY.")
		st.stop()

	geo_options: list[tuple[int | None, str]] = [(None, "All geographies")]
	if len(geos) > 0:
		for _, row in geos.iterrows():
			geo_options.append((int(row["geo_id"]), str(row.get("geo_name", row["geo_id"]))))

	with st.sidebar:
		geo_choice_label = st.selectbox(
			"Geography",
			[label for _, label in geo_options],
		)
		geo_choice = next(gid for gid, label in geo_options if label == geo_choice_label)

	sql = build_indicator_sql(int(indicator_id), start_date, end_date, geo_choice)

	with st.expander("SQL query"):
		st.code(sql, language="sql")

	with st.spinner("Loading indicator data..."):
		try:
			df = load_indicator_frame(api_key, sql)
		except AuthenticationError:
			st.error("Invalid DATONS_API_KEY.")
			st.stop()

	if len(df) == 0:
		st.warning("No rows returned for the selected indicator and date range.")
		st.stop()

	time_col = "hour" if "hour" in df.columns else "date"
	df[time_col] = pd.to_datetime(df[time_col], utc=True)
	for col in ("avg_value", "min_value", "max_value"):
		df[col] = pd.to_numeric(df[col], errors="coerce")

	indicator_name = meta["indicator_name"] or selected["name"]
	y_unit = meta["unit"] or "Value"
	has_multi_geo = "geo_name" in df.columns

	# -- KPIs ------------------------------------------------------------------

	c1, c2, c3 = st.columns(3)
	c1.metric("Indicator", indicator_name[:40])
	c2.metric("Unit", y_unit)
	c3.metric("Data points", f"{len(df):,}")

	# -- Chart -----------------------------------------------------------------

	if has_multi_geo:
		# Multiple geos: one line per geography
		fig = px.line(
			df.sort_values([time_col, "geo_name"]),
			x=time_col,
			y="avg_value",
			color="geo_name",
			title=f"{selected["name"]} (indicator {int(indicator_id)})",
		)
		fig.update_layout(
			xaxis_title="", yaxis_title=y_unit,
			**PLOTLY_LAYOUT,
		)
	else:
		# Single geo: line with min/max band
		fig = go.Figure()
		fig.add_trace(go.Scatter(
			x=df[time_col], y=df["avg_value"],
			mode="lines", name="Average",
			line=dict(color="#2563eb", width=2),
		))
		fig.add_trace(go.Scatter(
			x=df[time_col], y=df["max_value"],
			mode="lines", name="Max",
			line=dict(width=0), showlegend=False,
		))
		fig.add_trace(go.Scatter(
			x=df[time_col], y=df["min_value"],
			mode="lines", name="Min/Max range",
			line=dict(width=0),
			fill="tonexty",
			fillcolor="rgba(37, 99, 235, 0.12)",
		))
		fig.update_layout(
			title=f"{selected["name"]} (indicator {int(indicator_id)})",
			xaxis_title="", yaxis_title=y_unit,
			**PLOTLY_LAYOUT,
		)

	st.plotly_chart(fig, use_container_width=True)

	# -- Data ------------------------------------------------------------------

	with st.expander("Aggregated data"):
		st.dataframe(df, use_container_width=True, height=400)


main()
