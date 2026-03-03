#!/usr/bin/env perl
# =============================================================================
# cgi_input_validation.t — Test CGI input validation patterns from all Perl CGI scripts
# =============================================================================
#
# Scope:
#   Validates the input-validation functions used across four CGI scripts:
#   fetchWSPR.pl, fetchPSKReporter.pl, fetchRBN.pl, fetchBandConditions.pl,
#   and tail.pl.  Validation functions are extracted and tested in isolation
#   without starting a web server or executing CGI.
#
# What is Tested:
#   1. Maidenhead Grid Validation — 4/6-char grid locators (FN31, RR99XX)
#      accepted; out-of-range, wrong-length, lowercase, and SQL injection
#      payloads rejected.
#   2. Callsign Validation — alphanumeric + / + - accepted (W1AW, VE3/W1AW);
#      command injection and quote injection rejected.
#   3. Numeric Parameter Validation — year (4 digits), month (1-12),
#      coordinate (decimal with optional sign); injection payloads rejected.
#   4. File Parameter Allowlisting — only pre-approved log names accepted;
#      path traversal, absolute paths, and command injection rejected.
#   5. Maxage Clamping — values below 60 clamped up, above 86400 clamped
#      down, non-numeric defaults to 900, embedded injection stripped.
#
# Dependencies:
#   - perl 5.x
#   - Test::More (core module)
#
# Runner:
#   prove -v tests/perl/cgi_input_validation.t
#
# See Also:
#   tests/TEST_README.md — Tier 4 (Perl Unit Tests)
# =============================================================================
use strict;
use warnings;
use Test::More;

# ═══════════════════════════════════════════════════════════════════════════════
# Maidenhead grid validation (fetchWSPR.pl, fetchPSKReporter.pl)
#
# Maidenhead Locator System: 2 uppercase letters (A-R) + 2 digits (0-9),
# optionally followed by 2 uppercase letters (A-X) for 6-character precision.
# Reference: https://en.wikipedia.org/wiki/Maidenhead_Locator_System
# ═══════════════════════════════════════════════════════════════════════════════

sub valid_maidenhead {
    my ($grid) = @_;
    return 0 unless defined $grid && $grid ne '';
    return ($grid =~ /^[A-R]{2}[0-9]{2}([A-X]{2})?$/) ? 1 : 0;
}

# Valid grids
ok(valid_maidenhead("FN31"),     "FN31 is valid 4-char Maidenhead");
ok(valid_maidenhead("FN31PR"),   "FN31PR is valid 6-char Maidenhead");
ok(valid_maidenhead("AA00"),     "AA00 is valid");
ok(valid_maidenhead("RR99XX"),   "RR99XX is valid (boundary)");

# Invalid grids
ok(!valid_maidenhead(""),         "Empty string rejected");
ok(!valid_maidenhead("ZZ99"),     "ZZ99 invalid (Z > R)");
ok(!valid_maidenhead("FN31PR00"), "8-char grid rejected");
ok(!valid_maidenhead("fn31"),     "Lowercase rejected (must UC first)");
ok(!valid_maidenhead("FN3"),      "3-char rejected");
ok(!valid_maidenhead("FN310"),    "5-char rejected");

# SQL injection attempts — these must never reach a database query
ok(!valid_maidenhead("FN31' OR '1'='1"), "SQL injection rejected");
ok(!valid_maidenhead("FN31; DROP TABLE"), "SQL drop rejected");
ok(!valid_maidenhead("FN31%"),            "Wildcard rejected");

# ═══════════════════════════════════════════════════════════════════════════════
# Callsign validation (fetchRBN.pl)
#
# Amateur radio callsigns consist of alphanumeric characters, optional
# "/" for portable designators, and optional "-" for SSID suffixes.
# ═══════════════════════════════════════════════════════════════════════════════

sub valid_callsign {
    my ($call) = @_;
    return 0 unless defined $call && $call ne '';
    return ($call =~ /^[A-Za-z0-9\/\-]+$/) ? 1 : 0;
}

