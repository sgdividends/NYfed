#!/usr/bin/env python3
"""
nyfed_fetch.py
Pulls NY Fed Reference Rates (SOFR/EFFR/OBFR/TGCR/BGCR) and Primary Dealer
Statistics (the full survey dataset) from the public Markets Data API.
No API key required. Caches each to CSV with dedupe.
"""

import sys
import datetime as dt
from pathlib import Path
from io import StringIO

import requests
import pandas as pd

CACHE_DIR = Path("data/nyfed")
BASE = "https://markets.newyorkfed.org/api"

HEADERS = {"User-Agent": "research-script/1.0 (personal, non-commercial use)"}

# Reference Rates: (rate_type, category) -> filename
RATE_SERIES = {
    "sofr":   ("secured", "sofr_daily.csv"),
    "tgcr":   ("secured", "tgcr_daily.csv"),
    "bgcr":   ("secured", "bgcr_daily.csv"),
    "effr":   ("unsecured", "effr_daily.csv"),
    "obfr":   ("unsecured", "obfr_daily.csv"),
}

PD_ALL_TIMESERIES_URL = f"{BASE}/pd/get/all/timeseries.csv"
PD_LIST_TIMESERIES_URL = f"{BASE}/pd/list/timeseries.csv"


def fetch_csv(url: str, params: dict = None) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, params=params, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))


def update_cache(df_new: pd.DataFrame, path: Path, dedupe_cols: list) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        df_old = pd.read_csv(path)
        merged = pd.concat([df_old, df_new]).drop_duplicates(
            subset=dedupe_cols, keep="last"
        )
    else:
        merged = df_new
    merged.to_csv(path, index=False)
    return merged


def fetch_reference_rates():
    for rate_type, (category, filename) in RATE_SERIES.items():
        url = f"{BASE}/rates/{category}/{rate_type}/last/250.json"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("refRates", [])
        if not data:
            print(f"  {rate_type.upper()}: no data returned", file=sys.stderr)
            continue
        df = pd.DataFrame(data)
        path = CACHE_DIR / filename
        dedupe_col = "effectiveDate" if "effectiveDate" in df.columns else df.columns[0]
        merged = update_cache(df, path, [dedupe_col])
        print(f"  {rate_type.upper()}: {len(merged)} rows cached, latest = "
              f"{merged.iloc[-1].to_dict()}")


def fetch_primary_dealer_stats():
    """
    Pulls the ENTIRE primary dealer survey dataset rather than guessing
    specific timeseries IDs. This is a large, complete dump — filter it
    down to specific series (e.g. net positions, repo financing) once
    you've inspected data/nyfed/pd_timeseries_labels.csv to find the IDs
    you actually want.
    """
    labels_df = fetch_csv(PD_LIST_TIMESERIES_URL)
    labels_path = CACHE_DIR / "pd_timeseries_labels.csv"
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_df.to_csv(labels_path, index=False)  # static reference, overwrite is fine
    print(f"  Primary Dealer series labels: {len(labels_df)} series documented")

    df = fetch_csv(PD_ALL_TIMESERIES_URL)
    path = CACHE_DIR / "pd_all_timeseries.csv"
    dedupe_cols = [c for c in ["Time Series", "As Of Date"] if c in df.columns]
    if not dedupe_cols:
        dedupe_cols = list(df.columns[:2])
    merged = update_cache(df, path, dedupe_cols)
    print(f"  Primary Dealer Statistics: {len(merged)} rows cached")


def main():
    print(f"[{dt.datetime.now()}] Fetching NY Fed Markets Data...")
    print("Reference Rates:")
    fetch_reference_rates()
    print("Primary Dealer Statistics:")
    fetch_primary_dealer_stats()
    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
