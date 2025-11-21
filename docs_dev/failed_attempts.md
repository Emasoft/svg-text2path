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
