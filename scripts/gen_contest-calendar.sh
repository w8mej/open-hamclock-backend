#!/bin/bash
set -e


URL="https://contestcalendar.com/weeklycontcustom.php"
OUTPUT_FILE="/opt/hamclock-backend/htdocs/ham/HamClock/contests/contests311.txt"

# Start by writing the header to the file (overwrites existing content)
echo "WA7BNM Weekend Contests" > "$OUTPUT_FILE"

# Process the data and append to the file
curl -sf "$URL" | tr -d '\r' | awk '
  /^BEGIN:VEVENT/ {printf "EVENT|"}
  /^DTSTART:/ {split($0, a, ":"); printf "%s|", a[2]}
  /^DTEND:/   {split($0, a, ":"); printf "%s|", a[2]}
  /^SUMMARY:/ {printf "%s|", substr($0, 9)}
  /^URL:/     {printf "%s\n", substr($0, 5)}
' | while IFS="|" read -r marker start_raw end_raw title url; do

    # Skip empty lines
    [[ -z "$start_raw" ]] && continue

    # Clean the title of any leading/trailing whitespace
    title=$(echo "$title" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    # Convert timestamps to Epoch and Day of Week
    # Format: YYYYMMDDTHHMMSSZ
    Y=${start_raw:0:4}; M=${start_raw:4:2}; D=${start_raw:6:2}
    H=${start_raw:9:2}; Min=${start_raw:11:2}; S=${start_raw:13:2}

    Y2=${end_raw:0:4}; M2=${end_raw:4:2}; D2=${end_raw:6:2}
    H2=${end_raw:9:2}; Min2=${end_raw:11:2}; S2=${end_raw:13:2}

    start_epoch=$(date -u -d "$Y-$M-$D $H:$Min:$S" +%s 2>/dev/null)
    end_epoch=$(date -u -d "$Y2-$M2-$D2 $H2:$Min2:$S2" +%s 2>/dev/null)
    dow=$(date -u -d "$Y-$M-$D $H:$Min:$S" +%w 2>/dev/null)

    # Filter for Saturday (6) or Sunday (0)
    if [[ "$dow" == "0" || "$dow" == "6" ]]; then
        # Append formatted lines to the file
        printf "%s %s %s\n" "$start_epoch" "$end_epoch" "$title" >> "$OUTPUT_FILE"
        printf "%s\n" "$url" >> "$OUTPUT_FILE"
    fi
done