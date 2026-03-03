#!/usr/bin/env bats
# =============================================================================
# test_lighttpd_config.bats — Static analysis of lighttpd configuration
# =============================================================================
#
# Scope:
#   Validates the lighttpd configuration files used by the OHB container
#   through text analysis.  No lighttpd process is started.
#
# What is Tested:
#   1. Config file existence — all expected .conf files are present.
#   2. Security headers — OWASP recommended headers are configured.
#   3. No version leak — server.tag must not reveal lighttpd version.
#   4. No wildcard CORS — Access-Control-Allow-Origin: * must not appear.
#   5. CGI cache prevention — CGI responses must set no-store/no-cache.
#   6. No server-side includes — SSI module must not be enabled.
#
# Dependencies:
#   - bats-core
#   - grep (coreutils)
#
# Runner:
#   bats tests/bats/test_lighttpd_config.bats
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
CONF_DIR="$ROOT/lighttpd-conf"
SECURITY_CONF="$CONF_DIR/99-security-headers.conf"

@test "Security headers config exists" {
    [ -f "$SECURITY_CONF" ]
}

@test "X-Frame-Options is configured" {
    grep -q 'X-Frame-Options' "$SECURITY_CONF"
}

@test "X-Content-Type-Options is configured" {
    grep -q 'X-Content-Type-Options' "$SECURITY_CONF"
}

@test "Content-Security-Policy is configured" {
    grep -q 'Content-Security-Policy' "$SECURITY_CONF"
}

@test "Referrer-Policy is configured" {
    grep -q 'Referrer-Policy' "$SECURITY_CONF"
}

@test "Strict-Transport-Security is configured" {
    grep -q 'Strict-Transport-Security' "$SECURITY_CONF"
}

@test "Permissions-Policy is configured" {
    grep -q 'Permissions-Policy' "$SECURITY_CONF"
}

@test "server.tag does not leak lighttpd version" {
    # server.tag should be set to a generic string, not include version
    local tag_line
    tag_line=$(grep 'server.tag' "$SECURITY_CONF" || true)
    if [ -n "$tag_line" ]; then
        # Must not contain a version pattern like lighttpd/1.4.76
        ! echo "$tag_line" | grep -qE 'lighttpd/[0-9]'
    fi
}

@test "No wildcard CORS in security headers" {
    ! grep -q 'Access-Control-Allow-Origin.*\*' "$SECURITY_CONF"
}

@test "CGI responses disable caching" {
    grep -q 'no-store' "$SECURITY_CONF"
    grep -q 'no-cache' "$SECURITY_CONF"
}

@test "No lighttpd config files enable mod_ssi" {
    # SSI (Server Side Includes) is a security risk
    ! grep -rq 'mod_ssi' "$CONF_DIR/"*.conf 2>/dev/null
}
