#!/usr/bin/env perl
# =============================================================================
# fetchBandConditions.t — Test input validation for fetchBandConditions.pl
# =============================================================================
#
# Scope:
#   Validates the parameter-validation logic used by the band-conditions
#   CGI endpoint (fetchBandConditions.pl), which accepts geolocation
#   coordinates, date/time, and computes HF propagation predictions.
#
# What is Tested:
#   1. Valid parameters — a fully-specified request (year, month, UTC,
#      TX/RX coordinates) produces zero validation errors.
#   2. Boundary values — edge cases (month=1, UTC=0, lat=±90, lng=±180,
#      zero coordinates) are accepted.
#   3. Missing parameters — omitting all or most parameters produces the
#      correct count of missing-field errors (7 for all, 6 for year-only).
#   4. Invalid types — alphabetic strings in numeric fields are all rejected.
#   5. Out-of-range values — month=0, month=13, UTC=24 are caught.
#   6. Injection attempts — command injection in YEAR and path traversal
#      in TXLAT are rejected by the numeric-format regex.
#
# Design Pattern:
#   The validate_params() function replicates the validation logic from
#   the production fetchBandConditions.pl script without requiring a
#   running web server or CGI execution environment.
#
# Dependencies:
#   - perl 5.x
#   - Test::More (core module)
#
# Runner:
#   prove -v tests/perl/fetchBandConditions.t
#
# See Also:
#   tests/TEST_README.md — Tier 4 (Perl Unit Tests)
# =============================================================================
use strict;
use warnings;
use Test::More;

# ═══════════════════════════════════════════════════════════════════════════════
# Parameter validation extracted from fetchBandConditions.pl
#
# Each parameter has a specific format:
#   YEAR  — exactly 4 digits (e.g., "2026")
#   MONTH — 1-2 digits, value in [1, 12]
#   UTC   — 1-2 digits, value in [0, 23]
#   TXLAT/TXLNG/RXLAT/RXLNG — decimal number with optional sign
# ═══════════════════════════════════════════════════════════════════════════════

sub validate_params {
    my (%p) = @_;
    my @missing;
    push @missing, 'YEAR'  unless ($p{year}  // '') =~ /^\d{4}$/;
    push @missing, 'MONTH' unless ($p{month} // '') =~ /^\d{1,2}$/ && ($p{month}//0) >= 1 && ($p{month}//0) <= 12;
    push @missing, 'UTC'   unless ($p{utc}   // '') =~ /^\d{1,2}$/ && ($p{utc}//0)   >= 0 && ($p{utc}//0)   <= 23;
    push @missing, 'TXLAT' unless ($p{txlat} // '') =~ /^-?\d+(\.\d+)?$/;
    push @missing, 'TXLNG' unless ($p{txlng} // '') =~ /^-?\d+(\.\d+)?$/;
    push @missing, 'RXLAT' unless ($p{rxlat} // '') =~ /^-?\d+(\.\d+)?$/;
    push @missing, 'RXLNG' unless ($p{rxlng} // '') =~ /^-?\d+(\.\d+)?$/;
    return @missing;
}

# ── Valid parameters ──────────────────────────────────────────────────────────
# A fully-specified request with realistic values should produce no errors.

my @missing = validate_params(
    year => '2026', month => '6', utc => '17',
    txlat => '28.0', txlng => '-81.0',
    rxlat => '42.5', rxlng => '-114.4',
);
is(scalar @missing, 0, "Valid params produce no errors");

# ── Boundary values ──────────────────────────────────────────────────────────
# Test the edges of valid ranges to ensure off-by-one errors are absent.

@missing = validate_params(
    year => '2026', month => '1', utc => '0',
    txlat => '-90', txlng => '-180',
    rxlat => '90', rxlng => '180',
);
is(scalar @missing, 0, "Boundary values are valid");

@missing = validate_params(
    year => '2026', month => '12', utc => '23',
    txlat => '0', txlng => '0',
    rxlat => '0', rxlng => '0',
);
is(scalar @missing, 0, "Zero coordinates valid");

# ── Missing parameters ───────────────────────────────────────────────────────
# validate_params should return one error per missing field.

@missing = validate_params();
is(scalar @missing, 7, "All params missing = 7 errors");

@missing = validate_params(year => '2026');
is(scalar @missing, 6, "Only year = 6 missing");

# ── Invalid types ─────────────────────────────────────────────────────────────
# Alphabetic strings in every numeric field should all be rejected.

@missing = validate_params(
    year => 'abc', month => 'jan', utc => 'noon',
    txlat => 'north', txlng => 'west',
    rxlat => 'south', rxlng => 'east',
);
is(scalar @missing, 7, "Alphabetic params all rejected");

# ── Out of range ──────────────────────────────────────────────────────────────
# Values that match the numeric format but exceed valid bounds.

@missing = validate_params(
    year => '2026', month => '0', utc => '17',
    txlat => '28', txlng => '-81',
    rxlat => '42', rxlng => '-114',
);
ok(grep(/MONTH/, @missing), "Month 0 rejected");

@missing = validate_params(
    year => '2026', month => '13', utc => '17',
    txlat => '28', txlng => '-81',
    rxlat => '42', rxlng => '-114',
);
ok(grep(/MONTH/, @missing), "Month 13 rejected");

@missing = validate_params(
    year => '2026', month => '6', utc => '24',
    txlat => '28', txlng => '-81',
    rxlat => '42', rxlng => '-114',
);
ok(grep(/UTC/, @missing), "UTC 24 rejected");

# ── Injection attempts ───────────────────────────────────────────────────────
# Command injection and path traversal payloads in numeric fields must
# fail the regex validation and appear in the @missing list.

@missing = validate_params(
    year => '2026; rm -rf /', month => '6', utc => '17',
    txlat => '28', txlng => '-81',
    rxlat => '42', rxlng => '-114',
);
ok(grep(/YEAR/, @missing), "Command injection in YEAR rejected");

@missing = validate_params(
    year => '2026', month => '6', utc => '17',
    txlat => '28/../../../etc/passwd', txlng => '-81',
    rxlat => '42', rxlng => '-114',
);
ok(grep(/TXLAT/, @missing), "Path traversal in TXLAT rejected");

done_testing();
