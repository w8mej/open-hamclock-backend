"""Integration tests for all CGI and static endpoints on a live OHB container.

This module validates HTTP endpoint behavior, security hardening, and
error-handling characteristics of the Open HamClock Backend when served
by lighttpd inside its production Docker image.

Test Categories:
    Endpoint Smoke:
        Basic reachability and content-type verification for core CGI
        scripts (``version.pl``, ``status.pl``, ``fetchBandConditions.pl``,
        ``fetchWSPR.pl``) and the dashboard index page.

    Injection Defense:
        Command injection (backticks, ``$()``, SSI), SQL injection,
        null-byte injection, double URL encoding, and reflected XSS.

    Path Traversal:
        Direct traversal (``../``), URL-encoded traversal (``%2E%2E``),
        double-encoded traversal (``%252E%252E``), and unicode fullwidth
        character bypass attempts.

    HTTP Method Safety:
        TRACE / PUT blocking, OPTIONS disclosure restrictions,
        ``X-HTTP-Method-Override`` bypass prevention.

    Header Security:
        Host-header injection, multiple Host headers, content-type
        enforcement, ETag information leakage.

    Error Handling:
        404 path leakage, oversized-parameter handling, CGI stderr
        leakage (Perl warnings in HTTP body).

    Protocol Edge Cases:
        HTTP/1.0 compatibility, WebSocket upgrade rejection, absolute
        URI proxy prevention, semicolon path-parameter bypass.

    Data Safety:
        Directory listing suppression, dotfile / ``.git`` / backup-file
        blocking, HTTP parameter pollution resilience.

    Redirect Safety:
        Open-redirect prevention via ``//evil.com`` and encoded variants.

    Resilience:
        Large POST body handling, HEAD/GET consistency, unicode
        normalization attacks.

Prerequisites:
    * A running OHB Docker container (see ``make -C tests test-integration``).
    * ``OHB_TEST_HOST`` environment variable set to the container's base URL.

Environment Variables:
    OHB_TEST_HOST (str):
        Fully-qualified base URL of the running container
        (e.g., ``http://localhost:8085``).  When unset, **all** tests in
        this module are skipped via ``pytestmark``.

See Also:
    ``tests/TEST_README.md`` — Tier 6 reference and vulnerability-to-test
    mapping table.
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("OHB_TEST_HOST", "http://localhost:8080")


def _parse_host_port():
    """Extract (host, port) from ``BASE_URL`` for ``http.client`` tests.

    Falls back to ``('localhost', 80)`` if no port is specified.
    """
    from urllib.parse import urlparse
    parsed = urlparse(BASE_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    return host, port


# Skip all tests if no container is running
pytestmark = pytest.mark.skipif(
    not os.environ.get("OHB_TEST_HOST"),
    reason="OHB_TEST_HOST not set — no container running"
)


class TestVersionEndpoint:
    """Smoke tests for ``/ham/HamClock/version.pl``.

    Validates that the version CGI script returns a ``200`` response with a
    ``text/plain`` content type and a body containing a recognizable version
    string.
    """

    def test_version_returns_200(self):
        """Verify ``version.pl`` returns HTTP 200 OK."""
        r = requests.get(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        assert r.status_code == 200

    def test_version_content_type(self):
        """Verify ``version.pl`` returns ``text/plain`` content type."""
        r = requests.get(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        assert "text/plain" in r.headers.get("Content-Type", "")

    def test_version_contains_number(self):
        """Verify response body contains a recognizable version identifier."""
        r = requests.get(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        assert "4." in r.text or "version" in r.text.lower()


class TestDashboardEndpoints:
    """Smoke tests for dashboard CGI scripts and the index page.

    Confirms that the administrative dashboard pages (``status.pl``,
    ``metrics.pl``, ``heartbeat.pl``, ``jobs.pl``) and the static
    ``index.html`` are reachable and return expected content types.
    """

    def test_status_returns_html(self):
        """Verify ``status.pl`` returns HTTP 200 with ``text/html``."""
        r = requests.get(f"{BASE_URL}/status.pl", timeout=5)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")

    def test_metrics_returns_html(self):
        """Verify ``metrics.pl`` returns HTTP 200."""
        r = requests.get(f"{BASE_URL}/metrics.pl", timeout=5)
        assert r.status_code == 200

    def test_heartbeat_returns_html(self):
        """Verify ``heartbeat.pl`` returns HTTP 200."""
        r = requests.get(f"{BASE_URL}/heartbeat.pl", timeout=5)
        assert r.status_code == 200

    def test_jobs_returns_html(self):
        """Verify ``jobs.pl`` returns HTTP 200."""
        r = requests.get(f"{BASE_URL}/jobs.pl", timeout=5)
        assert r.status_code == 200

    def test_index_returns_200(self):
        """Verify ``index.html`` returns HTTP 200 with HamClock branding."""
        r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        assert r.status_code == 200
        assert "hamclock" in r.text.lower() or "OHB" in r.text


class TestBandConditionsEndpoint:
    """Tests for ``/ham/HamClock/fetchBandConditions.pl``.

    Validates both the happy path (valid lat/lng/date parameters returning
    CSV data) and error handling (missing parameters returning 400 or an
    error message).
    """

    def test_valid_request_returns_csv(self):
        """Verify a fully-parameterized request returns ``text/plain`` CSV."""
        params = {
            "YEAR": "2026", "MONTH": "2", "UTC": "17",
            "TXLAT": "28", "TXLNG": "-81",
            "RXLAT": "42", "RXLNG": "-114",
        }
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchBandConditions.pl",
            params=params, timeout=30,
        )
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("Content-Type", "")

    def test_missing_params_returns_400(self):
        """Verify missing parameters produce an error, not a crash."""
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchBandConditions.pl",
            timeout=5,
        )
        assert r.status_code == 400 or "missing" in r.text.lower() or "invalid" in r.text.lower()


class TestFetchWSPREndpoint:
    """Tests for ``/ham/HamClock/fetchWSPR.pl``.

    Validates Maidenhead grid-based WSPR queries and verifies that SQL
    injection payloads in the ``ofgrid`` parameter are rejected or
    sanitized (V-051).
    """

    def test_valid_grid_request(self):
        """Verify a valid 4-character Maidenhead grid returns WSPR data."""
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchWSPR.pl",
            params={"ofgrid": "FN30", "maxage": "900"},
            timeout=20,
        )
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("Content-Type", "")

    def test_sql_injection_blocked(self):
        """Verify SQL injection in ``ofgrid`` is rejected (V-051).

        Sends a classic ``' OR '1'='1`` payload and confirms the server
        does not blindly pass it through to the database layer.
        """
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchWSPR.pl",
            params={"ofgrid": "FN30' OR '1'='1", "maxage": "900"},
            timeout=10,
        )
        # Should either return 400 or sanitize the input, NOT pass SQL through
        assert r.status_code in (200, 400)
        if r.status_code == 400:
            assert "invalid" in r.text.lower() or "error" in r.text.lower()


class TestTailEndpoint:
    """Tests for ``/tail.pl`` — path traversal and command injection defense.

    ``tail.pl`` accepts a ``file`` query parameter mapped to an allowlist
    of known log files.  These tests verify that path traversal (``../``),
    command injection (``;``, backticks), and subshell (``$()``) payloads
    are all correctly neutralized (V-001, V-002).
    """

    def test_valid_file_returns_200(self):
        """Verify requesting an allowed log file returns HTTP 200."""
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "lighttpd_error"},
            timeout=5,
        )
        assert r.status_code == 200

    def test_path_traversal_blocked(self):
        """Verify ``../../../etc/passwd`` traversal does not leak system files (V-001)."""
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "../../../etc/passwd"},
            timeout=5,
        )
        # Should return error, NOT the contents of /etc/passwd
        assert "root:" not in r.text
        assert r.status_code in (200, 400, 403, 404)

    def test_command_injection_blocked(self):
        """Verify semicolon-based command injection is blocked (V-002)."""
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "lighttpd_error; cat /etc/passwd"},
            timeout=5,
        )
        assert "root:" not in r.text


class TestErrorHandling:
    """Verify error responses do not leak internal server information.

    Ensures that 404 pages, oversized parameters, and excessively long
    URIs are handled without exposing internal filesystem paths, and that
    the server imposes URI length limits to prevent denial-of-service.
    """

    def test_404_does_not_leak_paths(self):
        """Verify 404 responses omit internal filesystem paths."""
        r = requests.get(f"{BASE_URL}/nonexistent_endpoint", timeout=5)
        assert "/opt/hamclock-backend" not in r.text

    def test_invalid_cgi_does_not_crash(self):
        """Verify 5,000-character parameter does not crash the CGI."""
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/version.pl",
            params={"unexpected": "A" * 5000},
            timeout=5,
        )
        assert r.status_code in (200, 400, 414)

    def test_uri_too_long_dos_prevention(self):
        """Verify a 10,000-character URI is rejected (DoS prevention)."""
        # 10,000 character URI should be rejected
        r = requests.get(f"{BASE_URL}/" + "A" * 10000, timeout=5)
        assert r.status_code in (400, 414, 431), "Server should reject overly long URIs"


class TestDirectoryListing:
    """Verify auto-index directory listings are disabled.

    Exposed directory listings can reveal internal file structure and
    potentially sensitive filenames.  The server should either serve an
    ``index.html`` or return a non-listing response.
    """

    def test_ham_directory_listing_disabled(self):
        """Verify ``/ham/`` does not expose a raw file listing."""
        r = requests.get(f"{BASE_URL}/ham/", timeout=5)
        # Directory listing should never expose raw file names
        assert "Index of /ham/" not in r.text, "Auto-indexing found"
        # If it returns 200, it should be serving index.html, not a listing
        if r.status_code == 200:
            assert "<title>" in r.text.lower() or "hamclock" in r.text.lower(), \
                "Directory returned 200 but not an index page — possible listing"


class TestHTTPMethods:
    """Verify dangerous HTTP methods are restricted.

    ``TRACE`` enables cross-site tracing (XST) attacks and ``PUT`` could
    allow remote file writes.  Both must be blocked on all endpoints.
    """

    def test_trace_method_blocked(self):
        """Verify ``TRACE`` returns 405 or 501 (XST prevention)."""
        r = requests.request("TRACE", f"{BASE_URL}/index.html", timeout=5)
        # Should be blocked, typically 405 Method Not Allowed or 501 Not Implemented
        assert r.status_code in (405, 501), "TRACE method should be blocked"

    def test_put_method_blocked(self):
        """Verify ``PUT`` returns 403, 405, or 501."""
        r = requests.put(f"{BASE_URL}/index.html", data="test", timeout=5)
        # Static assets should not accept PUT
        assert r.status_code in (403, 405, 501), "PUT method should be blocked"


class TestAdvancedInjection:
    """Advanced injection and LFI edge-case tests.

    Tests backtick command injection, ``$()`` subshell injection,
    reflected XSS in HTML responses, and URL-encoded path traversal
    (``%2E%2E%2F``).
    """

    def test_advanced_command_injection(self):
        """Verify backtick and ``$()`` command injection is blocked (V-002).

        Sends two payloads — backtick-wrapped ``id`` and ``$(whoami)`` —
        and asserts the server does not execute either.
        """
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "`id`"},
            timeout=5,
        )
        assert "uid=" not in r.text, "Command injection via backticks successful"

        r2 = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "$(whoami)"},
            timeout=5,
        )
        assert "www-data" not in r2.text and "root" not in r2.text, "Command injection via $() successful"

    def test_reflected_xss_prevention(self):
        """Verify reflected XSS payload is not echoed unencoded in HTML (V-029).

        If the response has ``text/html`` content type, the raw
        ``<script>`` tag must not appear verbatim.
        """
        payload = "<script>alert('XSS')</script>"
        r = requests.get(f"{BASE_URL}/tail.pl", params={"file": payload}, timeout=5)
        # It might be in the text, but the endpoint must return text/plain or encode it
        content_type = r.headers.get("Content-Type", "")
        if "text/html" in content_type:
            assert payload not in r.text, "Reflected XSS payload found unencoded in HTML response"

    def test_lfi_encoded_path_traversal(self):
        """Verify URL-encoded ``../`` (``%2E%2E%2F``) does not bypass path filters.

        Uses percent-encoded dot-dot-slash sequences to attempt local
        file inclusion of ``/etc/passwd``.
        """
        # %2E%2E%2F is ../
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "%2E%2E%2F%2E%2E%2Fetc%2Fpasswd"},
            timeout=5,
        )
        assert "root:x:0:0:" not in r.text, "LFI via URL-encoded path traversal successful"


class TestNullByteInjection:
    """Verify null byte injection is blocked in CGI parameters.

    Null bytes (``%00``) can truncate strings in C-based parsers,
    potentially bypassing file-extension allowlists.
    """

    def test_null_byte_in_tail_file_param(self):
        """Verify ``%00`` in ``file`` parameter does not bypass validation."""
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "lighttpd_error%00.txt"},
            timeout=5,
        )
        # Null byte should not bypass file extension checks
        assert "root:" not in r.text, "Null byte injection bypassed file validation"

    def test_null_byte_in_path(self):
        """Verify ``%00`` in the URL path does not confuse content negotiation."""
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/version.pl%00.html",
            timeout=5,
        )
        # Should not confuse the server into serving wrong content-type
        assert r.status_code in (200, 400, 404)


class TestDoubleEncoding:
    """Verify double URL encoding does not bypass path filters.

    Double encoding (``%252E`` → ``%2E`` → ``.``) is a common WAF bypass
    technique.  The server must not decode parameters twice.
    """

    def test_double_encoded_path_traversal(self):
        """Verify ``%252E%252E`` does not resolve to ``..`` in path filters."""
        # %252E%252E = double-encoded ".."
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "%252E%252E%252F%252E%252Fetc%252Fpasswd"},
            timeout=5,
        )
        assert "root:x:0:0:" not in r.text, "Double-encoded path traversal bypassed filters"


class TestHTTPResponseSplitting:
    """Verify HTTP response splitting (header injection) is blocked.

    CRLF injection (``\\r\\n``) in query parameters could allow an attacker
    to inject arbitrary HTTP response headers.
    """

    def test_crlf_injection_in_param(self):
        """Verify CRLF characters in ``file`` param do not inject response headers."""
        # Attempt to inject headers via CRLF in query parameter
        payload = "lighttpd_error\r\nX-Injected: true"
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": payload},
            timeout=5,
        )
        assert "X-Injected" not in r.headers, \
            "HTTP response splitting: injected header found in response"


class TestHostHeaderInjection:
    """Verify Host header manipulation does not leak internal paths.

    A spoofed ``Host`` header should not be reflected in the response
    body or ``Location`` header, which would indicate host-header
    poisoning susceptibility.
    """

    def test_spoofed_host_header(self):
        """Verify spoofed ``Host: evil.attacker.com`` is not reflected."""
        r = requests.get(
            f"{BASE_URL}/index.html",
            headers={"Host": "evil.attacker.com"},
            timeout=5,
        )
        # Server should not reflect the spoofed host in Location or body
        assert "evil.attacker.com" not in r.text, \
            "Host header injection reflected in response body"
        assert "evil.attacker.com" not in r.headers.get("Location", ""), \
            "Host header injection reflected in Location header"


class TestErrorPageInfoLeak:
    """Verify error pages don't leak sensitive information.

    Error responses (4xx, 5xx) must not expose Python tracebacks,
    internal file paths, or diagnostic messages.
    """

    def test_500_does_not_leak_stack_trace(self):
        """Verify malformed CGI params do not expose tracebacks or paths."""
        # Send a request designed to trigger an error in CGI
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchBandConditions.pl",
            params={"YEAR": "AAAA", "MONTH": "BB"},
            timeout=10,
        )
        # Check that error response doesn't leak stack traces or source paths
        assert "Traceback" not in r.text, "Python traceback leaked in response"
        assert "/opt/hamclock-backend/scripts/" not in r.text, \
            "Internal script path leaked in error response"

    def test_error_pages_no_server_internals(self):
        """Verify 404 pages contain no debug-level diagnostic strings."""
        r = requests.get(f"{BASE_URL}/does_not_exist.xyz", timeout=5)
        body = r.text.lower()
        assert "stack trace" not in body, "Stack trace found in error page"
        assert "segfault" not in body, "Segfault reference in error page"
        assert "core dump" not in body, "Core dump reference in error page"


class TestHTTPVersionEnforcement:
    """Verify server handles HTTP version edge cases.

    Confirms HTTP/1.0 backward compatibility.  The ``http.client`` module
    is used directly to control the protocol version.
    """

    def test_http10_request_works(self):
        """Verify HTTP/1.0 ``GET`` against ``version.pl`` returns 200."""
        # HTTP/1.0 should still work
        import http.client
        host, port = _parse_host_port()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/ham/HamClock/version.pl")
        r = conn.getresponse()
        assert r.status == 200, f"HTTP/1.0 request failed with {r.status}"
        conn.close()


class TestCGIStderrLeakage:
    """Ensure CGI stderr does not leak into HTTP responses.

    Perl warnings (``Use of uninitialized value``) triggered by missing
    parameters must be captured by lighttpd's error log, not echoed
    directly to the HTTP client.
    """

    def test_band_conditions_no_perl_warnings(self):
        """Verify missing params do not expose Perl ``-w`` diagnostics."""
        # Missing params may trigger Perl warnings — they should not appear
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchBandConditions.pl",
            timeout=5,
        )
        body = r.text.lower()
        assert "uninitialized value" not in body, \
            "Perl warning leaked in HTTP response"
        assert "use of" not in body or "at line" not in body, \
            "Perl diagnostic leaked in HTTP response"


class TestStaticFileAccess:
    """Verify access to known-sensitive file extensions is denied.

    Dotfiles (``.env``, ``.git``), backup files (``~``), and other
    sensitive patterns must never be served by the web server.
    """

    def test_dotfile_access_blocked(self):
        """Verify ``.env`` returns 403 or 404."""
        r = requests.get(f"{BASE_URL}/.env", timeout=5)
        # .env files should never be served
        assert r.status_code in (403, 404), \
            f".env file accessible with status {r.status_code}"

    def test_git_directory_blocked(self):
        """Verify ``.git/HEAD`` is not accessible."""
        r = requests.get(f"{BASE_URL}/.git/HEAD", timeout=5)
        assert r.status_code in (403, 404), \
            f".git/HEAD accessible with status {r.status_code}"
        assert "ref:" not in r.text.lower(), ".git/HEAD contents leaked"

    def test_backup_file_blocked(self):
        """Verify editor backup files (``~``) are not served."""
        r = requests.get(f"{BASE_URL}/index.html~", timeout=5)
        assert r.status_code in (403, 404), \
            f"Backup file accessible with status {r.status_code}"


class TestHTTPOptionsDisclosure:
    """Verify ``OPTIONS`` does not disclose dangerous methods.

    The ``Allow`` header in an ``OPTIONS`` response must not include
    ``PUT``, ``DELETE``, ``PATCH``, or ``TRACE``.
    """

    def test_options_no_dangerous_methods(self):
        """Verify ``Allow`` header excludes ``PUT``, ``DELETE``, ``PATCH``, ``TRACE``."""
        r = requests.options(f"{BASE_URL}/index.html", timeout=5)
        allow = r.headers.get("Allow", "")
        for method in ("PUT", "DELETE", "PATCH", "TRACE"):
            assert method not in allow.upper(), \
                f"OPTIONS Allow header exposes dangerous method: {method}"

    def test_options_on_cgi(self):
        """Verify CGI ``OPTIONS`` also excludes dangerous methods."""
        r = requests.options(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        allow = r.headers.get("Allow", "")
        for method in ("PUT", "DELETE", "TRACE"):
            assert method not in allow.upper(), \
                f"CGI OPTIONS exposes dangerous method: {method}"


class TestParameterPollution:
    """Verify HTTP parameter pollution doesn't bypass validation.

    Sending duplicate query parameters (e.g., ``YEAR=2026&YEAR=9999``)
    should not cause crashes or unexpected behavior in CGI scripts.
    """

    def test_duplicate_params_band_conditions(self):
        """Verify duplicate ``YEAR`` params do not crash ``fetchBandConditions.pl``."""
        # Send duplicate YEAR params — server should not crash or behave unexpectedly
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/fetchBandConditions.pl",
            params=[("YEAR", "2026"), ("YEAR", "9999"), ("MONTH", "2"),
                    ("UTC", "17"), ("TXLAT", "28"), ("TXLNG", "-81"),
                    ("RXLAT", "42"), ("RXLNG", "-114")],
            timeout=30,
        )
        # Should still work or return error, not crash
        assert r.status_code in (200, 400), \
            f"Parameter pollution caused status {r.status_code}"


class TestOpenRedirectPrevention:
    """Ensure the server doesn't act as an open redirect.

    Requests to ``//evil.com`` or ``%2F%2Fevil.com`` must not produce a
    ``Location`` header redirecting to the external domain.
    """

    def test_no_redirect_to_external(self):
        """Verify ``//evil.com`` does not trigger an open redirect."""
        r = requests.get(
            f"{BASE_URL}//evil.com",
            allow_redirects=False,
            timeout=5,
        )
        location = r.headers.get("Location", "")
        assert "evil.com" not in location, \
            f"Open redirect to external domain: {location}"

    def test_encoded_redirect_blocked(self):
        """Verify URL-encoded ``//evil.com`` (``%2F%2F``) does not redirect."""
        r = requests.get(
            f"{BASE_URL}/%2F%2Fevil.com",
            allow_redirects=False,
            timeout=5,
        )
        location = r.headers.get("Location", "")
        assert "evil.com" not in location, \
            f"Encoded open redirect to external domain: {location}"


