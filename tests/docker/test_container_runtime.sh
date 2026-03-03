#!/usr/bin/env bash
# =============================================================================
# test_container_runtime.sh — Verify container runtime services are working
# =============================================================================
#
# Scope:
#   Starts a container with port mapping and validates that all core
#   runtime services (lighttpd, CGI, dashboard, cron) are functional.
#   Unlike test_container_security.sh, this test exercises the HTTP
#   stack end-to-end.
#
# What is Tested:
#   1. Container starts with port mapping — the image can bind to a
#      random localhost port without conflicts.
#   2. lighttpd responds — HTTP GET to / returns 200, 301, or 302.
#   3. version.pl CGI — the VOACAP version endpoint returns expected
#      version information.
#   4. Dashboard accessibility — index.html is served with HTTP 200.
#   5. Content-Type headers — version.pl returns text/plain.
#   6. Cron daemon — the cron process is running inside the container
#      (required for scheduled data fetches).
#
# Port Selection:
#   A random port (8080 + RANDOM % 1000) is used to avoid conflicts
#   with other services or parallel test runs.
#
# Environment Variables:
#   OHB_TEST_IMAGE — Docker image to test (default: ohb:test)
#
# Exit Codes:
#   0 — All checks passed
#   1 — One or more checks failed
#
# Cleanup:
#   The test container is automatically removed via a trap on EXIT.
#
# Runner:
#   OHB_TEST_IMAGE=ohb:test bash tests/docker/test_container_runtime.sh
#
# See Also:
#   tests/TEST_README.md — Tier 5 (Docker Image Tests)
# =============================================================================
set -euo pipefail

IMAGE="${OHB_TEST_IMAGE:-ohb:test}"
CONTAINER="ohb-runtime-test-$$"
HOST_PORT=$((8080 + RANDOM % 1000))
PASS=0
FAIL=0

pass() { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Container Runtime Tests"
echo "    Port: $HOST_PORT"
echo ""

# ── Start container with port mapping ────────────────────────────────────────
# Map a random host port to container port 80 (lighttpd default).
docker run -d --name "$CONTAINER" -p "${HOST_PORT}:80" "$IMAGE" >/dev/null 2>&1 \
    && pass "Container starts with port mapping" \
    || { fail "Container failed to start"; exit 1; }

# Wait for lighttpd to be ready (up to 30 seconds).
# lighttpd needs time to parse configs, load modules, and start listening.
echo "  Waiting for lighttpd..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${HOST_PORT}/" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# ── Test lighttpd is listening ───────────────────────────────────────────────
# A successful response (200, 301, or 302) confirms lighttpd started.
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${HOST_PORT}/" 2>/dev/null || echo 000)"
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    pass "lighttpd responds (HTTP $HTTP_CODE)"
else
    fail "lighttpd not responding (HTTP $HTTP_CODE)"
fi

# ── Test version.pl CGI ──────────────────────────────────────────────────────
# The version endpoint is the simplest CGI script — if it works, the
# CGI execution pipeline (lighttpd → mod_cgi → Perl) is functional.
VERSION_OUTPUT="$(curl -sf "http://localhost:${HOST_PORT}/ham/HamClock/version.pl" 2>/dev/null || echo '')"
if echo "$VERSION_OUTPUT" | grep -q '4\.\|version'; then
    pass "version.pl returns version info"
else
    fail "version.pl did not return expected output: '$VERSION_OUTPUT'"
fi

# ── Test dashboard index ─────────────────────────────────────────────────────
# The dashboard is the primary administrative interface.
DASH_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${HOST_PORT}/index.html" 2>/dev/null || echo 000)"
if [ "$DASH_CODE" = "200" ]; then
    pass "Dashboard index.html accessible (HTTP $DASH_CODE)"
else
    fail "Dashboard index.html not accessible (HTTP $DASH_CODE)"
fi

# ── Test Content-Type headers ────────────────────────────────────────────────
# Correct Content-Type prevents MIME-sniffing attacks and ensures
# browsers render responses safely.
CT="$(curl -s -I "http://localhost:${HOST_PORT}/ham/HamClock/version.pl" 2>/dev/null | grep -i 'content-type' || echo '')"
if echo "$CT" | grep -qi 'text/plain'; then
    pass "version.pl returns text/plain Content-Type"
else
    fail "version.pl Content-Type unexpected: '$CT'"
fi

# ── Test cron is running ─────────────────────────────────────────────────────
# The cron daemon is responsible for periodic data fetches (RSS, NOAA,
# TLE updates). Without cron, cached data will go stale.
CRON_STATUS="$(docker exec "$CONTAINER" pgrep cron 2>/dev/null || echo '')"
if [ -n "$CRON_STATUS" ]; then
    pass "cron daemon is running (PID: $CRON_STATUS)"
else
    fail "cron daemon is not running"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
