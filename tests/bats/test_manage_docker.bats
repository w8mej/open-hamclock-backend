#!/usr/bin/env bats
# =============================================================================
# test_manage_docker.bats — Static analysis of manage-ohb-docker.sh
# =============================================================================
#
# Scope:
#   Validates the security and correctness properties of the Docker
#   management script (docker/manage-ohb-docker.sh) through static
#   analysis.  No Docker commands are executed.
#
# What is Tested:
#   1. File existence — deployment readiness guard.
#   2. Strict mode — set -e must be present.
#   3. Usage output — usage() function must list expected subcommands.
#   4. No hardcoded secrets — password/secret/token assignments must
#      not appear in clear text.
#   5. Docker Compose YAML template — must contain expected fields
#      (image, ports, volumes).
#   6. Default port — the script must define a default HTTP port.
#   7. run.sh exists — the container entrypoint script must be present.
#
# Dependencies:
#   - bats-core
#   - grep (coreutils)
#
# Runner:
#   bats tests/bats/test_manage_docker.bats
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
MANAGE="$ROOT/docker/manage-ohb-docker.sh"

@test "manage-ohb-docker.sh exists" {
    [ -f "$MANAGE" ]
}

@test "manage-ohb-docker.sh has set -e" {
    head -5 "$MANAGE" | grep -q 'set -e'
}

@test "manage-ohb-docker.sh usage() lists expected subcommands" {
    # The usage function must reference key subcommands
    grep -q 'install' "$MANAGE"
    grep -q 'upgrade' "$MANAGE"
    grep -q 'remove' "$MANAGE"
    grep -q 'generate-docker-compose' "$MANAGE"
}

@test "manage-ohb-docker.sh contains no hardcoded secrets" {
    local secrets
    secrets=$(grep -iE '(password|secret|token|apikey)\s*=' "$MANAGE" \
        | grep -v '#' | grep -v 'ENV{' || true)
    [ -z "$secrets" ]
}

@test "manage-ohb-docker.sh YAML template contains image field" {
    grep -q 'image:' "$MANAGE"
}

@test "manage-ohb-docker.sh YAML template contains ports field" {
    grep -q 'ports:' "$MANAGE"
}

@test "manage-ohb-docker.sh YAML template contains volumes field" {
    grep -q 'volumes:' "$MANAGE"
}

@test "manage-ohb-docker.sh defines a default HTTP port" {
    grep -qE 'DEFAULT.*PORT|HTTP_PORT|8080' "$MANAGE"
}

@test "Docker run.sh entrypoint exists" {
    [ -f "$ROOT/docker/run.sh" ]
}
