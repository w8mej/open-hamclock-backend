"""Tests for ``voacap_bandconditions.py`` — argument parsing, output format, math.

This module validates the VOACAP (Voice of America Coverage Analysis Program)
band-conditions prediction script, which is the computational core of the
``/ham/HamClock/fetchBandConditions.pl`` CGI endpoint.

Modules Under Test:
    ``scripts/voacap_bandconditions.py``
        Accepts geolocation coordinates, date/time, and solar parameters,
        then computes HF band-condition reliability predictions using the
        VOACAP propagation engine.

Test Strategy:
    * **CLI argument validation** (``TestArgumentParsing``): Exercises the
      script as a subprocess to verify that missing or out-of-range
      arguments produce non-zero exit codes.
    * **Math in isolation** (``TestBandCorrectionMath``): Imports the
      ``apply_band_correction`` function directly and verifies output
      ranges and edge-case inputs.
    * **Lookup tables** (``TestModeResolution``): Validates the
      ``mode_label`` function for known and unknown mode codes.
    * **Defensive parsing** (``TestSafeFloat``): Validates the
      ``safe_float`` helper, which converts arbitrary input to a float
      without raising exceptions.

See Also:
    ``tests/TEST_README.md`` — Tier 3 (Python Unit Tests).
"""

import os
import sys
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "voacap_bandconditions.py")


