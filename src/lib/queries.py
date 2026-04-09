from __future__ import annotations

import re
from datetime import date


DEFAULT_PROGRAMS = [
	"PDBF",
	"BS",
	"RR",
	"BT",
	"PDVP",
	"PHF1",
	"PHF2",
	"PHF3",
	"PHF4",
	"PHF5",
	"PHF6",
	"PHF7",
	"RTR",
]

COMMON_INDICATORS = [
	(600, "PVPC"),
	(1001, "Day-ahead price"),
	(10033, "Demand"),
	(10034, "Wind generation"),
	(10035, "Solar PV generation"),
]


def _sql_date(value: date) -> str:
	return value.isoformat()


def _sanitize(value: str) -> str:
	"""Escape single quotes to prevent SQL injection."""
	return re.sub(r"'", "''", value)


def _resolution(start: date, end: date) -> str:
	"""Pick hourly or daily aggregation based on date range."""
	days = (end - start).days
	if days <= 30:
		return "hour"
	return "day"


def _time_expr(start: date, end: date) -> tuple[str, str]:
	"""Return (SQL expression, alias) for time bucketing."""
	res = _resolution(start, end)
	if res == "hour":
		return "toStartOfHour(datetime)", "hour"
	return "toDate(datetime)", "date"


# -- Operational data ----------------------------------------------------------


def build_daily_sql(unit: str, start: date, end: date, program: str | None) -> str:
	"""Aggregated query: energy, avg price, and revenue by time bucket and program."""
	safe_unit = _sanitize(unit)
	program_clause = f"AND program = '{_sanitize(program)}'" if program else ""
	expr, alias = _time_expr(start, end)
	return f"""
SELECT
    {expr} AS {alias},
    program,
    sum(energy) AS total_energy,
    avg(price) AS avg_price,
    sum(energy * price) AS revenue
FROM operational_data
WHERE unit = '{safe_unit}'
  AND datetime >= toDateTime('{_sql_date(start)} 00:00:00')
  AND datetime <  toDateTime('{_sql_date(end)} 23:59:59')
  {program_clause}
GROUP BY {alias}, program
ORDER BY {alias}, program
""".strip()


def build_program_summary_sql(unit: str, start: date, end: date) -> str:
	"""Summary per program: totals and record count."""
	safe_unit = _sanitize(unit)
	return f"""
SELECT
    program,
    sum(energy) AS total_energy,
    avg(price) AS avg_price,
    sum(energy * price) AS revenue,
    count() AS records
FROM operational_data
WHERE unit = '{safe_unit}'
  AND datetime >= toDateTime('{_sql_date(start)} 00:00:00')
  AND datetime <  toDateTime('{_sql_date(end)} 23:59:59')
GROUP BY program
ORDER BY revenue DESC
""".strip()


def build_capture_sql(unit: str, start: date, end: date) -> str:
	"""Captured price vs market price by time bucket."""
	safe_unit = _sanitize(unit)
	expr, alias = _time_expr(start, end)
	return f"""
SELECT
    {expr} AS {alias},
    sum(energy * price) / nullIf(sum(energy), 0) AS captured_price,
    avg(price) AS market_price
FROM operational_data
WHERE unit = '{safe_unit}'
  AND datetime >= toDateTime('{_sql_date(start)} 00:00:00')
  AND datetime <  toDateTime('{_sql_date(end)} 23:59:59')
GROUP BY {alias}
ORDER BY {alias}
""".strip()


# -- Indicators ----------------------------------------------------------------


def build_indicator_sql(
	indicator_id: int,
	start: date,
	end: date,
	geo_id: int | None = None,
) -> str:
	"""Aggregated indicator time series, grouped by geo when showing all."""
	geo_clause = f"AND geo_id = {int(geo_id)}" if geo_id is not None else ""
	expr, alias = _time_expr(start, end)
	# When a specific geo is selected, no need to group by geo
	if geo_id is not None:
		return f"""
SELECT
    {expr} AS {alias},
    avg(value) AS avg_value,
    min(value) AS min_value,
    max(value) AS max_value,
    count() AS samples
FROM esios_indicators
WHERE indicator_id = {int(indicator_id)}
  AND datetime >= toDateTime('{_sql_date(start)} 00:00:00')
  AND datetime <  toDateTime('{_sql_date(end)} 23:59:59')
  {geo_clause}
GROUP BY {alias}
ORDER BY {alias}
""".strip()
	# All geos: group by geo_name to keep them separate
	return f"""
SELECT
    {expr} AS {alias},
    geo_name,
    avg(value) AS avg_value,
    min(value) AS min_value,
    max(value) AS max_value,
    count() AS samples
FROM esios_indicators
WHERE indicator_id = {int(indicator_id)}
  AND datetime >= toDateTime('{_sql_date(start)} 00:00:00')
  AND datetime <  toDateTime('{_sql_date(end)} 23:59:59')
GROUP BY {alias}, geo_name
ORDER BY {alias}, geo_name
""".strip()


def build_indicator_meta_sql(indicator_id: int) -> str:
	"""Fetch indicator metadata: name, unit, magnitude."""
	return f"""
SELECT DISTINCT indicator_name, unit, magnitude
FROM esios_indicators
WHERE indicator_id = {int(indicator_id)}
""".strip()


def build_indicator_geo_sql(indicator_id: int) -> str:
	"""Distinct geographies for an indicator, with human-readable names."""
	return f"""
SELECT DISTINCT geo_id, geo_name
FROM esios_indicators
WHERE indicator_id = {int(indicator_id)}
ORDER BY geo_name
""".strip()