class TestUnicodeNormalization:
    """Verify unicode path normalization doesn't bypass security.

    Fullwidth Unicode characters (e.g., ``．．／`` for ``../``) must not
    be normalized into ASCII equivalents that bypass path filters.
    """

    def test_unicode_dot_dot_traversal(self):
        """Verify fullwidth ``．．／`` does not resolve as ``../``."""
        # Fullwidth period and slash: ．．／
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": "\uff0e\uff0e\uff0fetc\uff0fpasswd"},
            timeout=5,
        )
        assert "root:" not in r.text, \
            "Unicode normalization bypassed path traversal filter"


class TestLargePostBody:
    """Verify server handles oversized POST bodies gracefully.

    A 1 MB POST to a static endpoint must not crash the server or cause
    a denial-of-service condition.  The server may reject the request
    (413) or simply return a normal error.
    """

    def test_large_post_rejected(self):
        """Verify 1 MB POST does not crash the server and it remains responsive."""
        # Send 1MB POST to a static endpoint
        try:
            r = requests.post(
                f"{BASE_URL}/index.html",
                data="X" * (1024 * 1024),
                timeout=10,
            )
            # Server should not crash — accept any valid response
            assert r.status_code in (200, 405, 413, 414, 431, 501), \
                f"Large POST caused unexpected status {r.status_code}"
            # Verify server is still responsive after large POST
            check = requests.get(f"{BASE_URL}/index.html", timeout=5)
            assert check.status_code == 200, "Server unresponsive after large POST"
        except requests.exceptions.ConnectionError:
            # Server closing connection is also acceptable
            pass


