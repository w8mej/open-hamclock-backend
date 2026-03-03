#!/usr/bin/env python3
"""
voacap_bandconditions.py

HamClock-style band conditions generator using dvoacap-python.

Output format:
- First line: header row (9 comma-separated values)
- Second line: descriptor line (e.g. 100W,CW,TOA>3,LP,S=0)
- Then rows for UTC hours in HamClock order: 1..23,0
- Each row has 9 values: 8 bands + trailing 0.00 placeholder

Band columns:
  80m,40m,30m,20m,17m,15m,12m,10m,(extra zero column)

Notes:
- dvoacap expects utc_time as fractional day (e.g. 12:00 UTC => 0.5)
- MODE is a HamClock code. We do NOT convert MODE to another code.
- MODE may imply a required SNR threshold. That mapping is a heuristic and can be overridden.
"""

import sys
import argparse
from typing import List, Tuple

import numpy as np
from dvoacap.path_geometry import GeoPoint
from dvoacap.prediction_engine import PredictionEngine


# 8 real HamClock-ish bands; HamClock output has a 9th trailing value (often 0.00)
BANDS: List[Tuple[str, float]] = [
    ("80", 3.60),
    ("40", 7.10),
    ("30", 10.10),
    ("20", 14.10),
    ("17", 18.10),
    ("15", 21.10),
    ("12", 24.90),
    ("10", 28.20),
]

# HamClock MODE labels
MODE_LABELS = {
    3:  "WSPR",
    13: "FT8",
    17: "FT4",
    19: "CW",
    22: "RTTY",
    38: "SSB",
    49: "AM",
}

MODE_BANDWIDTH_HZ = {
    3:  6.0,    # WSPR (~6 Hz)
    13: 50.0,   # FT8 (~50 Hz)
    17: 80.0,   # FT4 (~80 Hz)
    19: 500.0,  # CW (typical filter)
    22: 500.0,  # RTTY
    38: 3000.0, # SSB
    49: 6000.0, # AM
}

# Heuristic mode->required SNR thresholds (dB), configurable/overrideable
# These are not from dvoacap docs; they are application-level assumptions.
MODE_REQUIRED_SNR_DB = {
    3:  -28.0,  # WSPR (very weak-signal digital)
    13: -10.0,
    17: -16.0,  # FT4 (roughly weak-signal digital)
    19: 10.0,   # CW
    22: 18.0,   # RTTY
    38: 24.0,   # SSB
    49: 40.0,   # AM
}

# Fitted from 88 HamClock reference files (W4→Brazil, 12 months, SSN 0-150,
# modes 13/19/38). Reduces MAE from 0.2034 -> 0.1753 (13.8% improvement).

# ── Band correction parameters ───────────────────────────────────────────────
# Formula per band: x = clip(raw * scale, 0, 1)^gamma; if x < threshold: x = 0
BAND_CORRECTION = {
    '80m': (1.8956, 0.8185, 0.0235),  # scale, gamma, threshold
    '40m': (4.9780, 0.7082, 0.2951),
    '30m': (1.6745, 0.8315, 0.2994),
    '20m': (1.3688, 0.7171, 0.2805),
    '17m': (1.3947, 1.0299, 0.0399),
    '15m': (1.3011, 0.6127, 0.0601),
    '12m': (1.0315, 0.3002, 0.1991),
    '10m': (1.1641, 0.3000, 0.0703),
}

def apply_band_correction(row):
    """Apply per-band post-processing correction to a dvoacap output row.

    Args:
        row: list of 8 floats [80m, 40m, 30m, 20m, 17m, 15m, 12m, 10m]
    Returns:
        list of 8 corrected floats
    """
    bands = ['80m', '40m', '30m', '20m', '17m', '15m', '12m', '10m']
    out = []
    for b, band in enumerate(bands):
        scale, gamma, threshold = BAND_CORRECTION[band]
        x = min(row[b] * scale, 1.0)
        if x > 0:
            x = x ** gamma
        if x < threshold:
            x = 0.0
        out.append(round(x, 3))
    return out

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def parse_args():
    p = argparse.ArgumentParser()

    # HamClock-like query params
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=int, required=True)
    p.add_argument("--utc", type=int, required=True, help="Header UTC hour (0..23)")

    p.add_argument("--txlat", type=float, required=True)
    p.add_argument("--txlng", type=float, required=True)
    p.add_argument("--rxlat", type=float, required=True)
    p.add_argument("--rxlng", type=float, required=True)

    p.add_argument("--path", type=int, default=0, help="0=SP, 1=LP")
    p.add_argument("--pow", type=float, default=100.0, help="Transmitter power in watts")
    p.add_argument("--mode", type=int, default=19, help="HamClock mode code (3,17,19,22,38,49)")
    p.add_argument("--toa", type=float, default=3.0, help="Minimum TOA in degrees")
    p.add_argument("--ssn", type=float, default=0.0, help="Sunspot number")
    p.add_argument("--bandwidth-hz", type=float, default=3000.0,
               help="Signal bandwidth in Hz (default 3000 for SSB reference)")

    # Matching/tuning knobs
    p.add_argument("--noise-at-3mhz", type=float, default=153.0,
                   help="Man-made noise at 3 MHz")
    p.add_argument("--required-snr", type=float, default=None,
                   help="Required SNR threshold in dB. If omitted, derive from MODE heuristic.")
    p.add_argument("--required-reliability", type=float, default=0.0,
                   help="Engine required reliability target (0..1)")

    # Controls for mode->required_snr heuristic
    p.add_argument("--disable-mode-snr-map", action="store_true",
                   help="Do not derive required_snr from MODE when --required-snr is omitted")
    p.add_argument("--unknown-mode-required-snr", type=float, default=10.0,
                   help="Fallback required_snr dB if MODE is unknown and no explicit --required-snr provided")

    # Debug (stderr only)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--debug-hour", type=int, default=None, help="Print per-band debug for one UTC hour (0..23)")
    p.add_argument("--debug-all-hours", action="store_true")
    p.add_argument("--debug-raw", action="store_true",
                   help="Print extra raw details (attributes present on params/pred)")
    p.add_argument("--quiet-set-debug", action="store_true",
                   help="Suppress repeated 'set params' debug lines")

    return p.parse_args()


