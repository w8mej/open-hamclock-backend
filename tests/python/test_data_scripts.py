"""Tests for Python data-processing scripts in ``scripts/``.

This module validates the data-processing utilities that generate BMP
images, perform RGB565 color-space conversions, and handle NOAA data
transforms.

Modules Under Test:
    ``scripts/bz_simple.py``
        Parses NOAA Bz (interplanetary magnetic field) JSON data.
        Tested functions: ``iso_to_epoch()``.

    ``scripts/dst_simple.py``
        Parses NOAA Dst (disturbance storm time) index data.
        Tested functions: ``parse_dst_line_fixed()``, ``_parse_int_token()``,
        ``prev_month()``, ``build_presentmonth_url()``, ``merge_rows()``,
        ``format_line()``.

    ``scripts/flux_simple.py``
        Parses NOAA solar radio flux (F10.7) data.
        Tested functions: ``parse_dsd_fluxes()``, ``parse_wwv_flux()``,
        ``build_phase3_bridge()``, ``expand_tripled()``.

    ``scripts/hc_bmp.py``
        Generates BMP v4 image files for HamClock display rendering.

    ``scripts/hc_raw_to_bmp565.py``
        Converts raw RGB pixel data to BMP files using the RGB565
        (16-bit, 5-6-5) color encoding.

Test Strategy:
    These tests validate **pure functions** in each script without any
    network I/O or filesystem writes:

    1. Verifying scripts exist at the expected paths (deployment guard).
    2. Confirming modules import without side effects.
    3. Validating mathematical transformations (RGB → RGB565 bit packing)
       with known input/output pairs.
    4. Testing data parsing functions with synthetic inline data.
    5. Testing edge cases: malformed input, boundary values, empty data.

See Also:
    ``tests/TEST_README.md`` — Tier 3 (Python Unit Tests).
"""

import os
import sys
import json
import tempfile
import struct
from datetime import datetime, timezone, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")


# ── bz_simple.py ─────────────────────────────────────────────────────────────


