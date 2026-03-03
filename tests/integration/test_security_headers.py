"""Integration tests for HTTP security headers on the OHB container.

This module validates that the lighttpd server emits all required HTTP
security headers as configured in ``lighttpd-conf/99-security-headers.conf``.

Test Classes:
    TestSecurityHeaders:
        Verifies the presence and correct values of defensive headers
        (``X-Frame-Options``, ``X-Content-Type-Options``, ``CSP``,
        ``Referrer-Policy``, ``HSTS``, ``Permissions-Policy``, and
        ``Cache-Control`` on CGI responses).  References vulnerability
        finding V-015.

    TestCORSHeaders:
        Ensures CORS is not configured with a wildcard (``*``) origin,
        which would undermine same-origin protections.

    TestHTTPS:
        Validates that the dashboard ``index.html`` does not reference
        insecure ``http://`` resources (mixed-content prevention).

Prerequisites:
    * A running OHB Docker container (``make -C tests test-integration``).
    * ``OHB_TEST_HOST`` environment variable set.

See Also:
    ``lighttpd-conf/99-security-headers.conf`` — Header configuration.
    ``tests/TEST_README.md`` — Tier 6 reference.
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("OHB_TEST_HOST", "http://localhost:8080")

pytestmark = pytest.mark.skipif(
    not os.environ.get("OHB_TEST_HOST"),
    reason="OHB_TEST_HOST not set — no container running"
)


class TestSecurityHeaders:
    """Verify security headers on all responses (V-015).

    Each test fetches ``/index.html`` and inspects a specific header.
    This class validates the full set of OWASP-recommended HTTP security
    headers.
    """

    def _get_headers(self):
        """Fetch ``/index.html`` and return the response headers dict."""
        r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        return r.headers

    def test_x_frame_options(self):
        """Verify ``X-Frame-Options`` is ``DENY`` or ``SAMEORIGIN`` (clickjacking)."""
        h = self._get_headers()
        val = h.get("X-Frame-Options", "")
        assert val.upper() in ("DENY", "SAMEORIGIN"), \
            f"X-Frame-Options missing or invalid: '{val}'"

    def test_x_content_type_options(self):
        """Verify ``X-Content-Type-Options: nosniff`` is present (MIME sniffing)."""
        h = self._get_headers()
        assert h.get("X-Content-Type-Options", "").lower() == "nosniff", \
            "X-Content-Type-Options: nosniff missing"

    def test_content_security_policy(self):
        """Verify ``Content-Security-Policy`` header is present."""
        h = self._get_headers()
        csp = h.get("Content-Security-Policy", "")
        assert csp, "Content-Security-Policy header missing"

    def test_no_server_version_leak(self):
        """Verify ``Server`` header does not reveal lighttpd version string."""
        h = self._get_headers()
        server = h.get("Server", "")
        # Should not reveal specific version like "lighttpd/1.4.76"
        assert "/" not in server or "lighttpd" not in server.lower(), \
            f"Server header leaks version: '{server}'"

    def test_referrer_policy(self):
        """Verify ``Referrer-Policy`` header is present."""
        h = self._get_headers()
        rp = h.get("Referrer-Policy", "")
        assert rp, "Referrer-Policy header missing"

    def test_strict_transport_security(self):
        """Verify ``Strict-Transport-Security`` header includes ``max-age``."""
        h = self._get_headers()
        hsts = h.get("Strict-Transport-Security", "")
        assert hsts, "Strict-Transport-Security header missing"
        assert "max-age=" in hsts.lower(), "HSTS must have max-age"

    def test_permissions_policy(self):
        """Verify ``Permissions-Policy`` restricts ``geolocation``."""
        h = self._get_headers()
        pp = h.get("Permissions-Policy", "")
        assert pp, "Permissions-Policy header missing"
        assert "geolocation" in pp, "Permissions-Policy should restrict geolocation"

    def test_cache_control_on_cgi(self):
        """Verify CGI endpoints set ``Cache-Control: no-store`` or ``no-cache``."""
        r = requests.get(f"{BASE_URL}/ham/HamClock/version.pl", timeout=5)
        cc = r.headers.get("Cache-Control", "")
        # CGI should ideally prevent caching
        assert "no-store" in cc.lower() or "no-cache" in cc.lower(), \
            "CGI endpoints should have Cache-Control: no-store, no-cache"



class TestCORSHeaders:
    """Verify CORS is restrictive.

    A wildcard ``Access-Control-Allow-Origin: *`` would allow any
    website to make authenticated cross-origin requests to the OHB
    server.
    """

    def test_no_wildcard_cors(self):
        """Verify ``Access-Control-Allow-Origin`` is not ``*`` on static assets."""
        r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        assert acao != "*", f"CORS wildcard * is too permissive"

    def test_cgi_no_cors(self):
        """Verify ``Access-Control-Allow-Origin`` is not ``*`` on CGI endpoints."""
        r = requests.get(
            f"{BASE_URL}/ham/HamClock/version.pl", timeout=5
        )
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        assert acao != "*", "CGI endpoint should not have wildcard CORS"


class TestHTTPS:
    """Verify HTTPS-related behavior.

    Mixed content (loading ``http://`` sub-resources from an HTTPS page)
    is blocked by modern browsers and indicates a configuration error.
    """

    def test_no_mixed_content_in_html(self):
        """Verify ``index.html`` does not reference insecure ``http://`` resources."""
        r = requests.get(f"{BASE_URL}/index.html", timeout=5)
        # HTML should not reference http:// resources
        assert "http://" not in r.text or "http://localhost" in r.text, \
            "Dashboard references insecure HTTP resources"