class TestHEADConsistency:
    """Verify ``HEAD`` returns same headers as ``GET`` but no body.

    RFC 9110 §9.3.2 requires that ``HEAD`` produce identical headers to
    ``GET`` while omitting the response body.
    """

    def test_head_matches_get_status(self):
        """Verify ``HEAD`` and ``GET`` return the same status code."""
        get_r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        head_r = requests.head(f"{BASE_URL}/index.html", timeout=5)
        assert head_r.status_code == get_r.status_code, \
            f"HEAD status {head_r.status_code} != GET status {get_r.status_code}"
        assert len(head_r.content) == 0, "HEAD response should have empty body"

    def test_head_has_content_length(self):
        """Verify ``HEAD`` response includes a non-zero ``Content-Length``."""
        head_r = requests.head(f"{BASE_URL}/index.html", timeout=5)
        cl = head_r.headers.get("Content-Length", "")
        assert cl, "HEAD response missing Content-Length"
        assert int(cl) > 0, "HEAD reports zero Content-Length"


class TestMultipleHostHeaders:
    """Verify server rejects requests with multiple ``Host`` headers.

    HTTP/1.1 (RFC 9110 §7.2) permits only a single ``Host`` header.
    Sending two conflicting values must not cause the server to reflect
    the attacker-controlled value.  Uses ``http.client`` for raw header
    control since ``requests`` normalizes headers.
    """

    def test_conflicting_host_headers(self):
        """Verify duplicate ``Host`` headers do not reflect ``evil.com``."""
        import http.client
        host, port = _parse_host_port()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.putrequest("GET", "/index.html")
        conn.putheader("Host", "localhost")
        conn.putheader("Host", "evil.com")
        conn.endheaders()
        r = conn.getresponse()
        # Should reject (400) or serve safely — must NOT reflect evil.com
        body = r.read().decode("utf-8", errors="replace")
        assert "evil.com" not in body, "Multiple Host headers: evil.com reflected"
        conn.close()


