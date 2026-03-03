#!/usr/bin/env bats
# =============================================================================
# test_crontab.bats — Verify crontab security properties
# =============================================================================
#
# Scope:
#   Validates that the project's crontab file (scripts/crontab) follows
#   security best practices for scheduled-task configuration.
#
# What is Tested:
#   1. File existence — confirms the crontab file is present in the repo.
#   2. No /tmp usage — cron jobs must not write lock files or temp data to
#      /tmp (world-writable, symlink-attack risk). Use the application's
#      own tmp/ directory instead.
#   3. PATH ordering — system directories (/usr/bin, /bin) must appear
#      before venv/bin in the crontab PATH to prevent PATH-hijack attacks
#      when cron runs as www-data.
#   4. Log directory — all cron output redirections (>>) must target
#      /opt/hamclock-backend/logs/ (or $BASE/logs) for centralized
#      log management.
#
# Dependencies:
#   - bats-core (Bash Automated Testing System)
#   - The file scripts/crontab must exist in the repository root
#
# Runner:
#   bats tests/bats/test_crontab.bats
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
CRONTAB="$ROOT/scripts/crontab"

@test "Crontab file exists" {
    [ -f "$CRONTAB" ]
}

@test "No lock files in /tmp" {
    # /tmp is world-writable and susceptible to symlink attacks.
    # All temporary files should use /opt/hamclock-backend/tmp instead.
    local count
    count=$(grep -cE '(^|[[:space:]])/tmp/' "$CRONTAB" 2>/dev/null || echo 0)
    if [ "$count" -gt 0 ]; then
        echo "Found /tmp references in crontab (use /opt/hamclock-backend/tmp instead):"
        grep -E '(^|[[:space:]])/tmp/' "$CRONTAB"
        return 1
    fi
}

@test "PATH puts system directories before venv" {
    # If the crontab defines a PATH variable, system directories (/usr/bin,
    # /bin) must appear before /opt/hamclock-backend/venv/bin to prevent
    # a compromised venv from shadowing critical system binaries.
    local path_line
    path_line=$(grep '^PATH=' "$CRONTAB" || true)

    if [ -z "$path_line" ]; then
        skip "No PATH variable in crontab"
    fi

    # Extract the first entry in PATH
    local first_dir
    first_dir=$(echo "$path_line" | sed 's/^PATH=//' | cut -d: -f1)

    # System dirs should come before /opt/hamclock-backend/venv/bin
    if echo "$first_dir" | grep -q 'venv'; then
        echo "PATH starts with venv — should start with system dirs"
        echo "Current: $path_line"
        return 1
    fi
}

@test "All cron log files go to /opt/hamclock-backend/logs" {
    # Centralized logging ensures log rotation, monitoring, and access
    # control are applied uniformly.
    bad_logs=$(grep '>>' "$CRONTAB" | grep -vE '/opt/hamclock-backend/logs|\$BASE/logs' | grep -v '^#' || true)

    if [ -n "$bad_logs" ]; then
        echo "Cron output redirects to non-standard locations:"
        echo "$bad_logs"
        return 1
    fi
}
