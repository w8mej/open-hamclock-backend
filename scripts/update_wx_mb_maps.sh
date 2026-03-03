#!/usr/bin/env bash
set -e

# update_wx_mb_maps.sh
#
# Generates HamClock Wx-mB maps in multiple sizes using a GMT-generated black/white
# base (not Countries.bmp.z), then overlays weather via Python renderer.
#
# Composition order:
#   1) Build neutral GMT base (same geometry for D/N)
#   2) Render weather (temp/isobars/wind) on top

set -euo pipefail
export LC_ALL=C

export GMT_USERDIR=/opt/hamclock-backend/tmp
cd "$GMT_USERDIR"

OUTDIR="/opt/hamclock-backend/htdocs/ham/HamClock/maps"
TMPROOT="/opt/hamclock-backend/tmp"
export MPLCONFIGDIR="$TMPROOT/mpl"

RENDER_PY="/opt/hamclock-backend/scripts/render_wx_mb_map.py"
RAW2BMP_PY="/opt/hamclock-backend/scripts/hc_raw_to_bmp565.py"
PYTHON_BIN="/opt/hamclock-backend/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="/usr/bin/python3"
fi

# Load unified size list
# shellcheck source=/dev/null
source "/opt/hamclock-backend/scripts/lib_sizes.sh"
ohb_load_sizes

NOMADS_FILTER="https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
export PYTHONPATH="/opt/hamclock-backend/scripts${PYTHONPATH:+:$PYTHONPATH}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }

need curl
need gmt
need convert

[[ -x "$PYTHON_BIN" ]] || { echo "ERROR: missing executable $PYTHON_BIN" >&2; exit 1; }
[[ -f "$RENDER_PY" ]]  || { echo "ERROR: missing $RENDER_PY" >&2; exit 1; }
[[ -f "$RAW2BMP_PY" ]] || { echo "ERROR: missing $RAW2BMP_PY" >&2; exit 1; }

mkdir -p "$OUTDIR" "$TMPROOT" "$MPLCONFIGDIR"

TMPDIR="$(mktemp -d -p "$TMPROOT" wxmb.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

