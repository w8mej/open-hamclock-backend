#!/usr/bin/env bash
set -euo pipefail

TLEDIR="/opt/hamclock-backend/tle"
ARCHIVE="$TLEDIR/archive"
TLEFILE="$TLEDIR/tles.txt"
TMPFILE="$TLEDIR/tles.new"
FILTER_STAMP="$TLEDIR/.amsat_filter_date"
ESATS_OUT="/opt/hamclock-backend/htdocs/ham/HamClock/esats/esats.txt"

FILTER="/opt/hamclock-backend/scripts/filter_amsat_active.pl"

mkdir -p "$TLEDIR" "$ARCHIVE"
mkdir -p "$TLEDIR" "$ARCHIVE" "$(dirname "$ESATS_OUT")"

URLS=(
  "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
  "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle"
  "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
)

ts() { date -u +"%Y%m%dT%H%M%SZ"; }

echo "[$(date -u)] Fetching TLEs..."

: > "$TMPFILE"

for u in "${URLS[@]}"; do
    curl -fsSL "$u" >> "$TMPFILE"
    echo >> "$TMPFILE"
done

# Sanity check
if ! grep -q '^1 ' "$TMPFILE"; then
    echo "ERROR: no TLE records"
    exit 1
fi

# First install
if [ ! -f "$TLEFILE" ]; then
    mv "$TMPFILE" "$TLEFILE"
    cp "$TLEFILE" "$ARCHIVE/tles-$(ts).txt"
    echo "Initial TLE install"
    TODAY=$(date -u +"%Y%m%d")
    echo "[$(ts)] Running AMSAT status filter..."
    if env ESATS_TLE_CACHE="$TLEFILE" ESATS_OUT="$ESATS_OUT" perl "$FILTER"; then
        echo "$TODAY" > "$FILTER_STAMP"
        echo "[$(ts)] AMSAT filter complete — esats.txt updated"
    else
        echo "WARNING: AMSAT filter failed — esats.txt not updated"
    fi
    exit 0
fi

OLDHASH=$(sha256sum "$TLEFILE" | awk '{print $1}')
NEWHASH=$(sha256sum "$TMPFILE" | awk '{print $1}')

if [[ "$OLDHASH" == "$NEWHASH" ]]; then
    rm "$TMPFILE"
    echo "No TLE change"
else
    STAMP="$(ts)"

    # Archive old + new
    cp "$TLEFILE" "$ARCHIVE/tles-${STAMP}-old.txt"
    cp "$TMPFILE" "$ARCHIVE/tles-${STAMP}-new.txt"

    # Atomic replace
    mv "$TMPFILE" "$TLEFILE"

    echo "TLE updated ($STAMP)"

    # Keep last 60 snapshots (~15 days at 6h cadence)
    ls -1t "$ARCHIVE"/tles-* 2>/dev/null | tail -n +61 | xargs -r rm --
fi

# Run AMSAT filter once per UTC day, or if esats.txt is missing
TODAY=$(date -u +"%Y%m%d")
LAST_FILTER=$(cat "$FILTER_STAMP" 2>/dev/null || echo "")

if [[ "$LAST_FILTER" != "$TODAY" ]] || [[ ! -f "$ESATS_OUT" ]]; then
    echo "[$(ts)] Running AMSAT status filter..."
    if env ESATS_TLE_CACHE="$TLEFILE" ESATS_OUT="$ESATS_OUT" perl "$FILTER"; then
        echo "$TODAY" > "$FILTER_STAMP"
        echo "[$(ts)] AMSAT filter complete — esats.txt updated"
    else
        echo "WARNING: AMSAT filter failed — esats.txt not updated"
    fi
else
    echo "[$(ts)] AMSAT filter already ran today — skipping"
fi