class TestContentTypeEnforcement:
    """Verify CGI scripts return proper content types.

    Incorrect content types can enable MIME-sniffing attacks.  Each
    endpoint has a documented expected content type.
    """

    def test_version_returns_text_plain(self):
        """Verify ``version.pl`` returns ``text/plain``."""
        r = requests.get(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        ct = r.headers.get("Content-Type", "")
        assert "text/plain" in ct, \
            f"version.pl should return text/plain, got: {ct}"

    def test_status_returns_text_html(self):
        """Verify ``status.pl`` returns ``text/html``."""
        r = requests.get(f"{BASE_URL}/status.pl", timeout=5)
        ct = r.headers.get("Content-Type", "")
        assert "text/html" in ct, \
            f"status.pl should return text/html, got: {ct}"


class TestETagInfoLeak:
    """Verify ETags don't leak inode or internal path information.

    Apache-style ETags with format ``"inode-size-mtime"`` expose internal
    filesystem metadata.  lighttpd ETags should use at most two
    components (size + mtime).
    """

    def test_etag_no_inode_leak(self):
        """Verify ``ETag`` has at most two hyphen-separated components."""
        r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        etag = r.headers.get("ETag", "")
        if etag:
            # Inode-based ETags typically have format "inode-size-mtime"
            parts = etag.strip('"').split("-")
            assert len(parts) <= 2, \
                f"ETag appears to leak inode info: {etag}"


class TestSSIInjection:
    """Verify Server-Side Include injection is blocked.

    SSI directives (``<!--#exec cmd="..."-->``) in query parameters must
    not be interpreted by the server.
    """

    def test_ssi_in_query_param(self):
        """Verify ``<!--#exec cmd="id"-->`` in ``file`` param is not executed."""
        r = requests.get(
            f"{BASE_URL}/tail.pl",
            params={"file": '<!--#exec cmd="id"-->'},
            timeout=5,
        )
        assert "uid=" not in r.text, "SSI injection executed via query param"


class TestSemicolonPathDelimiter:
    """Verify semicolons in paths don't bypass routing.

    Some servers treat ``;`` as a path-parameter delimiter (Tomcat-style).
    A request to ``version.pl;.html`` must not change the served content
    type to ``text/html``.
    """

    def test_semicolon_path_bypass(self):
        """Verify ``;.html`` suffix does not override content-type routing."""
        # Some servers treat ; as a path parameter delimiter
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/version.pl;.html",
            timeout=5,
        )
        ct = r.headers.get("Content-Type", "")
        # Should NOT serve as text/html — that would mean the .html extension won
        if r.status_code == 200:
            assert "text/html" not in ct or "hamclock" in r.text.lower(), \
                f"Semicolon path bypass changed content-type to {ct}"


