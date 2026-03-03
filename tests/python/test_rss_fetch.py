"""Tests for ``web15rss_fetch.py`` — cache writing, encoding, and error resilience.

This module tests the cache subsystem of ``web15rss_fetch.py``, which
fetches amateur radio news feeds and writes them to disk as plain-text
cache files.

Modules Under Test:
    ``scripts/web15rss_fetch.py``
        Fetches RSS feeds from ARNewsLine, DX Engineering News, and
        other sources, then writes processed headlines to
        ``cache/*.txt`` for consumption by HamClock.

Test Strategy:
    Tests override ``web15rss_fetch.CACHE_DIR`` to a temporary directory,
    allowing full verification of file creation, atomic writes, and
    character-encoding conversion without affecting the real cache.

Test Classes:
    TestAtomicCacheWrite:
        Verifies that ``write_cache()`` creates files atomically (no
        partial writes), skips empty input, and leaves no ``.tmp``
        residue.

    TestEncodingHandling:
        Verifies that ``write_cache()`` correctly converts UTF-8 text
        to ISO-8859-1 when requested (HamClock expects Latin-1 encoding
        for proper diacritical rendering).

See Also:
    ``tests/TEST_README.md`` — Tier 3 (Python Unit Tests).
"""

import os
import sys
import tempfile
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestAtomicCacheWrite:
    """Test the ``write_cache`` function for atomicity and correctness.

    Each test overrides ``web15rss_fetch.CACHE_DIR`` to an isolated temp
    directory and restores the original value in teardown, ensuring no
    cross-test pollution.
    """

    def setup_method(self):
        """Create a fresh temporary directory for cache output."""
        self.cache_dir = tempfile.mkdtemp(prefix="ohb_rss_test_")

    def teardown_method(self):
        """Remove the temporary cache directory and all contents."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_write_cache_creates_file(self):
        """Verify ``write_cache()`` creates a ``.txt`` file with expected content.

        Writes two lines to a named cache source and confirms both lines
        appear in the resulting file at ``<cache_dir>/<source>.txt``.
        """
        from web15rss_fetch import write_cache, CACHE_DIR
        import web15rss_fetch
        # Override cache dir
        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            write_cache("test_source", ["line1", "line2"], encoding="utf-8")
            dest = os.path.join(self.cache_dir, "test_source.txt")
            assert os.path.exists(dest)
            with open(dest, "r") as f:
                content = f.read()
            assert "line1" in content
            assert "line2" in content
        finally:
            web15rss_fetch.CACHE_DIR = orig

    def test_write_cache_empty_lines_skipped(self):
        """Verify ``write_cache()`` does not create a file for empty input.

        An empty list of lines should be silently ignored — no file is
        created, and no exception is raised.
        """
        from web15rss_fetch import write_cache
        import web15rss_fetch
        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            write_cache("empty_test", [], encoding="utf-8")
            dest = os.path.join(self.cache_dir, "empty_test.txt")
            # Should NOT create file (empty input)
            assert not os.path.exists(dest)
        finally:
            web15rss_fetch.CACHE_DIR = orig

    def test_write_cache_atomic_no_partial(self):
        """Verify no ``.tmp`` residue remains after a successful write.

        The write-cache function uses a write-to-temp-then-rename pattern
        (atomic write).  After completion, the temp directory should
        contain only the final ``.txt`` file — no intermediate ``.tmp``
        artifacts.
        """
        from web15rss_fetch import write_cache
        import web15rss_fetch
        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            write_cache("atomic_test", ["data"], encoding="utf-8")
            tmp_files = [f for f in os.listdir(self.cache_dir) if f.endswith(".tmp")]
            assert len(tmp_files) == 0, f"Leftover tmp files: {tmp_files}"
        finally:
            web15rss_fetch.CACHE_DIR = orig


class TestEncodingHandling:
    """Test character-encoding conversion in ``write_cache()``.

    HamClock's firmware expects ISO-8859-1 (Latin-1) encoded text for
    proper rendering of accented characters.  This class verifies that
    UTF-8 source text is correctly transcoded.
    """

    def setup_method(self):
        """Create a fresh temporary directory for cache output."""
        self.cache_dir = tempfile.mkdtemp(prefix="ohb_enc_test_")

    def teardown_method(self):
        """Remove the temporary cache directory and all contents."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_utf8_to_iso8859_conversion(self):
        """Verify UTF-8 text is correctly encoded as ISO-8859-1 on disk.

        Writes ``Héllo Wörld`` with ``encoding='iso-8859-1'`` and
        confirms the raw byte ``\\xe9`` (é in Latin-1) is present in
        the output file.
        """
        from web15rss_fetch import write_cache
        import web15rss_fetch
        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            # Write with ISO-8859-1 encoding
            write_cache("iso_test", ["Héllo Wörld"], encoding="iso-8859-1")
            dest = os.path.join(self.cache_dir, "iso_test.txt")
            with open(dest, "rb") as f:
                raw = f.read()
            # é is 0xe9 in ISO-8859-1
            assert b"\xe9" in raw
        finally:
            web15rss_fetch.CACHE_DIR = orig