class TestArgumentParsing:
    """Test CLI argument validation for ``voacap_bandconditions.py``.

    The script requires ``--year``, ``--month``, ``--utc``, ``--txlat``,
    ``--txlng``, ``--rxlat``, ``--rxlng``, and ``--ssn``.  Missing or
    out-of-range values must result in a non-zero exit code.
    """

    def test_missing_required_args_fails(self):
        """Verify the script exits non-zero when invoked with no arguments."""
        result = subprocess.run(
            [sys.executable, SCRIPT],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_invalid_month_rejected(self):
        """Verify ``--month 13`` (out of range 1–12) causes a non-zero exit."""
        result = subprocess.run(
            [sys.executable, SCRIPT,
             "--year", "2026", "--month", "13", "--utc", "12",
             "--txlat", "28", "--txlng", "-81",
             "--rxlat", "42", "--rxlng", "-114",
             "--ssn", "50"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_invalid_utc_rejected(self):
        """Verify ``--utc 25`` (out of range 0–23) causes a non-zero exit."""
        result = subprocess.run(
            [sys.executable, SCRIPT,
             "--year", "2026", "--month", "6", "--utc", "25",
             "--txlat", "28", "--txlng", "-81",
             "--rxlat", "42", "--rxlng", "-114",
             "--ssn", "50"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0


class TestBandCorrectionMath:
    """Test the ``apply_band_correction`` function in isolation.

    ``apply_band_correction`` applies empirical correction factors to
    raw VOACAP reliability values.  All output values must remain in
    the ``[0.0, 1.0]`` range (probability).
    """

    def test_apply_band_correction_imports(self):
        """Verify ``apply_band_correction`` is importable and callable."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        assert callable(apply_band_correction)

    def test_apply_band_correction_zeros(self):
        """Verify all-zero input produces all-zero output (identity case)."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        result = apply_band_correction([0.0] * 8)
        assert all(v == 0.0 for v in result)

    def test_apply_band_correction_output_range(self):
        """Verify all output values are clamped to ``[0.0, 1.0]``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        result = apply_band_correction([0.5] * 8)
        for v in result:
            assert 0.0 <= v <= 1.0, f"Value {v} out of range"


class TestModeResolution:
    """Test the ``mode_label`` function for known and unknown mode codes.

    ``mode_label`` maps numeric VOACAP mode indices to human-readable
    labels (e.g., 19 → ``CW``, 13 → ``FT8``, 38 → ``SSB``).  Unknown
    mode codes should produce a fallback string containing the numeric
    value.
    """

    def test_mode_label_known(self):
        """Verify known mode codes return correct labels."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import mode_label
        assert mode_label(19) == "CW"
        assert mode_label(13) == "FT8"
        assert mode_label(38) == "SSB"

    def test_mode_label_unknown(self):
        """Verify unknown mode code 999 returns a fallback string like ``M999``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import mode_label
        result = mode_label(999)
        assert "999" in result  # Should return something like "M999"


class TestSafeFloat:
    """Test the ``safe_float`` defensive parsing helper.

    ``safe_float`` converts arbitrary input to a ``float``, returning
    ``0.0`` for ``None``, non-numeric strings, and other unparseable
    values.  This prevents ``ValueError`` / ``TypeError`` exceptions
    in the VOACAP computation pipeline.
    """

    def test_safe_float_none(self):
        """Verify ``None`` input returns ``0.0``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float(None) == 0.0

    def test_safe_float_normal(self):
        """Verify numeric input ``3.14`` passes through unchanged."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float(3.14) == 3.14

    def test_safe_float_string(self):
        """Verify non-numeric string ``'not a number'`` returns ``0.0``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float("not a number") == 0.0

    def test_safe_float_empty_string(self):
        """Verify empty string returns ``0.0``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float("") == 0.0

    def test_safe_float_whitespace(self):
        """Verify whitespace-only string returns ``0.0``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float("   ") == 0.0

    def test_safe_float_negative(self):
        """Verify negative float passes through unchanged."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import safe_float
        assert safe_float(-3.14) == -3.14


class TestBandCorrectionEdgeCases:
    """Test ``apply_band_correction`` with boundary and adversarial inputs.

    Verifies the correction function handles negative values, very large
    values, and confirms output clamping to ``[0.0, 1.0]`` is robust.
    """

    def test_all_ones_clamped(self):
        """Verify all-ones input produces values in ``[0.0, 1.0]``."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        result = apply_band_correction([1.0] * 8)
        for v in result:
            assert 0.0 <= v <= 1.0

    def test_negative_inputs_clamped(self):
        """Verify negative inputs are clamped to 0.0 minimum."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        result = apply_band_correction([-0.5] * 8)
        for v in result:
            assert 0.0 <= v <= 1.0

    def test_large_inputs_clamped(self):
        """Verify very large inputs are clamped to 1.0 maximum."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import apply_band_correction
        result = apply_band_correction([999.0] * 8)
        for v in result:
            assert 0.0 <= v <= 1.0


class TestAllModeLabels:
    """Test ``mode_label`` for all defined mode codes.

    The VOACAP mode table defines 7 modes: WSPR(3), FT8(13), FT4(17),
    CW(19), RTTY(22), SSB(38), AM(49). All must return correct labels.
    """

    def test_all_known_modes(self):
        """Verify all 7 known mode codes return correct labels."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from voacap_bandconditions import mode_label
        expected = {
            3: "WSPR", 13: "FT8", 17: "FT4",
            19: "CW", 22: "RTTY", 38: "SSB", 49: "AM",
        }
        for code, label in expected.items():
            assert mode_label(code) == label, f"mode_label({code}) != {label}"


class TestVoacapOutputFormat:
    """Test VOACAP output format using the shared ``sample_voacap_output`` fixture.

    Validates the structural properties of band-conditions output:
    line count, CSV formatting, and hour coverage.
    """

    def test_output_has_26_lines(self, sample_voacap_output):
        """Verify output is exactly 26 lines (header + metadata + 24 hours)."""
        lines = sample_voacap_output.strip().split("\n")
        assert len(lines) == 26

    def test_header_is_csv(self, sample_voacap_output):
        """Verify first line contains 9 comma-separated reliability values."""
        lines = sample_voacap_output.strip().split("\n")
        header_parts = lines[0].split(",")
        assert len(header_parts) == 9

    def test_all_24_hours_present(self, sample_voacap_output):
        """Verify hours 0–23 are all represented in the output."""
        lines = sample_voacap_output.strip().split("\n")
        hours = set()
        for line in lines[2:]:  # skip header and metadata
            hour = int(line.split()[0])
            hours.add(hour)
        assert hours == set(range(24))
