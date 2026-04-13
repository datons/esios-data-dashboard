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
daily_detail = st.Page("pages/04_daily_detail.py", title="Daily detail", icon=":material/schedule:")
constraints = st.Page("pages/03_technical_constraints.py", title="Technical constraints", icon=":material/warning:")
report = st.Page("pages/05_program_report.py", title="Program report", icon=":material/assessment:")

pg = st.navigation({
	"ESIOS Data": [overview, indicators, operational, daily_detail, constraints, report],
})

pg.run()
