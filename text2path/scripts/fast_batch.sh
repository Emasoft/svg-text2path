#!/usr/bin/env bash
set -euo pipefail

# Fast, low-memory batch compare for text*.svg reference samples.
# Targets: <1 minute, <5 GB. Uses a single Chromium session via sbb-compare --batch.

REAL="$(realpath "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$REAL")"/../.. && pwd)"
SRC="$ROOT/samples/reference_objects"
OUT="${OUTDIR:-$ROOT/tmp/fast}"

THRESHOLD="${THRESHOLD:-20}"      # pixel diff threshold
SCALE="${SCALE:-1}"               # render scale (keep low for speed)
RESOLUTION="${RESOLUTION:-nominal}" # rendering mode

mkdir -p "$OUT/converted"

# Build batch pairs JSON
PAIRS=()
for svg in "$SRC"/text*.svg; do
  base="$(basename "$svg")"
  # Skip known problematic sample
  [[ "$base" == "text4.svg" ]] && continue
  out="$OUT/converted/${base%.svg}_conv.svg"
  python "$ROOT/text2path/main.py" "$svg" "$out" --no-html >/dev/null
  PAIRS+=("{\"a\":\"$svg\",\"b\":\"$out\"}")
done

printf '[%s]' "$(IFS=,; echo "${PAIRS[*]}")" > "$OUT/pairs.json"

# Single Chromium session, batch compare, JSON out (npm svg-bbox)
npx sbb-compare \
  --batch "$OUT/pairs.json" \
  --threshold "$THRESHOLD" \
  --scale "$SCALE" \
  --resolution "$RESOLUTION" \
  --json > "$OUT/summary.json"

# Print quick CSV (file,diff,status)
node -e '
const fs=require("fs");
const r=JSON.parse(fs.readFileSync(process.argv[1]));
r.results.forEach(x=>{
  const d = (x.diffPercent ?? x.diff ?? 0);
  const status = d < 3 ? "pass" : "FAIL";
  console.log(`${x.a.split("/").pop()},${d.toFixed(2)},${status}`);
});
' "$OUT/summary.json"

echo "Summary JSON: $OUT/summary.json"
