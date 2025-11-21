## Failed attempt: chunk-based anchoring/refactor (2025-11-21)

Goal: adopt chunk-based shaping (split runs by font coverage, anchor once with transform-aware widths) to reduce diff against Inkscape on `samples/test_text_to_path_advanced.svg`.

Changes made:
- Segmented runs into primary/fallback chunks, shaped each with its own HarfBuzz font.
- Tried single global anchor offset (with baked transform scale).
- Decorations switched to “dominant chunk” font metrics.

Outcome:
- Diff worsened/slightly regressed (~7.9% vs original ~7.6% baseline).
- Observed issues: per-line anchoring lost (global advance cursor shifts lines); textPath/startOffset still misaligned; decorations still not solving main diff drivers.

Why it failed:
- Anchor was applied globally, not per baseline/line; mixing multiple lines and path text caused horizontal drift.
- TextPath anchoring still ignored path length after transform.
- Decorations used dominant chunk metrics but baseline positioning still depended on global advance.

Next time:
- Revert to per-line anchoring before chunking.
- Apply anchor after converting advances to path-length for textPath.
- Keep chunk shaping but compute anchor per line, not globally.

## Failed attempt: anchor scaling & partial textPath (2025-11-21)

Goal: fix misalignment by baking transform scale into anchor offsets and add a first pass of textPath rotation.

Changes made:
- Multiplied anchor offsets by averaged transform scale before glyph placement.
- Implemented textPath laying glyphs along the path tangent with rotation/normal offset; kept existing tspan handling.

Outcome:
- Diff barely improved (≈7.9% vs 8.3%). The scale tweak was counterproductive and later reverted; textPath handled but main diff persists.

Why it failed:
- Anchor pre-scaling double-applied transforms (anchors already scaled when glyph coordinates are baked), so positions stayed off for scaled text.
- TextPath fix alone cannot recover the large diff coming from general layout/RTL issues.

Next time:
- Keep anchors in local coordinates and let the baked matrix scale everything.
- Focus on accurate line measurement (letter/word spacing, dx/dy) and RTL run ordering; audit inline-size/anchor handling against Inkscape code.
