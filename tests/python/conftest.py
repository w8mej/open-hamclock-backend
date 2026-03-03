"""Shared pytest fixtures for OHB Python unit tests.

This module provides fixtures consumed by all test modules in the
``tests/python/`` directory.  Fixtures are automatically discovered by
pytest's conftest mechanism — no explicit import is needed.

Key Responsibilities:
    * Inject the project's ``scripts/`` directory into ``sys.path`` so
      production modules (``bz_simple``, ``web15rss_fetch``,
      ``voacap_bandconditions``, etc.) can be imported directly in tests.
    * Provide reusable sample data (RSS XML, NOAA JSON, VOACAP output)
      so that individual test modules do not duplicate fixture boilerplate.

Note:
    The ``sys.path`` insertion happens at module import time (not inside
    a fixture) because pytest discovers and imports test modules before
    fixture setup.  This is intentional.

See Also:
    ``tests/TEST_README.md`` — Tier 3 (Python Unit Tests) reference.
"""

import os
import sys
import tempfile
import shutil

import pytest


# Add the scripts directory to sys.path so we can import project modules
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)


@pytest.fixture
def tmp_dir():
    """Create an isolated temporary directory for the test, cleaned up after.

    Yields:
        str: Absolute path to a freshly-created temporary directory
        prefixed with ``ohb_test_``.

    Cleanup:
        The directory and all contents are removed via ``shutil.rmtree``
        after the test completes, regardless of pass/fail status.
    """
    d = tempfile.mkdtemp(prefix="ohb_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_rss_xml():
    """Return a minimal RSS 2.0 XML document for testing feed parsers.

    The feed mimics the ARNewsLine format used by ``web15rss_fetch.py``,
    containing a single ``<item>`` with ``<content:encoded>`` CDATA
    including bullet-point paragraphs.

    Returns:
        str: Well-formed RSS 2.0 XML string.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
    <channel>
        <title>ARNewsLine</title>
        <item>
            <title>Test Headline One</title>
            <content:encoded><![CDATA[
                <p>- First bullet item</p>
                <p>- Second bullet item</p>
            ]]></content:encoded>
        </item>
    </channel>
    </rss>"""


@pytest.fixture
def sample_noaa_json():
    """Return a minimal NOAA-format JSON string for data script tests.

    Mimics the structure returned by NOAA's real-time solar wind API,
    containing a single measurement with ``time_tag``, ``Bt``, and
    ``Bz`` fields.

    Returns:
        str: JSON-encoded array with one measurement object.
    """
    return '[{"time_tag":"2026-02-25 12:00:00","Bt":5.2,"Bz":-1.3}]'


@pytest.fixture
def sample_voacap_output():
    """Return a sample VOACAP band-conditions output (26 lines).

    Matches the expected output format of ``voacap_bandconditions.py``:
    a header line with reliability values, a metadata line (power, mode,
    TOA, path, SNR), and 24 hourly data lines (hours 1–23, then 0).

    Used By:
        ``test_voacap.py`` — Format validation and output structure tests.

    Returns:
        str: Multi-line string with trailing newline.
    """
    lines = ["0.50,0.30,0.20,0.10,0.05,0.02,0.01,0.00,0.00"]
    lines.append("100W,CW,TOA>3,SP,S=0")
    for hour in list(range(1, 24)) + [0]:
        lines.append(f"{hour} 0.50,0.30,0.20,0.10,0.05,0.02,0.01,0.00,0.00")
    return "\n".join(lines) + "\n"