ok(valid_callsign("W1AW"),        "W1AW is valid callsign");
ok(valid_callsign("VE3/W1AW"),    "VE3/W1AW valid (portable)");
ok(valid_callsign("W1AW-1"),      "W1AW-1 valid (SSID)");
ok(!valid_callsign("W1AW; rm -rf /"), "Command injection rejected");
ok(!valid_callsign("W1AW'"),          "Quote injection rejected");

# ═══════════════════════════════════════════════════════════════════════════════
# Numeric parameter validation (fetchBandConditions.pl)
#
# These validators enforce strict numeric formats to prevent injection
# through CGI query parameters.
# ═══════════════════════════════════════════════════════════════════════════════

sub valid_year {
    my ($y) = @_;
    return ($y =~ /^\d{4}$/) ? 1 : 0;
}

sub valid_month {
    my ($m) = @_;
    return ($m =~ /^\d{1,2}$/ && $m >= 1 && $m <= 12) ? 1 : 0;
}

sub valid_coordinate {
    my ($c) = @_;
    return ($c =~ /^-?\d+(\.\d+)?$/) ? 1 : 0;
}

ok(valid_year("2026"),  "2026 is valid year");
ok(!valid_year("26"),   "2-digit year rejected");
ok(!valid_year("abcd"), "Alpha year rejected");

ok(valid_month("1"),  "Month 1 valid");
ok(valid_month("12"), "Month 12 valid");
ok(!valid_month("0"),  "Month 0 rejected");
ok(!valid_month("13"), "Month 13 rejected");

ok(valid_coordinate("28.5"),    "28.5 valid coordinate");
ok(valid_coordinate("-81.0"),   "-81.0 valid coordinate");
ok(valid_coordinate("0"),       "0 valid coordinate");
ok(!valid_coordinate("28.5; rm -rf /"), "Command in coordinate rejected");
ok(!valid_coordinate("../../etc/passwd"), "Path traversal in coordinate rejected");

# ═══════════════════════════════════════════════════════════════════════════════
# File parameter allowlisting (tail.pl)
#
# tail.pl maps symbolic names to absolute log-file paths.  Only names in
# the allowlist hash are accepted — all other inputs (including path
# traversal, absolute paths, and command injection) are rejected.
# ═══════════════════════════════════════════════════════════════════════════════

my %ALLOWED_FILES = (
    'lighttpd_error'  => '/opt/hamclock-backend/logs/lighttpd_error.log',
    'lighttpd_access' => '/opt/hamclock-backend/logs/lighttpd_access.log',
    'cron'            => '/opt/hamclock-backend/logs/cron.log',
);

sub valid_tail_file {
    my ($file_param) = @_;
    return exists $ALLOWED_FILES{$file_param} ? 1 : 0;
}

ok(valid_tail_file("lighttpd_error"),  "Allowed file accepted");
ok(valid_tail_file("cron"),            "Cron log accepted");
ok(!valid_tail_file("../../../etc/passwd"), "Path traversal rejected");
ok(!valid_tail_file("/etc/shadow"),         "Absolute path rejected");
ok(!valid_tail_file("lighttpd_error; ls"),  "Command injection rejected");
ok(!valid_tail_file(""),                    "Empty string rejected");

# ═══════════════════════════════════════════════════════════════════════════════
# Maxage clamping (fetchWSPR.pl, fetchPSKReporter.pl)
#
# The maxage parameter controls how far back to query historical data.
# It is sanitized by stripping non-digits, defaulting to 900 seconds,
# and clamping to the [60, 86400] range (1 minute to 24 hours).
# ═══════════════════════════════════════════════════════════════════════════════

sub clamp_maxage {
    my ($val) = @_;
    $val =~ s/\D//g;
    $val = int($val || 900);
    $val = 60    if $val < 60;
    $val = 86400 if $val > 86400;
    return $val;
}

is(clamp_maxage("900"),          900,   "Normal maxage passes through");
is(clamp_maxage("30"),           60,    "Below minimum clamped to 60");
is(clamp_maxage("999999999"),    86400, "Huge value clamped to 86400");
is(clamp_maxage("abc"),          900,   "Non-numeric defaults to 900");
is(clamp_maxage("100; rm -rf"), 100,   "Injection stripped, numeric kept");

done_testing();
