#!/usr/bin/env perl
# filter_amsat_active.pl
# Fetches AMSAT status page, finds satellites with status today,
# filters the Celestrak TLE file to matching satellites, and writes
# esats.txt with friendly AMSAT names — replacing build_esats.pl.

use strict;
use warnings;
use LWP::UserAgent;

my $AMSAT_URL = "https://www.amsat.org/status/";
my $TLE_IN    = $ENV{ESATS_TLE_CACHE} // "/opt/hamclock-backend/tle/tles.txt";
my $TLE_OUT   = $ENV{ESATS_OUT}       // "/opt/hamclock-backend/htdocs/ham/HamClock/esats/esats.txt";

# AMSAT name => { tle => Celestrak name, out => friendly output name }
# Only needed when AMSAT and Celestrak names differ.
# 'out' is what gets written to esats.txt.
my %ALIAS = (
    'AO-123'            => { tle => 'ASRTU-1 (AO-123)',      out => 'AO-123'            },
    'AO-73'             => { tle => 'FUNCUBE-1 (AO-73)',      out => 'AO-73'             },
    'AO-7[A]'           => { tle => 'OSCAR 7 (AO-7)',         out => 'AO-7'              },
    'AO-7[B]'           => { tle => 'OSCAR 7 (AO-7)',         out => 'AO-7'              },
    'AO-85'             => { tle => 'FOX-1A (AO-85)',         out => 'AO-85'             },
    'BOTAN APRS'        => { tle => 'BOTAN',                  out => 'BOTAN'             },
    'CatSat'            => { tle => 'CATSAT',                 out => 'CATSAT'            },
    'ISS-DATA'          => { tle => 'ISS (ZARYA)',             out => 'ISS'               },
    'ISS-FM'            => { tle => 'ISS (ZARYA)',             out => 'ISS'               },
    'JO-97'             => { tle => 'JY1SAT (JO-97)',         out => 'JO-97'             },
    'QMR-KWT-2_(RS95S)' => { tle => 'QMR-KWT-2 (RS95S)',     out => 'QMR-KWT-2 (RS95S)' },
    'QO-100_NB'         => { tle => '',                       out => ''                  },
    'RS-44'             => { tle => 'RS-44 & BREEZE-KM R/B',  out => 'RS-44'             },
    'SO-125'            => { tle => 'HADES-ICM',              out => 'SO-125'            },
    'SO-50'             => { tle => 'SAUDISAT 1C (SO-50)',    out => 'SO-50'             },
    'SONATE-2 APRS'     => { tle => 'SONATE-2',               out => 'SONATE-2'          },
);

# --- Fetch AMSAT status page ---
my $ua = LWP::UserAgent->new(timeout => 30);
$ua->agent("fetch-amsat-status/1.0");
my $resp = $ua->get($AMSAT_URL);
die "Failed to fetch AMSAT status: " . $resp->status_line . "\n"
    unless $resp->is_success;

my $html = $resp->decoded_content;

# --- Parse satellite names with status today ---
# %active keys are uppercased Celestrak TLE names
# %active values are the friendly output name to write
my %active;

while ($html =~ m{<tr[^>]*>\s*<td[^>]*>\s*(?:<a[^>]*>)?([^<]+?)(?:</a>)?\s*</td>(.*?)</tr>}gsi) {
    my $sat_name = $1;
    my $cells    = $2;
    $sat_name =~ s/^\s+|\s+$//g;

    # Check only the first 12 td cells (today's columns)
    my @tds;
    while ($cells =~ m{<td([^>]*)>.*?</td>}gsi && @tds < 12) {
        push @tds, $1;
    }

    # Active = any cell with a known status bgcolor
    my $has_status = grep {
        /bgcolor\s*=\s*["']?(#4169E1|orange|yellow|#9900FF)["']?/i
    } @tds;

    next unless $has_status;

    my $uname = uc($sat_name);

    if (exists $ALIAS{$uname} || exists $ALIAS{$sat_name}) {
        # Look up using original or uppercased key
        my $entry = $ALIAS{$uname} // $ALIAS{$sat_name};
        next if !$entry->{tle} || $entry->{tle} eq '';
        # Map Celestrak TLE name -> friendly output name
        $active{uc($entry->{tle})} = $entry->{out};
    } else {
        # No alias — Celestrak name matches AMSAT name, use as-is
        $active{$uname} = $sat_name;
    }
}

my $found = scalar keys %active;
print STDERR "AMSAT active satellites today: $found\n";
if ($found == 0) {
    die "ERROR: No active satellites parsed from AMSAT — aborting to avoid empty output\n";
}

# --- Read and filter TLE file, writing friendly names ---
open my $in, "<", $TLE_IN or die "Cannot open TLE file $TLE_IN: $!\n";
my @lines = <$in>;
close $in;
chomp @lines;

open my $out, ">", $TLE_OUT or die "Cannot write $TLE_OUT: $!\n";

my $i          = 0;
my $written    = 0;
my %seen_norad;

while ($i < @lines) {
    my $name = $lines[$i];
    $name =~ s/\r$//;
    $name =~ s/^\s+|\s+$//g;

    if ($name eq '' || $name =~ /^[12]\s/) { $i++; next; }

    my $l1 = $lines[$i+1] // '';
    my $l2 = $lines[$i+2] // '';
    $l1 =~ s/\r$//;
    $l2 =~ s/\r$//;

    if ($l1 =~ /^1\s/ && $l2 =~ /^2\s/) {
        my ($norad) = $l1 =~ /^1\s+(\d+)/;
        my $key = uc($name);
        $key =~ s/^\s+|\s+$//g;

        if (exists $active{$key} && !$seen_norad{$norad}) {
            my $out_name = $active{$key};
            print $out "$out_name\n$l1\n$l2\n";
            $seen_norad{$norad} = 1;
            $written++;
        }
        $i += 3;
    } else {
        $i++;
    }
}

close $out;
print STDERR "Wrote $written blocks to $TLE_OUT\n";
