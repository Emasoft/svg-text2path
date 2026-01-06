#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SAMPLES="$ROOT/samples/reference_objects"
OUTDIR="${OUTDIR:-$ROOT/tmp/batch_runs}"
THRESHOLD="${THRESHOLD:-20}"
# Lower scale/resolution for speed; caller can override.
SCALE="${SCALE:-1}"
RESOLUTION="${RESOLUTION:-nominal}"

mkdir -p "$OUTDIR"

SKIP=("text4.svg")

is_skipped() {
  local f="$1"
  for s in "${SKIP[@]}"; do
    [[ "$s" == "$f" ]] && return 0
  done
  return 1
}

printf "file,diff_percent,status\n" > "$OUTDIR/summary.csv"

for svg in "$SAMPLES"/text*.svg; do
  fname="$(basename "$svg")"
  if is_skipped "$fname"; then
    printf "%s,SKIPPED,skip\n" "$fname" >> "$OUTDIR/summary.csv"
    continue
  fi

  out_svg="$OUTDIR/${fname%.svg}_converted.svg"
  diff_img="$OUTDIR/${fname%.svg}_diff.png"
  json_out="$OUTDIR/${fname%.svg}_compare.json"

  python "$ROOT/text2path/main.py" "$svg" "$out_svg" --no-html >/dev/null

  # Use npx sbb-compare from npm svg-bbox package
  npx sbb-compare "$svg" "$out_svg" \
    --out-diff "$diff_img" --threshold "$THRESHOLD" --scale "$SCALE" --resolution "$RESOLUTION" \
    --json > "$json_out"

  diff_pct=$(node -e "const d=require('./$json_out');console.log((d.diffPercent ?? d.diff ?? 0).toFixed(2));")
  status="pass"
  awk "BEGIN{exit !($diff_pct<3)}" || status="fail"

  printf "%s,%s,%s\n" "$fname" "$diff_pct" "$status" >> "$OUTDIR/summary.csv"
done

echo "Summary: $OUTDIR/summary.csv"
