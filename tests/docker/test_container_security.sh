#!/usr/bin/env bash
# =============================================================================
# test_container_security.sh — Verify container runtime security properties
# =============================================================================
#
# Scope:
#   Starts a container from the OHB image and validates that runtime
#   security hardening is correctly applied.  The container is started
#   without port mapping (no HTTP traffic needed) and inspected via
#   `docker exec`.
#
# What is Tested:
#   1. Container starts — the image runs without immediate crash.
#   2. Non-root process (V-008) — the main process runs as a
#      non-root user (typically www-data).
#   3. /etc/shadow permissions — the shadow password file must not
#      be world-readable (last octal digit must be 0).
#   4. No curl installed — curl in a production container enables
#      SSRF and data exfiltration from inside the container.
#   5. CGI executability — fetchBandConditions.pl must have the
#      execute bit set for lighttpd to run it as CGI.
#   6. Log directory ownership — /opt/hamclock-backend/logs must be
#      owned by www-data or root.
#   7. SUID binary count — excessive SUID binaries increase the
#      privilege-escalation attack surface (threshold: ≤ 3).
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
#   OHB_TEST_IMAGE=ohb:test bash tests/docker/test_container_security.sh
#
# See Also:
#   tests/TEST_README.md — Tier 5 (Docker Image Tests)
#   V-008 — Container runs as root
# =============================================================================
set -euo pipefail

IMAGE="${OHB_TEST_IMAGE:-ohb:test}"
CONTAINER="ohb-security-test-$$"
PASS=0
FAIL=0

pass() { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Container Security Tests"
echo ""

# ── Start container ──────────────────────────────────────────────────────────
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null 2>&1 \
    && pass "Container starts successfully" \
    || { fail "Container failed to start"; exit 1; }

sleep 3  # let init scripts run

# ── Check running user (V-008) ──────────────────────────────────────────────
# The container must not run its main process as root. A compromised
# process running as root can escape the container namespace.
RUN_USER="$(docker exec "$CONTAINER" whoami 2>/dev/null || echo unknown)"
if [ "$RUN_USER" != "root" ]; then
    pass "Process runs as $RUN_USER (non-root)"
else
    fail "Process runs as root (V-008)"
fi

# ── Check /etc/shadow is not world-readable ──────────────────────────────────
# If /etc/shadow is world-readable, any process in the container can
# read password hashes and attempt offline cracking.
SHADOW_PERMS="$(docker exec "$CONTAINER" stat -c '%a' /etc/shadow 2>/dev/null || echo 000)"
if [ "${SHADOW_PERMS: -1}" = "0" ]; then
    pass "/etc/shadow not world-readable (perms: $SHADOW_PERMS)"
else
    fail "/etc/shadow is world-readable (perms: $SHADOW_PERMS)"
fi

# ── Check that curl/wget are NOT installed (minimize attack surface) ─────────
# curl and wget inside a production container enable:
# - SSRF from compromised CGI scripts
# - Data exfiltration to attacker-controlled servers
# - Downloading additional payloads post-exploitation
if docker exec "$CONTAINER" which curl >/dev/null 2>&1; then
    fail "curl is installed in production container (remove to reduce attack surface)"
else
    pass "curl not installed in production container"
fi

# ── Check CGI scripts are executable ─────────────────────────────────────────
# lighttpd requires the execute bit on CGI scripts to run them.
CGI_DIR="/opt/hamclock-backend/htdocs/ham/HamClock"
if docker exec "$CONTAINER" test -x "$CGI_DIR/fetchBandConditions.pl" 2>/dev/null; then
    pass "CGI scripts are executable"
else
    fail "CGI scripts are not executable"
fi

# ── Check log directory permissions ──────────────────────────────────────────
# The log directory must be writable by the service account (www-data).
LOG_OWNER="$(docker exec "$CONTAINER" stat -c '%U' /opt/hamclock-backend/logs 2>/dev/null || echo unknown)"
if [ "$LOG_OWNER" = "www-data" ] || [ "$LOG_OWNER" = "root" ]; then
    pass "Log directory owned by $LOG_OWNER"
else
    fail "Log directory owned by unexpected user: $LOG_OWNER"
fi

# ── Check no SUID binaries ──────────────────────────────────────────────────
# SUID binaries run with the file owner's privileges, enabling privilege
# escalation. Minimizing SUID binaries reduces the attack surface.
SUID_COUNT="$(docker exec "$CONTAINER" find / -perm -4000 -type f 2>/dev/null | wc -l)"
if [ "$SUID_COUNT" -le 3 ]; then
    pass "SUID binary count: $SUID_COUNT (acceptable)"
else
    fail "Too many SUID binaries: $SUID_COUNT"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