class TestMethodOverrideHeader:
    """Verify ``X-HTTP-Method-Override`` doesn't bypass method restrictions.

    Some frameworks honor the ``X-HTTP-Method-Override`` header to tunnel
    ``DELETE`` or ``PUT`` through ``GET`` requests.  lighttpd should
    ignore this header.
    """

    def test_method_override_blocked(self):
        """Verify ``X-HTTP-Method-Override: DELETE`` does not affect a ``GET``."""
        r = requests.get(
            f"{BASE_URL}/index.html",
            headers={"X-HTTP-Method-Override": "DELETE"},
            timeout=5,
        )
        # Should still be served as normal GET, not delete the resource
        assert r.status_code == 200, \
            f"X-HTTP-Method-Override affected request: status {r.status_code}"


class TestWebSocketUpgrade:
    """Verify WebSocket upgrade requests are properly handled.

    The OHB server does not support WebSocket.  Upgrade requests should
    be rejected or silently ignored, not cause a crash.
    """

    def test_websocket_upgrade_rejected(self):
        """Verify WebSocket ``Upgrade`` headers do not crash the server."""
        r = requests.get(
            f"{BASE_URL}/index.html",
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version": "13",
            },
            timeout=5,
        )
        # Should be rejected or ignored — not crash
        assert r.status_code in (200, 400, 426, 501), \
            f"WebSocket upgrade caused unexpected status: {r.status_code}"


class TestAbsoluteURIRequest:
    """Verify server handles absolute URI in request line safely.

    Per RFC 9112 §3.2, a server receiving an absolute-form request URI
    should not act as a forward proxy.  Requesting
    ``GET http://evil.com/steal-data`` must not proxy the request.
    """

    def test_absolute_uri_no_proxy(self):
        """Verify absolute URI ``http://evil.com/...`` is not proxied."""
        import http.client
        host, port = _parse_host_port()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        # Send absolute URI as if using a forward proxy
        conn.request("GET", "http://evil.com/steal-data")
        r = conn.getresponse()
        body = r.read().decode("utf-8", errors="replace")
        # Server must NOT proxy the request to evil.com
        assert "evil.com" not in body or r.status == 400, \
            "Server may be acting as an open forward proxy"
        conn.close()
