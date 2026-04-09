from __future__ import annotations

import streamlit as st


st.set_page_config(
	page_title="Datons ESIOS Dashboard",
	page_icon="📊",
	layout="wide",
)

overview = st.Page("pages/00_overview.py", title="Market overview", icon=":material/trending_up:")
indicators = st.Page("pages/01_indicators.py", title="Indicators", icon=":material/show_chart:")
operational = st.Page("pages/02_operational_data.py", title="Operational data", icon=":material/factory:")

pg = st.navigation({
	"ESIOS Data": [overview, indicators, operational],
})

st.sidebar.divider()
st.sidebar.info(
	"**API limits:** raw queries → 50 rows, "
	"aggregated queries → 10,000 rows.",
	icon="ℹ️",
)

pg.run()
