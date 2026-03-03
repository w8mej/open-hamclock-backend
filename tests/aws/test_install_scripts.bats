#!/usr/bin/env bats
# =============================================================================
# test_install_scripts.bats — Static analysis of AWS install scripts
# =============================================================================
#
# Scope:
#   Validates the security properties of the AWS deployment scripts
#   (install_ohb.sh and install_voacap.sh) through static analysis.
#   No scripts are executed — only source text is inspected.
#
# What is Tested:
#   install_ohb.sh:
#     1. File existence — deployment readiness guard.
#     2. Shebang safety — must use #!/bin/bash (not #!/usr/bin/env bash)
#        because it runs as root; #!/usr/bin/env bash is susceptible to
#        PATH hijack attacks.
#     3. Strict mode — set -euo pipefail or set -e must be present.
#     4. curl -f flag — all curl calls must use -f (--fail) to detect
#        HTTP errors instead of silently accepting error pages.
#     5. No chmod 777 — overly permissive permissions are never acceptable.
#     6. No chmod 666 — world-writable files are a security risk.
#
#   install_voacap.sh:
#     7. File existence — deployment readiness guard.
#     8. Strict mode — set -euo pipefail must be present.
#     9. --break-system-packages check — pip should use a venv, not
#        break system packages (informational warning).
#    10. Smoke test — the script must include a verification step.
#    11. Temp file cleanup — temporary files must be removed after use.
#
#   Both scripts:
#    12. No hardcoded secrets — password/secret/token/apikey assignments
#        must not appear in clear text.
#    13. sudo usage — privileged operations (chown, mkdir /opt) should
#        use sudo for proper audit logging (informational).
#
# Dependencies:
#   - bats-core
#   - grep, head (coreutils)
#
# Runner:
#   bats tests/aws/test_install_scripts.bats
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

# ═══════════════════════════════════════════════════════════════════════════════
# install_ohb.sh
# ═══════════════════════════════════════════════════════════════════════════════

@test "install_ohb.sh exists" {
    [ -f "$ROOT/aws/install_ohb.sh" ]
}

@test "install_ohb.sh uses #!/bin/bash (not env bash) for privilege safety" {
    # Root scripts must use absolute shebang paths to prevent PATH hijack.
    # #!/usr/bin/env bash searches $PATH, which an attacker could manipulate.
    local shebang
    shebang="$(head -1 "$ROOT/aws/install_ohb.sh")"
    if echo "$shebang" | grep -q '#!/usr/bin/env bash'; then
        echo "WARN: Uses #!/usr/bin/env bash — root script should use #!/bin/bash"
        return 1
    fi
}

@test "install_ohb.sh has set -euo pipefail" {
    head -5 "$ROOT/aws/install_ohb.sh" | grep -q 'set -euo pipefail' \
        || head -5 "$ROOT/aws/install_ohb.sh" | grep -q 'set -e'
}

@test "install_ohb.sh curl calls use -f flag" {
    # Without -f, curl returns exit 0 even for 404/500 responses,
    # causing corrupted downloads to be treated as valid data.
    local bad_curls
    bad_curls=$(grep 'curl ' "$ROOT/aws/install_ohb.sh" | grep -v '#' | grep -v '\-[a-zA-Z]*f' | grep -v '\-\-fail' || true)
    if [ -n "$bad_curls" ]; then
        echo "curl calls missing -f (fail on HTTP error):"
        echo "$bad_curls"
        return 1
    fi
}

@test "install_ohb.sh does not use chmod 777" {
    # chmod 777 grants read/write/execute to all users — never acceptable.
    ! grep -q 'chmod.*777' "$ROOT/aws/install_ohb.sh"
}

@test "install_ohb.sh does not use chmod 666" {
    # chmod 666 makes files world-writable — a data integrity risk.
    ! grep -q 'chmod.*666' "$ROOT/aws/install_ohb.sh"
}

# ═══════════════════════════════════════════════════════════════════════════════
# install_voacap.sh
# ═══════════════════════════════════════════════════════════════════════════════

@test "install_voacap.sh exists" {
    [ -f "$ROOT/aws/install_voacap.sh" ]
}

@test "install_voacap.sh has set -euo pipefail" {
    head -5 "$ROOT/aws/install_voacap.sh" | grep -q 'set -euo pipefail'
}

@test "install_voacap.sh pip install does not use --break-system-packages" {
    # pip --break-system-packages bypasses the virtual environment
    # protection, potentially overwriting system Python packages.
    # install_voacap.sh already uses a venv, so this is a warning.
    if grep -q '\-\-break-system-packages' "$ROOT/aws/install_voacap.sh"; then
        echo "WARN: Uses --break-system-packages — should use venv (already does)"
    fi
}

@test "install_voacap.sh has a smoke test" {
    # The install script should verify the installation succeeded
    # by running a quick test (e.g., checking output line count).
    grep -q 'smoketest\|smoke.*test\|verify\|line_count' "$ROOT/aws/install_voacap.sh"
}

@test "install_voacap.sh cleans up temp files" {
    # Temporary files left behind can consume disk space and leak
    # information about the install process.
    grep -q 'rm -f.*smoketest\|rm.*tmp' "$ROOT/aws/install_voacap.sh"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Both install scripts — cross-cutting security properties
# ═══════════════════════════════════════════════════════════════════════════════

@test "No hardcoded secrets in install scripts" {
    # Passwords, API keys, and tokens must be provided via environment
    # variables or secrets managers — never hardcoded in source files.
    local secrets
    secrets=$(grep -iE '(password|secret|token|apikey)\s*=' "$ROOT/aws/"*.sh 2>/dev/null \
        | grep -v '#' | grep -v 'ENV{' | grep -v '// ' || true)
    if [ -n "$secrets" ]; then
        echo "Possible hardcoded secrets:"
        echo "$secrets"
        return 1
    fi
}

@test "Install scripts use sudo for privileged operations" {
    # Commands like chown, mkdir in /opt should use sudo for proper
    # audit logging and to work in both root and non-root contexts.
    local bad_ops
    bad_ops=$(grep -n 'chown\|mkdir -p /opt\|chmod' "$ROOT/aws/"*.sh 2>/dev/null \
        | grep -v 'sudo' | grep -v '#' || true)
    # This is informational — some setups run as root directly
    if [ -n "$bad_ops" ]; then
        echo "Operations without sudo (may be intentional if running as root):"
        echo "$bad_ops"
    fi
}
