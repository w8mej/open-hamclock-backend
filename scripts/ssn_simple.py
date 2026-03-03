#!/usr/bin/env python3
"""
Build ssn-31.txt (YYYY MM DD SSN) using:
- NOAA SWPC daily-solar-indices.txt for historical daily SSN (SESC)
- SWPC solar-cycle JSON (swpc_observed_ssn.json) for *today's* SSN (matches CSI)
- SILSO EISN_current.txt only as a fallback for *today* if SWPC JSON is missing

Rules / precedence for today's (UTC) value:
  1) SWPC JSON swpc_ssn (preferred; matches CSI)
  2) SILSO EISN (fallback)
  3) Otherwise, keep whatever NOAA/existing has (usually yesterday)

Always writes exactly N_DAYS lines (default 31), ascending by date, with zero-padded MM/DD.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

NOAA_URL = "https://services.swpc.noaa.gov/text/daily-solar-indices.txt"
SWPC_JSON_URL = "https://services.swpc.noaa.gov/json/solar-cycle/swpc_observed_ssn.json"
SILSO_URL = "https://sidc.be/SILSO/DATA/EISN/EISN_current.txt"

OUT = Path("/opt/hamclock-backend/htdocs/ham/HamClock/ssn/ssn-31.txt")
N_DAYS = 31


def read_existing(out_path: Path) -> pd.DataFrame:
    if not out_path.exists():
        return pd.DataFrame(columns=["date", "ssn", "src"])

    df = pd.read_csv(
        out_path,
        sep=r"\s+",
        header=None,
        names=["year", "month", "day", "ssn"],
        dtype={"year": "int64", "month": "int64", "day": "int64", "ssn": "Int64"},
        engine="python",
    )

    df["date"] = pd.to_datetime(
        df[["year", "month", "day"]].astype(str).agg("-".join, axis=1),
        errors="coerce",
        utc=True,
    ).dt.date

    df = df.dropna(subset=["date", "ssn"])[["date", "ssn"]]
    df["src"] = "existing"
    return df


def read_noaa_swpc(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    lines = r.text.splitlines()

    rows = []
    for line in lines:
        s = line.strip()
        if not s:
            continue

        # Data rows begin with: YYYY MM DD ...
        if len(s) >= 10 and s[0:4].isdigit() and s[4].isspace():
            parts = s.split()
            # SWPC format: YYYY MM DD 10.7cm_flux Sunspot_Number ...
            if len(parts) >= 5 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
                y, m, d = parts[0], parts[1], parts[2]
                ssn = parts[4]
                if ssn.lstrip("-").isdigit():
                    rows.append((y, m, d, ssn))

    if not rows:
        raise RuntimeError("No NOAA SWPC data rows parsed (format may have changed)")

    df = pd.DataFrame(rows, columns=["year", "month", "day", "ssn"])
    df[["year", "month", "day", "ssn"]] = df[["year", "month", "day", "ssn"]].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["year", "month", "day", "ssn"])

    df["date"] = pd.to_datetime(
        df[["year", "month", "day"]].astype(int).astype(str).agg("-".join, axis=1),
        errors="coerce",
        utc=True,
    ).dt.date

    df = df.dropna(subset=["date"])[["date", "ssn"]]
    df["src"] = "noaa"
    return df


def get_swpc_json_today(url: str, today_utc) -> Optional[int]:
    """
    SWPC JSON looks like:
      { "Obsdate": "YYYY-MM-DDT00:00:00", "swpc_ssn": 69 }
    Return today's swpc_ssn or None if not present.
    """
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return None

    for obj in reversed(data):
       if not isinstance(obj, dict):
          continue

       v = obj.get("swpc_ssn")
       if v is None:
          continue

       try:
          return int(v)
       except Exception:
          return None

    return None


def get_silso_today(url: str, today_utc) -> Optional[int]:
    # Fixed-width positions per SILSO spec (0-based, half-open):
    # Year [0,4), Month [5,8), Day [8,10), Decimal [11,19), EISN [20,23), ...
    colspecs = [(0, 4), (5, 8), (8, 10), (11, 19), (20, 23), (24, 29), (30, 33), (34, 37)]
    names = ["year", "month", "day", "dec_date", "eisn", "sd", "ncalc", "navail"]

    r = requests.get(url, timeout=20)
    r.raise_for_status()

    df = pd.read_fwf(
        pd.io.common.StringIO(r.text),
        colspecs=colspecs,
        header=None,
        names=names,
        dtype=str,
    )

    df = df[df["year"].str.fullmatch(r"\d{4}", na=False)].copy()
    for c in ["year", "month", "day", "eisn"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["year", "month", "day", "eisn"])

    df["date"] = pd.to_datetime(
        df[["year", "month", "day"]].astype(int).astype(str).agg("-".join, axis=1),
        errors="coerce",
        utc=True,
    ).dt.date
    df = df.dropna(subset=["date"])

    row = df[df["date"] == today_utc]
    if row.empty:
        return None

    try:
        return int(row.iloc[-1]["eisn"])
    except Exception:
        return None


def main() -> int:
    today_utc = datetime.now(timezone.utc).date()

    try:
        existing = read_existing(OUT)
        noaa = read_noaa_swpc(NOAA_URL)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Merge existing + NOAA (NOAA overrides existing on same date)
    combined = (
        pd.concat([existing, noaa], ignore_index=True)
        .dropna(subset=["date", "ssn"])
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
    )

    # Today's override: SWPC JSON first (matches CSI), SILSO only if JSON missing.
    today_ssn = None
    today_src = None

    try:
        v = get_swpc_json_today(SWPC_JSON_URL, today_utc)
        if v is not None:
            today_ssn = v
            today_src = "swpc_json"
    except Exception:
        pass

    if today_ssn is None:
        try:
            v = get_silso_today(SILSO_URL, today_utc)
            if v is not None:
                today_ssn = v
                today_src = "silso"
        except Exception:
            pass

    if today_ssn is not None:

        combined = combined[combined["date"] != today_utc]
        combined = pd.concat(
            [combined, pd.DataFrame([{"date": today_utc, "ssn": int(today_ssn), "src": today_src}])],
            ignore_index=True,
        )

    combined = combined.sort_values("date").drop_duplicates(subset=["date"], keep="last")

    # Enforce exactly N_DAYS (must be able to do this from existing cache + NOAA window)
    if len(combined) < N_DAYS:
        print(
            f"ERROR: only {len(combined)} unique days available; need {N_DAYS}. "
            f"Seed {OUT} once or keep it persistent so it accumulates history.",
            file=sys.stderr,
        )
        return 2

    combined = combined.tail(N_DAYS)

    # Write CSI-style formatting with zero-padded month/day
    dt = pd.to_datetime(combined["date"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for y, m, d, ssn in zip(dt.dt.year, dt.dt.month, dt.dt.day, combined["ssn"].astype(int).to_numpy()):
            f.write(f"{int(y):04d} {int(m):02d} {int(d):02d} {int(ssn)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

