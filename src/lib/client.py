from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from datons import Client


load_dotenv()


def get_api_key() -> str | None:
	return os.getenv("DATONS_API_KEY") or os.getenv("ESIOS_API_KEY")


@st.cache_resource
def get_client(token: str) -> Client:
	return Client(token=token)


def normalize_query_result(data: object) -> pd.DataFrame:
	if hasattr(data, "to_pandas"):
		return data.to_pandas()
	if isinstance(data, pd.DataFrame):
		return data.copy()
	return pd.DataFrame(data)


@st.cache_data(ttl=600)
def run_query(_token: str, sql: str) -> pd.DataFrame:
	client = get_client(_token)
	data = client.esios.query(sql, backend="pandas")
	return normalize_query_result(data)


@st.cache_data(ttl=3600)
def load_units(_token: str) -> list[str]:
	"""Load all available unit codes from the API dimensions endpoint."""
	client = get_client(_token)
	result = client.esios.dimensions("unit", detail="summary")
	return result.values


@st.cache_data(ttl=3600)
def load_units_enriched(_token: str) -> list[dict]:
	"""Load units with name, technology, and company via fields parameter."""
	import httpx

	client = get_client(_token)
	base = client.base_url.rstrip("/")
	resp = httpx.get(
		f"{base}/esios-data/dimensions",
		params={"dim": "unit", "fields": "unit,unit_name,technology,company_name"},
		headers={"X-API-Key": _token},
	)
	resp.raise_for_status()
	return resp.json().get("items", [])


@st.cache_data(ttl=3600)
def load_companies(_token: str) -> list[str]:
	"""Extract distinct company names from enriched units data."""
	units = load_units_enriched(_token)
	companies = sorted({u["company_name"] for u in units if u.get("company_name")})
	return companies


@st.cache_data(ttl=3600)
def load_indicators(_token: str) -> list[dict]:
	"""Load all available indicators (id + name) from esios_indicators."""
	sql = "SELECT DISTINCT indicator_id, indicator_name FROM esios_indicators ORDER BY indicator_id"
	df = run_query(_token, sql)
	return [{"id": int(row["indicator_id"]), "name": str(row["indicator_name"])} for _, row in df.iterrows()]


def search_units(_token: str, query: str) -> list[dict]:
	"""Search units by name/company/technology via fields parameter."""
	import httpx

	client = get_client(_token)
	base = client.base_url.rstrip("/")
	resp = httpx.get(
		f"{base}/esios-data/dimensions",
		params={"dim": "unit", "fields": "unit,unit_name,technology,company_name", "q": query},
		headers={"X-API-Key": _token},
	)
	resp.raise_for_status()
	return resp.json().get("items", [])