def resolve_bandwidth_hz(args) -> float:
    if args.bandwidth_hz != 3000.0:  # explicit override
        return float(args.bandwidth_hz)
    if args.mode in MODE_BANDWIDTH_HZ:
        return float(MODE_BANDWIDTH_HZ[args.mode])
    return 3000.0

def mode_label(mode: int) -> str:
    return MODE_LABELS.get(mode, f"M{mode}")


def path_label(path: int) -> str:
    return "LP" if int(path) == 1 else "SP"


def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def fmt_vals(vals: List[float]) -> str:
    return ",".join(f"{v:.2f}" for v in vals)


def get_pred_field(pred, *names, default=None):
    """
    Try multiple attribute names / nested forms safely.
    """
    for name in names:
        try:
            if "." in name:
                obj = pred
                for part in name.split("."):
                    obj = getattr(obj, part)
                return obj
            return getattr(pred, name)
        except Exception:
            pass
    return default


def set_if_attr(obj, attr, value, debug=False, quiet=False):
    """
    Set only if attribute exists; return True if set.
    """
    if hasattr(obj, attr):
        try:
            setattr(obj, attr, value)
            if debug and not quiet:
                eprint(f"set {obj.__class__.__name__}.{attr} = {value!r}")
            return True
        except Exception as e:
            if debug:
                eprint(f"failed setting {obj.__class__.__name__}.{attr}: {e!r}")
    return False


def resolve_required_snr(args) -> float:
    """
    Determine required_snr:
    1) explicit --required-snr wins
    2) otherwise optionally derive from MODE heuristic
    3) fallback default
    """
    if args.required_snr is not None:
        return float(args.required_snr)

    if not args.disable_mode_snr_map:
        if args.mode in MODE_REQUIRED_SNR_DB:
            return float(MODE_REQUIRED_SNR_DB[args.mode])

    return float(args.unknown_mode_required_snr)


def build_engine(tx: GeoPoint, args, effective_required_snr: float, effective_bandwidth_hz: float) -> PredictionEngine:
    engine = PredictionEngine()
    p = engine.params

    # Core params
    p.ssn = float(args.ssn)
    p.month = int(args.month)
    p.tx_location = tx
    p.tx_power = float(args.pow)

    # Optional params (only if present in this dvoacap version)
    set_if_attr(p, "bandwidth_hz", float(effective_bandwidth_hz),
            debug=args.debug, quiet=args.quiet_set_debug)
    set_if_attr(p, "man_made_noise_at_3mhz", float(args.noise_at_3mhz),
                debug=args.debug, quiet=args.quiet_set_debug)
    set_if_attr(p, "required_snr", float(effective_required_snr),
                debug=args.debug, quiet=args.quiet_set_debug)
    set_if_attr(p, "required_reliability", float(args.required_reliability),
                debug=args.debug, quiet=args.quiet_set_debug)
    set_if_attr(p, "min_angle", float(np.deg2rad(args.toa)),
                debug=args.debug, quiet=args.quiet_set_debug)

    # dvoacap-python long/short path switch (if supported by this version)
    set_if_attr(p, "long_path", bool(int(args.path) == 1),
                debug=args.debug, quiet=args.quiet_set_debug)

    if args.debug and args.debug_raw:
        try:
            attrs = [a for a in dir(p) if not a.startswith("_")]
            eprint(f"params attrs: {', '.join(attrs)}")
        except Exception:
            pass

    return engine


