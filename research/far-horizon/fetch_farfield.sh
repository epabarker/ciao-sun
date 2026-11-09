#!/bin/bash
# RESEARCH, throwaway. Fetch the far-field data used in far-horizon.md (all anonymous, open).
#   bash fetch_farfield.sh /path/to/data/farfield
# Writes ~1.05 GB: OS Terrain 50 GB ASCII grid (162 MB) + EA LIDAR Composite 2 m DSM and DTM
# for the 20 5 km tiles E 365000-385000, N 160000-185000 (east/south-east of Bristol, ~22 MB each).
set -euo pipefail
OUT="$1"
mkdir -p "$OUT/terr50" "$OUT/ea2m"
T50="$OUT/terr50/terr50_gagg_gb.zip"
if [ ! -s "$T50" ]; then
  curl -fL -sS -o "$T50" "https://api.os.uk/downloads/v1/products/Terrain50/downloads?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect"
fi
for e in 65 70 75 80; do
  for n in 60 65 70 75 80; do
    t="ST${e}${n}"
    for prod in dsm:lidar_composite_last_return_dsm dtm:lidar_composite_dtm; do
      k="${prod%%:*}"; slug="${prod#*:}"
      z="$OUT/ea2m/${k}_${t}.zip"
      [ -s "$z" ] && continue
      curl -fsS -A "sunspot-research (github.com/epabarker/daylight-viewing)" -o "$z" \
        -w "$k $t %{http_code} %{size_download}\n" \
        "https://environment.data.gov.uk/tiles/collections/survey/${slug}/2022/2/${t}" || echo "$k $t FAILED"
    done
  done
done
du -sh "$OUT/terr50/terr50_gagg_gb.zip" "$OUT/ea2m"
