#!/opt/hamclock-backend/venv/bin/python3
# kindex_simple.py
#
# Build HamClock geomag/kindex.txt (72 lines) from SWPC:
# - daily-geomagnetic-indices.txt -> most recent 56 valid observed Planetary Kp bins
# - 3-day-geomag-forecast.txt -> 16 forecast Kp bins using CSI-like fixed window:
#     start at day1 15-18UT, continue column-major, stop at day3 12-15UT (inclusive)
#
# Output path is atomically written:
# /opt/hamclock-backend/htdocs/ham/HamClock/geomag/kindex.txt

from __future__ import annotations

import os
import re
import sys
import tempfile

import pandas as pd
import requests

DAILY_URL = "https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt"
FCST_URL = "https://services.swpc.noaa.gov/text/3-day-geomag-forecast.txt"
OUTFILE = "/opt/hamclock-backend/htdocs/ham/HamClock/geomag/kindex.txt"

TIMEOUT = 20
HEADERS = {"User-Agent": "OHB kindex_simple.py"}

ROW_ORDER = [
    "00-03UT",
    "03-06UT",
    "06-09UT",
    "09-12UT",
    "12-15UT",
    "15-18UT",
    "18-21UT",
    "21-00UT",
]


def fetch_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def parse_daily_kp_observed(text: str) -> pd.Series:
    """
    Parse SWPC daily-geomagnetic-indices.txt and return chronological valid Planetary Kp bins.

    Assumption (matches SWPC product): the LAST 8 numeric fields on each data row are
    Planetary Kp values for 00-03, 03-06, ..., 21-24 UTC.
    """
    vals = []
    date_row_re = re.compile(r"^\s*(\d{4})\s+(\d{2})\s+(\d{2})\b")

    for line in text.splitlines():
        if not date_row_re.match(line):
            continue

        nums = re.findall(r"-?\d+(?:\.\d+)?", line)
        if len(nums) < 11:
            continue

        try:
            kp8 = [float(x) for x in nums[-8:]]
        except ValueError:
            continue

        vals.extend(kp8)

    if not vals:
        raise RuntimeError("No Kp rows parsed from daily-geomagnetic-indices.txt")

    s = pd.Series(vals, dtype="float64")
    s = s[s >= 0].reset_index(drop=True)  # drop -1 placeholders

    if len(s) < 56:
        raise RuntimeError(f"Need at least 56 valid observed Kp bins, got {len(s)}")

    return s


def parse_kp_forecast_window(
    text: str,
    start_row: str = "15-18UT",
    start_col_idx: int = 0,   # first forecast column
    end_row: str = "12-15UT",
    end_col_idx: int = 2,     # third forecast column
) -> pd.Series:
    """
    Parse the NOAA Kp forecast table from 3-day-geomag-forecast.txt and return a
    pandas Series traversed in column-major order from (start_col_idx, start_row)
    to (end_col_idx, end_row), inclusive.

    Default CSI-like window:
      day1 15-18UT -> day3 12-15UT  (16 values total)

    Returns a Series of floats (no labels needed for kindex output).
    """
    lines = text.splitlines()

    # Locate the Kp table section
    kp_header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("NOAA Kp index forecast"):
            kp_header_idx = i
            break
    if kp_header_idx is None:
        raise RuntimeError("Could not find 'NOAA Kp index forecast' section")

    # Find the date header line (e.g., "Feb 25    Feb 26    Feb 27")
    date_line_idx = None
    for i in range(kp_header_idx + 1, min(kp_header_idx + 8, len(lines))):
        if lines[i].strip():
            date_line_idx = i
            break
    if date_line_idx is None:
        raise RuntimeError("Could not find Kp forecast date header line")

    date_line = lines[date_line_idx]
    day_labels = re.findall(r"[A-Z][a-z]{2}\s+\d{1,2}", date_line)
    if len(day_labels) < 3:
        raise RuntimeError(f"Could not parse 3 forecast day labels from line: {date_line!r}")
    day_labels = day_labels[:3]

    # Parse the 8 UT rows
    row_re = re.compile(
        r"^\s*(\d{2}-\d{2}UT)\s+"
        r"(-?\d+(?:\.\d+)?)\s+"
        r"(-?\d+(?:\.\d+)?)\s+"
        r"(-?\d+(?:\.\d+)?)\s*$"
    )

    table: dict[str, list[float]] = {}
    for i in range(date_line_idx + 1, min(date_line_idx + 24, len(lines))):
        m = row_re.match(lines[i])
        if not m:
            continue
        row_label = m.group(1)
        table[row_label] = [float(m.group(2)), float(m.group(3)), float(m.group(4))]
        if len(table) == 8:
            break

    missing = [r for r in ROW_ORDER if r not in table]
    if missing:
        raise RuntimeError(f"Missing Kp forecast rows: {missing}")

    if start_row not in ROW_ORDER or end_row not in ROW_ORDER:
        raise RuntimeError(f"Invalid row labels: start={start_row}, end={end_row}")
    if not (0 <= start_col_idx <= 2 and 0 <= end_col_idx <= 2):
        raise RuntimeError("Column indexes must be in range 0..2")

    start_row_idx = ROW_ORDER.index(start_row)
    end_row_idx = ROW_ORDER.index(end_row)

    # Validate traversal ordering in column-major space
    if (end_col_idx, end_row_idx) < (start_col_idx, start_row_idx):
        raise RuntimeError("End position is before start position")

    # Build ordered matrix
    df = pd.DataFrame(
        [table[r] for r in ROW_ORDER],
        index=ROW_ORDER,
        columns=day_labels,
        dtype="float64",
    )

    out_vals: list[float] = []

    for c in range(start_col_idx, end_col_idx + 1):
        r_start = start_row_idx if c == start_col_idx else 0
        r_end = end_row_idx if c == end_col_idx else len(ROW_ORDER) - 1
        for r in range(r_start, r_end + 1):
            out_vals.append(float(df.iloc[r, c]))

    fc = pd.Series(out_vals, dtype="float64").reset_index(drop=True)

    if len(fc) != 16:
        raise RuntimeError(f"Expected 16 forecast Kp bins from fixed window, got {len(fc)}")

    return fc


def atomic_write_lines(path: str, values: pd.Series) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = "".join(f"{v:.2f}\n" for v in values.tolist())

    fd, tmp = tempfile.mkstemp(
        prefix=".kindex.",
        suffix=".tmp",
        dir=os.path.dirname(path),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    try:
        daily_text = fetch_text(DAILY_URL)
        fcst_text = fetch_text(FCST_URL)

        obs = parse_daily_kp_observed(daily_text).tail(56).reset_index(drop=True)

        # CSI-like fixed 16-bin forecast window:
        # day1 15-18UT -> day3 12-15UT (inclusive), column-major
        fc = parse_kp_forecast_window(fcst_text)

        out = pd.concat([obs, fc], ignore_index=True)

        if len(out) != 72:
            raise RuntimeError(f"Expected 72 output values, got {len(out)}")

        atomic_write_lines(OUTFILE, out)
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
