# Text51 Investigation – Final Notes (Iteration_0017)

## What was fixed
- **sbb-svg2png.cjs**: stopped regenerating viewBox when one already exists (visible/element modes), eliminating false shrinkage.
- **sbb-comparer.cjs**: now accepts `--scale` (default `4`, matching sbb-svg2png); render params are logged in verbose mode and shown in HTML (“Render Resolution”). Diff PNG now renders at the same resolution as the individual renders.
- **run_text51_iteration.py**: passes `--scale 4` to sbb-comparer; retains stroke patch on converted SVGs.

## Current patch rules
- Original `text51.svg` stays untouched.
- Converted SVG paths get `stroke-width="0.23px"` and `stroke="#000080"` (fill preserved or default `#000080`).
- Diff threshold set to `20/256` to absorb AA noise.

## Latest benchmark (wins)
- Iteration folder: `samples/TEXT51_INVESTIGATION/ITERATION_0017_20251201_210828/`
- Pair A (original vs converted, no patch): **0.66%** diff @ threshold 20. Diff PNG: 4215×758.
  - HTML: `.../COMPARISONS/SVG-PAIR-A-DIFF/text51_original_vs_text51_converted_comparison.html`
- Pair B (converted patched stroke 0.23px + stroke color): **0.93%** diff @ threshold 20 (slightly worse at full-res).
  - HTML: `.../COMPARISONS/SVG-PAIR-B-DIFF/text51_original_patched_vs_text51_converted_patched_comparison.html`

## How to reproduce
1) Ensure SVG-BBOX and SVG-MATRIX are present at repo root (using our forked copies).  
2) Run: `python scripts/run_text51_iteration.py`  
   - Produces timestamped iteration with SVG pairs, PNG renders, diffs, and HTML reports.
   - Uses sbb-comparer with `--scale 4`, threshold 20.
3) Open reports:  
   `open -a "Google Chrome" samples/TEXT51_INVESTIGATION/<ITER>/COMPARISONS/SVG-PAIR-A-DIFF/text51_original_vs_text51_converted_comparison.html` (and the B variant).

## Key paths
- Tools: `SVG-BBOX/sbb-svg2png.cjs`, `SVG-BBOX/sbb-comparer.cjs`
- Runner: `scripts/run_text51_iteration.py`
- Winning iteration artifacts: `samples/TEXT51_INVESTIGATION/ITERATION_0017_20251201_210828/`

## Takeaway
Scaling mismatch in sbb-comparer was hiding the real progress. With viewBox handling fixed and diff rendering at full resolution, text2path now matches `text51.svg` to ~0.66% difference without font-size hacks—big step forward. 
