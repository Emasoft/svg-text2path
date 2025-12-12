#!/usr/bin/env bash
# Unified launcher for cached fast batch comparison.
# Uses defaults: threshold 20, resolution viewbox, scale 4, timeout 180s, skip text4.svg.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python "$SCRIPT_DIR/fast_batch_cached.py" \
  --threshold 20 \
  --resolution viewbox \
  --scale 4 \
  --timeout 180 \
  --skip text4.svg \
  "$@"