def predict_row_for_hour(tx: GeoPoint, rx: GeoPoint, hour: int, args, effective_required_snr: float, effective_bandwidth_hz: float) -> List[float]:
    frequencies = [f for _, f in BANDS]

    engine = build_engine(tx, args, effective_required_snr, effective_bandwidth_hz)

    utc_time = (hour % 24) / 24.0  # dvoacap docs use fractional day (e.g. 12:00 -> 0.5)

    engine.predict(
        rx_location=rx,
        utc_time=utc_time,
        frequencies=frequencies,
    )

    preds = list(getattr(engine, "predictions", []))
    row: List[float] = []

    dbg_this_hour = args.debug and (args.debug_all_hours or args.debug_hour == hour)
    if dbg_this_hour:
        lp_flag = getattr(engine.params, "long_path", None)
        eprint(f"UTC {hour:02d} utc_time={utc_time:.6f} predictions={len(preds)} long_path={lp_flag}")

    for (band_name, freq), pred in zip(BANDS, preds):
        rel = safe_float(get_pred_field(pred, "signal.reliability", "signal_reliability"), 0.0)
        snr = safe_float(get_pred_field(pred, "signal.snr_db"), 0.0)
        svc = safe_float(get_pred_field(pred, "service_prob"), 0.0)
        txe = safe_float(get_pred_field(pred, "tx_elevation"), 0.0)

        row.append(rel)

        if dbg_this_hour:
            mode_name = None
            try:
                if hasattr(pred, "get_mode_name") and hasattr(engine, "path") and hasattr(engine.path, "dist"):
                    mode_name = pred.get_mode_name(engine.path.dist)
            except Exception:
                mode_name = None

            eprint(
                f"UTC {hour:02d} band={band_name:>2} freq={freq:>5.2f} "
                f"rel={rel:.8f} snr={snr:.2f} svc={svc:.8f} txe={txe}"
                + (f" mode={mode_name}" if mode_name else "")
            )

    # Pad if needed
    while len(row) < 8:
        row.append(0.0)

    row = apply_band_correction(row)

    # HamClock expects 9 columns; append placeholder
    row.append(0.0)
    return row


def main():
    args = parse_args()

    if not (1 <= args.month <= 12):
        print("Invalid month", file=sys.stderr)
        sys.exit(2)

    if not (0 <= args.utc <= 23):
        print("Invalid utc", file=sys.stderr)
        sys.exit(2)

    tx = GeoPoint.from_degrees(args.txlat, args.txlng)
    rx = GeoPoint.from_degrees(args.rxlat, args.rxlng)

    effective_required_snr = resolve_required_snr(args)
    effective_bandwidth_hz = resolve_bandwidth_hz(args)

    if args.debug:
        eprint("=== voacap_bandconditions debug ===")
        eprint(f"TX=({args.txlat},{args.txlng}) RX=({args.rxlat},{args.rxlng}) path={path_label(args.path)}")
        eprint(f"year={args.year} month={args.month} utc={args.utc} ssn={args.ssn}")
        eprint(f"pow={args.pow}W mode={args.mode} ({mode_label(args.mode)}) toa={args.toa} deg")
        eprint(f"noise@3MHz={args.noise_at_3mhz} required_snr={effective_required_snr} required_rel={args.required_reliability}")
        if args.required_snr is None:
            if (not args.disable_mode_snr_map) and (args.mode in MODE_REQUIRED_SNR_DB):
                eprint(f"required_snr source=mode-map[{args.mode}]")
            elif args.disable_mode_snr_map:
                eprint("required_snr source=fallback (mode-map disabled)")
            else:
                eprint("required_snr source=fallback (unknown mode)")
        else:
            eprint("required_snr source=explicit --required-snr")
        eprint(f"noise@3MHz={args.noise_at_3mhz} required_snr={effective_required_snr} bandwidth_hz={effective_bandwidth_hz} required_rel={args.required_reliability}")
        eprint("bands=" + ", ".join(f"{b}:{f:.2f}" for b, f in BANDS))
        eprint("NOTE: values printed in table are rounded to 2 decimals")

    rows = {}
    for hour in range(24):
        try:
            rows[hour] = predict_row_for_hour(tx, rx, hour, args, effective_required_snr, effective_bandwidth_hz)
        except Exception as e:
            if args.debug:
                eprint(f"UTC {hour:02d} predict exception: {e!r}")
            rows[hour] = [0.0] * 9

    # Header row = requested UTC hour
    print(fmt_vals(rows[args.utc]))

    toa_disp = int(args.toa) if float(args.toa).is_integer() else args.toa
    print(f"{int(args.pow)}W,{mode_label(args.mode)},TOA>{toa_disp},{path_label(args.path)},S={int(args.ssn)}")

    # HamClock row order: 1..23,0
    for hour in list(range(1, 24)) + [0]:
        print(f"{hour} {fmt_vals(rows[hour])}")


if __name__ == "__main__":
    main()