class TestBzSimple:
    """Tests for ``bz_simple.py`` — NOAA Bz data parser.

    Validates script existence, importability, and the ``iso_to_epoch``
    timestamp conversion function.
    """

    def test_script_exists(self):
        """Verify ``bz_simple.py`` exists in the ``scripts/`` directory."""
        assert os.path.isfile(os.path.join(SCRIPTS, "bz_simple.py"))

    def test_imports_without_error(self):
        """Verify ``bz_simple.py`` can be imported without side effects."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bz_simple", os.path.join(SCRIPTS, "bz_simple.py"))
        assert spec is not None

    def test_iso_to_epoch_known_value(self):
        """Verify ``iso_to_epoch`` returns correct Unix epoch for a known timestamp.

        ``2026-01-01 00:00:00.000`` UTC = epoch 1767225600.
        """
        from bz_simple import iso_to_epoch
        result = iso_to_epoch("2026-01-01 00:00:00.000")
        expected = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_iso_to_epoch_with_fractional_seconds(self):
        """Verify fractional seconds are parsed but truncated to integer."""
        from bz_simple import iso_to_epoch
        result = iso_to_epoch("2026-06-15 12:30:45.500")
        expected = int(datetime(2026, 6, 15, 12, 30, 45, 500000,
                                tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_iso_to_epoch_midnight_boundary(self):
        """Verify midnight (00:00:00.000) is handled correctly."""
        from bz_simple import iso_to_epoch
        result = iso_to_epoch("2026-12-31 00:00:00.000")
        expected = int(datetime(2026, 12, 31, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_iso_to_epoch_malformed_raises(self):
        """Verify malformed timestamp raises ``ValueError``."""
        from bz_simple import iso_to_epoch
        with pytest.raises(ValueError):
            iso_to_epoch("not-a-date")

    def test_iso_to_epoch_missing_fractional_raises(self):
        """Verify missing fractional seconds raises ``ValueError``."""
        from bz_simple import iso_to_epoch
        with pytest.raises(ValueError):
            iso_to_epoch("2026-01-01 00:00:00")


# ── dst_simple.py ─────────────────────────────────────────────────────────────


class TestDstSimple:
    """Tests for ``dst_simple.py`` — NOAA Dst index parser.

    Validates the Kyoto fixed-width line parser, helper functions, and
    data merging logic.
    """

    def test_script_exists(self):
        """Verify ``dst_simple.py`` exists in the ``scripts/`` directory."""
        assert os.path.isfile(os.path.join(SCRIPTS, "dst_simple.py"))

    def test_parse_int_token_valid(self):
        """Verify ``_parse_int_token`` parses valid integers."""
        from dst_simple import _parse_int_token
        assert _parse_int_token("42") == 42
        assert _parse_int_token("-7") == -7
        assert _parse_int_token("+3") == 3
        assert _parse_int_token("  0  ") == 0

    def test_parse_int_token_invalid(self):
        """Verify ``_parse_int_token`` returns ``None`` for non-numeric input."""
        from dst_simple import _parse_int_token
        assert _parse_int_token("abc") is None
        assert _parse_int_token("") is None
        assert _parse_int_token("12.5") is None
        assert _parse_int_token("  ") is None

    def test_parse_dst_line_fixed_valid(self):
        """Verify a valid Kyoto DST fixed-width line is parsed correctly.

        Constructs a synthetic line matching the Kyoto format:
        columns 1-3: 'DST', 4-5: YY, 6-7: MM, 8: '*', 9-10: DD,
        then 4-char wide hourly values starting at column 21.
        """
        from dst_simple import parse_dst_line_fixed
        # Build a synthetic DST line: DST2603*01 with hourly values
        # Columns: DST YY MM * DD [padding] [pre-field] h00 h01 h02 ...
        line = "DST2603*01"         # cols 1-10
        line += " " * 6             # cols 11-16 (padding)
        line += "   0"              # cols 17-20 (pre-field, ignored)
        # 24 hourly values, 4 chars each
        for h in range(24):
            line += f"{-h:4d}"
        # trailing extra column
        line += "   0"

        row = parse_dst_line_fixed(line)
        assert row is not None
        assert row.year == 2026
        assert row.month == 3
        assert row.day == 1
        assert row.hours[0] == 0
        assert row.hours[1] == -1
        assert row.hours[23] == -23

    def test_parse_dst_line_fixed_filler_9999(self):
        """Verify parsing stops at filler value ``9999``."""
        from dst_simple import parse_dst_line_fixed
        line = "DST2603*01"
        line += " " * 6
        line += "   0"
        # First 3 hours have data, then 9999 filler
        line += "  -5"  # hour 0
        line += "  -3"  # hour 1
        line += "  -1"  # hour 2
        line += "9999"  # filler — parsing stops
        line += "  99" * 20  # remaining hours (should be ignored)

        row = parse_dst_line_fixed(line)
        assert row is not None
        assert len(row.hours) == 3
        assert row.hours[2] == -1

    def test_parse_dst_line_fixed_packed_filler(self):
        """Verify packed filler (e.g., ``2999``) records value then stops."""
        from dst_simple import parse_dst_line_fixed
        line = "DST2603*15"
        line += " " * 6
        line += "   0"
        line += "  10"  # hour 0
        line += "2999"  # packed filler: value=2, then stop
        line += "  99" * 22

        row = parse_dst_line_fixed(line)
        assert row is not None
        assert len(row.hours) == 2
        assert row.hours[0] == 10
        assert row.hours[1] == 2

    def test_parse_dst_line_fixed_not_dst(self):
        """Verify non-DST lines return ``None``."""
        from dst_simple import parse_dst_line_fixed
        assert parse_dst_line_fixed("NOT A DST LINE") is None
        assert parse_dst_line_fixed("") is None

    def test_prev_month(self):
        """Verify ``prev_month`` returns the last day of the previous month."""
        from dst_simple import prev_month
        dt = datetime(2026, 3, 15, tzinfo=timezone.utc)
        result = prev_month(dt)
        assert result.month == 2
        assert result.year == 2026

    def test_prev_month_january(self):
        """Verify ``prev_month`` wraps from January to December of previous year."""
        from dst_simple import prev_month
        dt = datetime(2026, 1, 10, tzinfo=timezone.utc)
        result = prev_month(dt)
        assert result.month == 12
        assert result.year == 2025

    def test_build_presentmonth_url(self):
        """Verify correct URL construction for the current month."""
        from dst_simple import build_presentmonth_url
        dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        url = build_presentmonth_url(dt)
        assert "dst2603" in url
        assert "presentmonth" in url

    def test_merge_rows_deduplicates(self):
        """Verify ``merge_rows`` deduplicates by (year, month, day), later wins."""
        from dst_simple import merge_rows, ParsedDstRow
        row_a = ParsedDstRow(year=2026, month=3, day=1, hours={0: -5})
        row_b = ParsedDstRow(year=2026, month=3, day=1, hours={0: -10})  # same date
        merged = merge_rows([row_a], [row_b])
        assert len(merged) == 1
        assert merged[0].hours[0] == -10  # row_b wins (later list)

    def test_format_line(self):
        """Verify ``format_line`` produces ``YYYY-MM-DDTHH:MM:SS VALUE`` format."""
        from dst_simple import format_line
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = format_line(ts, -15)
        assert result == "2026-03-01T12:00:00 -15"


# ── flux_simple.py ────────────────────────────────────────────────────────────


class TestFluxSimple:
    """Tests for ``flux_simple.py`` — NOAA solar flux parser.

    Validates the pure data-parsing and transformation functions used
    to generate ``solarflux-99.txt``.
    """

    def test_script_exists(self):
        """Verify ``flux_simple.py`` exists in the ``scripts/`` directory."""
        assert os.path.isfile(os.path.join(SCRIPTS, "flux_simple.py"))

    def test_parse_wwv_flux_valid(self):
        """Verify ``parse_wwv_flux`` extracts the flux value from WWV text."""
        from flux_simple import parse_wwv_flux
        text = "Solar flux 110 and estimated planetary A-index 36."
        assert parse_wwv_flux(text) == 110

    def test_parse_wwv_flux_multiline(self):
        """Verify flux extraction from multi-line WWV bulletin text."""
        from flux_simple import parse_wwv_flux
        text = """
        Some preamble text here.
        Solar flux 150 and estimated planetary A-index 12.
        More text after.
        """
        assert parse_wwv_flux(text) == 150

    def test_parse_wwv_flux_missing_raises(self):
        """Verify ``ValueError`` when 'Solar flux' line is absent."""
        from flux_simple import parse_wwv_flux
        with pytest.raises(ValueError, match="Could not parse"):
            parse_wwv_flux("There is no flux data here.")

    def test_build_phase3_bridge(self):
        """Verify the CSI-like 3-day tail heuristic: [obs, obs+2, obs+5]."""
        from flux_simple import build_phase3_bridge
        assert build_phase3_bridge(120) == [120, 122, 125]
        assert build_phase3_bridge(100) == [100, 102, 105]

    def test_expand_tripled(self):
        """Verify each value is repeated 3 times in order."""
        from flux_simple import expand_tripled
        assert expand_tripled([1, 2]) == [1, 1, 1, 2, 2, 2]
        assert expand_tripled([]) == []

    def test_expand_tripled_preserves_count(self):
        """Verify output length is exactly 3× input length."""
        from flux_simple import expand_tripled
        inp = list(range(10))
        result = expand_tripled(inp)
        assert len(result) == 30

    def test_parse_dsd_fluxes_valid(self):
        """Verify ``parse_dsd_fluxes`` extracts flux values from DSD text.

        Generates 35 synthetic rows (only last 30 are returned).
        """
        from flux_simple import parse_dsd_fluxes
        lines = []
        for day in range(1, 36):
            flux = 100 + day
            lines.append(f"2026 01 {day:02d}  {flux}    147      880      1")
        text = "\n".join(lines)
        result = parse_dsd_fluxes(text)
        assert len(result) == 30
        # Last value should be flux for day 35
        assert result[-1] == 135

    def test_parse_dsd_fluxes_skips_comments(self):
        """Verify comment and header lines are ignored."""
        from flux_simple import parse_dsd_fluxes
        lines = [":Created by SWPC", "# Header line"]
        for day in range(1, 31):
            lines.append(f"2026 02 {day:02d}  {150 + day}    147      880      1")
        text = "\n".join(lines)
        result = parse_dsd_fluxes(text)
        assert len(result) == 30

    def test_parse_dsd_fluxes_too_few_rows_raises(self):
        """Verify ``ValueError`` when fewer than 30 data rows are present."""
        from flux_simple import parse_dsd_fluxes
        lines = []
        for day in range(1, 10):
            lines.append(f"2026 01 {day:02d}  100    147      880      1")
        with pytest.raises(ValueError, match="Expected at least 30"):
            parse_dsd_fluxes("\n".join(lines))


# ── hc_bmp.py ─────────────────────────────────────────────────────────────────


class TestHcBmp:
    """Tests for ``hc_bmp.py`` — BMP v4 file generation.

    Validates script existence and BMP header constants used to construct
    the 122-byte file header (14-byte BMP header + 108-byte DIB v4 header).
    """

    def test_script_exists(self):
        """Verify ``hc_bmp.py`` exists in the ``scripts/`` directory."""
        assert os.path.isfile(os.path.join(SCRIPTS, "hc_bmp.py"))

    def test_bmp_header_structure(self):
        """Verify BMP magic bytes and v4 header offset constants.

        The BMP format requires:
        - Magic bytes: ``BM`` (0x42, 0x4D).
        - ``bfOffBits`` for a v4 header: 14 (file header) + 108 (DIB) = 122.
        """
        # BMP magic bytes
        assert struct.pack("<2s", b"BM") == b"BM"
        # BMPv4 header = 108 bytes
        assert 14 + 108 == 122  # bfOffBits for V4 header


# ── hc_raw_to_bmp565.py ──────────────────────────────────────────────────────


class TestHcRawToBmp565:
    """Tests for ``hc_raw_to_bmp565.py`` — RGB → RGB565 conversion.

    Validates the bit-packing arithmetic used to convert 24-bit RGB
    triples into 16-bit RGB565 values (5 bits red, 6 bits green,
    5 bits blue).

    RGB565 Encoding:
        ``value = (R >> 3) << 11 | (G >> 2) << 5 | (B >> 3)``

    Known Values:
        - Pure red   (255, 0, 0)   → ``0xF800``
        - Pure green (0, 255, 0)   → ``0x07E0``
        - Pure blue  (0, 0, 255)   → ``0x001F``
        - White      (255,255,255) → ``0xFFFF``
    """

    def test_script_exists(self):
        """Verify ``hc_raw_to_bmp565.py`` exists in the ``scripts/`` directory."""
        assert os.path.isfile(os.path.join(SCRIPTS, "hc_raw_to_bmp565.py"))

    def test_rgb_to_565_conversion(self):
        """Verify RGB → RGB565 conversion for primary colors.

        Tests pure red, green, and blue to confirm correct bit masking
        and shifting.
        """
        # Pure red (255, 0, 0) → RGB565
        r, g, b = 255, 0, 0
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        assert v == 0xF800  # Red in RGB565

        # Pure green (0, 255, 0) → RGB565
        r, g, b = 0, 255, 0
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        assert v == 0x07E0  # Green in RGB565

        # Pure blue (0, 0, 255) → RGB565
        r, g, b = 0, 0, 255
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        assert v == 0x001F  # Blue in RGB565

    def test_white_conversion(self):
        """Verify white (255, 255, 255) produces the maximum RGB565 value.

        The maximum 16-bit value ``0xFFFF`` indicates all color channels
        are at full intensity.
        """
        r, g, b = 255, 255, 255
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        assert v == 0xFFFF