class TestWriteCacheOverwrite:
    """Test that ``write_cache`` correctly overwrites existing cache files.

    Ensures the atomic write pattern replaces old content cleanly and
    does not corrupt data when called multiple times.
    """

    def setup_method(self):
        """Create a fresh temporary directory for cache output."""
        self.cache_dir = tempfile.mkdtemp(prefix="ohb_overwrite_test_")

    def teardown_method(self):
        """Remove the temporary cache directory and all contents."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_overwrite_replaces_content(self):
        """Verify repeated calls to ``write_cache`` replace prior content."""
        from web15rss_fetch import write_cache
        import web15rss_fetch
        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            write_cache("overwrite_test", ["old_data"], encoding="utf-8")
            write_cache("overwrite_test", ["new_data"], encoding="utf-8")
            dest = os.path.join(self.cache_dir, "overwrite_test.txt")
            with open(dest, "r") as f:
                content = f.read()
            assert "new_data" in content
            assert "old_data" not in content
        finally:
            web15rss_fetch.CACHE_DIR = orig


class TestFetchArnewslineMocked:
    """Test ``fetch_arnewsline()`` with mocked HTTP responses.

    Uses ``unittest.mock.patch`` to replace ``requests.get`` with a
    synthetic ARNewsLine RSS feed, validating the HTML parsing and
    bullet extraction logic without network I/O.
    """

    def setup_method(self):
        """Create a fresh temporary directory for cache output."""
        self.cache_dir = tempfile.mkdtemp(prefix="ohb_arn_test_")

    def teardown_method(self):
        """Remove the temporary cache directory and all contents."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_fetch_arnewsline_parses_bullets(self):
        """Verify bullet lines from ARNewsLine RSS are extracted correctly."""
        from unittest.mock import patch, MagicMock
        import web15rss_fetch

        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <channel>
            <title>ARNewsLine</title>
            <item>
                <title>Test Issue</title>
                <content:encoded><![CDATA[
                    <p>- First headline from ARNewsLine</p>
                    <p>- Second headline from ARNewsLine</p>
                ]]></content:encoded>
            </item>
        </channel>
        </rss>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_xml
        mock_resp.raise_for_status = MagicMock()

        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            with patch("web15rss_fetch.requests.get", return_value=mock_resp):
                web15rss_fetch.fetch_arnewsline()

            dest = os.path.join(self.cache_dir, "arnewsline.txt")
            assert os.path.exists(dest), "arnewsline.txt not created"
            with open(dest, "r") as f:
                content = f.read()
            assert "First headline" in content
            assert "Second headline" in content
            assert "ARNewsLine.org:" in content
        finally:
            web15rss_fetch.CACHE_DIR = orig

    def test_fetch_arnewsline_empty_feed_raises(self):
        """Verify ``fetch_arnewsline`` raises when feed has no entries."""
        from unittest.mock import patch, MagicMock
        import web15rss_fetch

        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_xml
        mock_resp.raise_for_status = MagicMock()

        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            with patch("web15rss_fetch.requests.get", return_value=mock_resp):
                with pytest.raises(ValueError, match="No entries"):
                    web15rss_fetch.fetch_arnewsline()
        finally:
            web15rss_fetch.CACHE_DIR = orig


class TestFetchHamweeklyMocked:
    """Test ``fetch_hamweekly()`` with mocked HTTP responses.

    Validates Atom feed parsing and title extraction for HamWeekly.
    """

    def setup_method(self):
        """Create a fresh temporary directory for cache output."""
        self.cache_dir = tempfile.mkdtemp(prefix="ohb_hw_test_")

    def teardown_method(self):
        """Remove the temporary cache directory and all contents."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_fetch_hamweekly_parses_titles(self):
        """Verify HamWeekly titles are extracted from Atom feed."""
        from unittest.mock import patch, MagicMock
        import web15rss_fetch

        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>HamWeekly Daily</title>
            <entry><title>Weekly Roundup: DX and Contests</title></entry>
            <entry><title>Solar Update: Cycle 25 Peaks</title></entry>
        </feed>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = atom_xml
        mock_resp.raise_for_status = MagicMock()

        orig = web15rss_fetch.CACHE_DIR
        web15rss_fetch.CACHE_DIR = self.cache_dir
        try:
            with patch("web15rss_fetch.requests.get", return_value=mock_resp):
                web15rss_fetch.fetch_hamweekly()

            dest = os.path.join(self.cache_dir, "hamweekly.txt")
            assert os.path.exists(dest), "hamweekly.txt not created"
            with open(dest, "r") as f:
                content = f.read()
            assert "Weekly Roundup" in content
            assert "Solar Update" in content
            assert "HamWeekly.com:" in content
        finally:
            web15rss_fetch.CACHE_DIR = orig


class TestFetchHTTPErrorHandling:
    """Test error handling when upstream HTTP requests fail.

    Validates that ``requests.exceptions.HTTPError`` is properly raised
    when the upstream server returns a non-2xx status code.
    """

    def test_http_500_raises(self):
        """Verify HTTP 500 from upstream raises ``HTTPError``."""
        from unittest.mock import patch, MagicMock
        import requests as req_lib
        import web15rss_fetch

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = MagicMock(
            side_effect=req_lib.exceptions.HTTPError("500 Server Error")
        )

        with patch("web15rss_fetch.requests.get", return_value=mock_resp):
            with pytest.raises(req_lib.exceptions.HTTPError):
                web15rss_fetch.fetch_arnewsline()