# Build neutral GMT base (same for Day/Night geometry)
make_wx_base_bmp() {
  local tag="$1" W="$2" H="$3" out_bmp_z="$4"

  local stem="$TMPDIR/wxbase_${tag}_${W}x${H}"
  local png="${stem}.png"
  local png_fixed="${stem}_fixed.png"
  local raw="${stem}.raw"
  local bmp="${stem}.bmp"

  gmt begin "$stem" png
    gmt coast -R-180/180/-90/90 -JQ0/${W}p -Gblack -Sblack -A10000
    gmt coast -R-180/180/-90/90 -JQ0/${W}p -W0.5p,black -N1/0.4p,black -A10000
  gmt end || { echo "gmt failed for Wx base $tag ${W}x${H}" >&2; return 1; }

  convert "$png" -resize "${W}x${H}!" "$png_fixed" || {
    echo "resize failed for Wx base $tag ${W}x${H}" >&2; return 1; }

  convert "$png_fixed" RGB:"$raw" || {
    echo "raw extract failed for Wx base $tag ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" "$RAW2BMP_PY" --in "$raw" --out "$bmp" --width "$W" --height "$H" || {
    echo "bmp write failed for Wx base $tag ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" - <<'PY' "$bmp" "$out_bmp_z"
from hc_zlib import zcompress_file
import sys
zcompress_file(sys.argv[1], sys.argv[2], level=9)
PY
  [[ -f "$out_bmp_z" ]] || { echo "zlib failed for Wx base $tag ${W}x${H}" >&2; return 1; }

  rm -f "$png" "$png_fixed" "$raw" "$bmp"
}

# Build transparent line overlay (black coastlines + country borders only)
# Used AFTER weather rendering so black lines remain visible.
make_wx_line_overlay_png() {
  local W="$1" H="$2" out_png="$3"

  local stem_base="wxlines_src_${W}x${H}"   
  local png="$TMPDIR/${stem_base}.png"

  rm -f "$png" "$out_png"

   local ps="$TMPDIR/${stem_base}.ps"
  (
    cd "$TMPDIR" || exit 1
    rm -f "$ps" "$png"

    gmt pscoast \
      -R-180/180/-90/90 \
      -JX${W}p/${H}p \
      -X0 -Y0 \
      -W0.6p,black -N1/0.45p,black -A10000 \
      -B0 -P -K > "$ps" && \
    gmt psxy -R -J -T -O >> "$ps" && \
    gmt psconvert "$ps" -Tg -A -F"$stem_base"
  ) || { echo "gmt failed for Wx line overlay ${W}x${H}" >&2; return 1;} 

  [[ -f "$png" ]] || {
    echo "line overlay PNG not found: $png" >&2
    ls -l "$TMPDIR" >&2 || true
    return 1
  }

  # Convert white background to transparent; preserve black lines
  convert "$png" \
    -fuzz 8% -transparent white \
    -resize "${W}x${H}!" \
    "$out_png" || {
      echo "line overlay convert failed for ${W}x${H}" >&2
      return 1
    }

  [[ -f "$out_png" ]] || {
    echo "line overlay output missing after convert: $out_png" >&2
    return 1
  }

  rm -f "$png" "$TMPDIR/${stem_base}.ps" "$TMPDIR/${stem_base}.eps"
}

boost_day_wx_brightness() {
  local W="$1" H="$2"

  local in_bmp="$OUTDIR/map-D-${W}x${H}-Wx-mB.bmp"
  local out_z="$OUTDIR/map-D-${W}x${H}-Wx-mB.bmp.z"
  local stem="$TMPDIR/wxbright_D_${W}x${H}"
  local png="${stem}.png"
  local png_out="${stem}_out.png"
  local raw="${stem}.raw"

  [[ -f "$in_bmp" ]] || { echo "ERROR: missing Day Wx map $in_bmp" >&2; return 1; }

  convert "$in_bmp" "$png" || { echo "convert bmp->png failed for Day Wx ${W}x${H}" >&2; return 1; }

  # modest brighten/saturation boost; tune if needed

    convert "$png" \
    -modulate 148,132,100 \
    -gamma 1.08 \
    "$png_out" || { echo "brightness boost failed for Day Wx ${W}x${H}" >&2; return 1; }

  convert "$png_out" -resize "${W}x${H}!" RGB:"$raw" || {
    echo "png->raw failed for brightened Day Wx ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" "$RAW2BMP_PY" --in "$raw" --out "$in_bmp" --width "$W" --height "$H" || {
    echo "bmp rewrite failed for brightened Day Wx ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" - <<'PY' "$in_bmp" "$out_z"
from hc_zlib import zcompress_file
import sys
zcompress_file(sys.argv[1], sys.argv[2], level=9)
PY

  rm -f "$png" "$png_out" "$raw"
}

# Composite black coastline/country lines OVER final Wx map (D or N)
overlay_black_borders_on_wx_output() {
  local tag="$1" W="$2" H="$3"

  local in_bmp="$OUTDIR/map-${tag}-${W}x${H}-Wx-mB.bmp"
  local out_z="$OUTDIR/map-${tag}-${W}x${H}-Wx-mB.bmp.z"
  local line_png="$TMPDIR/wxlines_${W}x${H}.png"

  [[ -f "$in_bmp" ]] || { echo "ERROR: missing Wx map $in_bmp" >&2; return 1; }

  make_wx_line_overlay_png "$W" "$H" "$line_png"

  local stem="$TMPDIR/wxlines_comp_${tag}_${W}x${H}"
  local png="${stem}.png"
  local png_out="${stem}_out.png"
  local raw="${stem}.raw"

  convert "$in_bmp" "$png" || {
    echo "convert bmp->png failed for Wx ${tag} ${W}x${H}" >&2; return 1; }

  # Composite line overlay last so borders stay black on top of temp shading/haze
  convert "$png" "$line_png" -compose over -composite "$png_out" || {
    echo "border overlay composite failed for Wx ${tag} ${W}x${H}" >&2; return 1; }

  convert "$png_out" -resize "${W}x${H}!" RGB:"$raw" || {
    echo "png->raw failed after border overlay for Wx ${tag} ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" "$RAW2BMP_PY" --in "$raw" --out "$in_bmp" --width "$W" --height "$H" || {
    echo "bmp rewrite failed after border overlay for Wx ${tag} ${W}x${H}" >&2; return 1; }

  "$PYTHON_BIN" - <<'PY' "$in_bmp" "$out_z"
from hc_zlib import zcompress_file
import sys
zcompress_file(sys.argv[1], sys.argv[2], level=9)
PY
  [[ -f "$out_z" ]] || {
    echo "zlib rewrite failed after border overlay for Wx ${tag} ${W}x${H}" >&2; return 1; }

  rm -f "$png" "$png_out" "$raw"
}

pick_and_download() {
  local ymd="$1" hh="$2"
  local file="gfs.t${hh}z.pgrb2.0p25.f000"
  local dir="%2Fgfs.${ymd}%2F${hh}%2Fatmos"

  local url="${NOMADS_FILTER}?file=${file}&lev_mean_sea_level=on&lev_10_m_above_ground=on&lev_2_m_above_ground=on&var_PRMSL=on&var_UGRD=on&var_VGRD=on&var_TMP=on&leftlon=0&rightlon=359.75&toplat=90&bottomlat=-90&dir=${dir}"

  echo "Trying GFS ${ymd} ${hh}Z ..."
  curl -fs -A "open-hamclock-backend/1.0" --retry 2 --retry-delay 2 "$url" -o "$TMPDIR/gfs.grb2"
  local RETVAL=$?
  if [[ $RETVAL -eq 0 ]]; then
    echo "Downloaded: ${file} (${ymd} ${hh}Z)"
    echo "${ymd} ${hh}" > "$TMPDIR/gfs_cycle.txt"
  else
    echo "Curl error '$RETVAL' on GFS ${ymd} ${hh}Z"
  fi
  return $RETVAL
}

MAP_INTERVAL=6
MAP_READY=2

NOW=$(date -u -d "$MAP_READY hours ago" +%s)
HOUR_NOW=$(date -u -d "@$NOW" +%H)
HOUR_NOW=$((10#$HOUR_NOW))
START_TIME=$(( NOW - ((HOUR_NOW % MAP_INTERVAL) * 3600) ))

NUM_TRYS=8
downloaded=0
for ((try=0; try<NUM_TRYS; try++)); do
  check_time=$(( START_TIME - MAP_INTERVAL*3600*try ))
  d=$(date -u -d "@${check_time}" +%Y%m%d)
  hh=$(date -u -d "@${check_time}" +%H)
  if pick_and_download "$d" "$hh"; then
    downloaded=1
    break
  fi
done

if [[ "$downloaded" -ne 1 ]]; then
  echo "ERROR: could not download a recent GFS subset from NOMADS." >&2
  exit 1
fi

render_one() {
  local tag="$1" W="$2" H="$3" base="$4" log_inventory="${5:-0}"

  local inv_flag=()
  if [[ "$log_inventory" -eq 1 ]]; then
    inv_flag=(--log-inventory)
  fi

  "$PYTHON_BIN" "$RENDER_PY" \
    --grib "$TMPDIR/gfs.grb2" \
    --base "$base" \
    --outdir "$OUTDIR" \
    --tag "$tag" \
    --width "$W" \
    --height "$H" \
    "${inv_flag[@]}"
}

logged_inventory=0

for wh in "${SIZES[@]}"; do
  W="${wh%x*}"
  H="${wh#*x}"

  DAY_WX_BASE="$TMPDIR/map-D-${W}x${H}-WxBase.bmp.z"
  NIGHT_WX_BASE="$TMPDIR/map-N-${W}x${H}-WxBase.bmp.z"

  echo "Building Wx base Day ${W}x${H} (GMT base)"
  make_wx_base_bmp "D" "$W" "$H" "$DAY_WX_BASE"

  echo "Rendering Wx-mB Day ${W}x${H}"
  if [[ "$logged_inventory" -eq 0 ]]; then
    render_one "D" "$W" "$H" "$DAY_WX_BASE" 1
    logged_inventory=1
  else
    render_one "D" "$W" "$H" "$DAY_WX_BASE" 0
  fi

  echo "Boosting Day brightness for final Wx-mB Day ${W}x${H}"
  boost_day_wx_brightness "$W" "$H"

  echo "Overlaying black borders on final Wx-mB Day ${W}x${H}"
  overlay_black_borders_on_wx_output "D" "$W" "$H"

  echo "Building Wx base Night ${W}x${H} (GMT base)"
  make_wx_base_bmp "N" "$W" "$H" "$NIGHT_WX_BASE"

  echo "Rendering Wx-mB Night ${W}x${H}"
  render_one "N" "$W" "$H" "$NIGHT_WX_BASE" 0

  echo "Overlaying black borders on final Wx-mB Night ${W}x${H}"
  overlay_black_borders_on_wx_output "N" "$W" "$H"

  chmod 0644 \
    "$OUTDIR/map-D-${W}x${H}-Wx-mB.bmp" \
    "$OUTDIR/map-D-${W}x${H}-Wx-mB.bmp.z" \
    2>/dev/null || true

  if [[ -f "$OUTDIR/map-N-${W}x${H}-Wx-mB.bmp" ]]; then
    chmod 0644 \
      "$OUTDIR/map-N-${W}x${H}-Wx-mB.bmp" \
      "$OUTDIR/map-N-${W}x${H}-Wx-mB.bmp.z"
  fi
done

echo "OK: Wx-mB maps updated in $OUTDIR"
