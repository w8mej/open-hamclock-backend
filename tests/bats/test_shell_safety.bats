#!/usr/bin/env bats
# =============================================================================
# test_shell_safety.bats — Verify all shell scripts follow security best practices
# =============================================================================
#
# Scope:
#   Enforces security coding standards across all shell scripts in
#   scripts/, docker/, and aws/ by statically analyzing source files.
#   No scripts are executed — only their source text is inspected.
#
# What is Tested:
#   1. ShellCheck compliance — all .sh files pass ShellCheck at severity
#      level 'warning' (with SC2034 suppressed for exported variables).
#   2. Strict mode — every script must have `set -euo pipefail` or at
#      minimum `set -e` within the first 10 lines.
#   3. Shebang safety — privileged scripts (aws/install_*.sh) must use
#      #!/bin/bash, not #!/usr/bin/env bash, to prevent PATH hijack
#      attacks when running as root.
#   4. No /tmp lock files — flock files in /tmp/ are world-accessible;
#      use application-specific directories instead.
#   5. No backtick subshells — prefer $() for command substitution to
#      avoid nesting issues and improve readability.
#   6. curl -f enforcement — all curl invocations must include -f (or
#      --fail) to detect HTTP errors instead of silently accepting
#      error pages as valid responses.
#
# Dependencies:
#   - bats-core
#   - shellcheck (optional; test skipped if not installed)
#   - grep, find (coreutils)
#
# Runner:
#   bats tests/bats/test_shell_safety.bats
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

# ── ShellCheck ────────────────────────────────────────────────────────────────

@test "All shell scripts pass ShellCheck (severity: warning)" {
    if ! command -v shellcheck &>/dev/null; then
        skip "shellcheck not installed"
    fi
    find "$ROOT/scripts" "$ROOT/docker" "$ROOT/aws" -name '*.sh' \
        -exec shellcheck -e SC2034 -S warning {} +
}

# ── Strict mode ───────────────────────────────────────────────────────────────

@test "All shell scripts have set -euo pipefail or set -e" {
    # `set -e` causes the script to exit immediately on any command failure,
    # preventing cascading errors and silent data corruption. `set -uo pipefail`
    # additionally catches unset variables and pipeline failures.
    local failures=()
    while IFS= read -r f; do
        if ! head -10 "$f" | grep -qE 'set -e|set -euo'; then
            failures+=("$f")
        fi
    done < <(find "$ROOT/scripts" "$ROOT/docker" "$ROOT/aws" -name '*.sh' -not -name 'env-gen.sh')

    if [ ${#failures[@]} -gt 0 ]; then
        echo "Scripts missing strict mode:"
        printf '  %s\n' "${failures[@]}"
        return 1
    fi
}

# ── No #!/usr/bin/env bash in privileged scripts ─────────────────────────────

@test "Privileged scripts use #!/bin/bash, not #!/usr/bin/env bash" {
    # When running as root, #!/usr/bin/env bash searches $PATH for bash,
    # which could be hijacked by placing a malicious binary earlier in PATH.
    # #!/bin/bash uses an absolute path, immune to PATH manipulation.
    local failures=()
    for f in "$ROOT/aws/install_ohb.sh" "$ROOT/aws/install_voacap.sh"; do
        [ -f "$f" ] || continue
        if head -1 "$f" | grep -q '#!/usr/bin/env bash'; then
            failures+=("$f")
        fi
    done

    if [ ${#failures[@]} -gt 0 ]; then
        echo "Privileged scripts using #!/usr/bin/env bash (PATH hijack risk):"
        printf '  %s\n' "${failures[@]}"
        return 1
    fi
}

# ── No /tmp lock files ───────────────────────────────────────────────────────

@test "No flock files in /tmp (use application dirs instead)" {
    # /tmp is world-writable (mode 1777). Lock files there are vulnerable
    # to symlink attacks and race conditions. Use /opt/hamclock-backend/tmp.
    local count
    count=$(grep -rE '(^|[[:space:]])/tmp/.*\.lock' "$ROOT/scripts" "$ROOT/docker" 2>/dev/null | wc -l)
    [ "$count" -eq 0 ]
}

# ── No bare backtick execution in shell scripts ──────────────────────────────

@test "No bash backtick subshells (use \$() instead)" {
    # Backtick command substitution (`cmd`) is harder to nest and debug
    # compared to $(cmd). Modern Bash style guides recommend $() exclusively.
    local count
    count=$(grep -rn '`[^`]*`' "$ROOT/scripts/"*.sh "$ROOT/docker/"*.sh "$ROOT/aws/"*.sh 2>/dev/null | \
        grep -v '#' | grep -v '.bats' | wc -l)
    [ "$count" -eq 0 ]
}

# ── curl uses -f (fail on HTTP errors) ───────────────────────────────────────

@test "All curl calls use -f or --fail flag" {
    # Without -f, curl considers any HTTP response (including 404, 500)
    # as success (exit 0). This can silently download error pages in place
    # of expected data, corrupting caches or configurations.
    local failures=()
    while IFS= read -r line; do
        if ! echo "$line" | grep -qE '\-[a-zA-Z]*f|--fail'; then
            failures+=("$line")
        fi
    done < <(grep -rnE '(^|[[:space:]])curl[[:space:]]' "$ROOT/scripts/"*.sh "$ROOT/docker/"*.sh "$ROOT/aws/"*.sh 2>/dev/null | \
        grep -v '#.*curl' | grep -vE 'jq curl perl|apt.*install' | grep -v '.bats')

    if [ ${#failures[@]} -gt 0 ]; then
        echo "curl calls missing -f flag:"
        printf '  %s\n' "${failures[@]}"
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# .env.example validation
# ═══════════════════════════════════════════════════════════════════════════════

@test ".env.example exists" {
    [ -f "$ROOT/.env.example" ]
}

@test ".env.example contains no real secrets" {
    # Values should be placeholders like <insert key here>, not actual keys
    local real_secrets
    real_secrets=$(grep -E '^[A-Z_]+=.+$' "$ROOT/.env.example" \
        | grep -v '<' | grep -v 'example' | grep -v 'placeholder' \
        | grep -v '#' || true)
    [ -z "$real_secrets" ]
}

@test ".env is in .gitignore" {
    grep -q '^\.env$' "$ROOT/.gitignore" || grep -q '\.env' "$ROOT/.gitignore"
}
