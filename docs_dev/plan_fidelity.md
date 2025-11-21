# Plan to reach Inkscape-level diff (<=0.2%)

1) Rebuild line/layout logic to match Inkscape plain-SVG flow
   - Parse tspans into “chunks” by x/y, dx/dy, role, and line changes (see docs_dev/inkscape_font_classes/sp-text.cpp and Layout-TNG-*.cpp).
   - Treat each text element as a single line unless explicit x/y on tspans; honor per-tspan anchors (start/middle/end) but compute the line anchor once after measuring all chunks.
   - Plain SVG case: if a tspan has x/y set, reset cursor to that absolute point; otherwise advance from previous chunk; apply dx/dy per-character.

2) Accurate width measurement for anchoring
   - Shape each chunk with its resolved font; sum advances (including letter/word spacing) to get chunk width.
   - Compute line width as sum of chunk widths (+ horizontal dx/dy); apply text-anchor to line_width, not per-chunk, in transformed coordinates (apply baked scale).

3) TextPath anchoring and baseline
   - Measure total text advance (with transform scale) to adjust startOffset for middle/end.
   - Place chunks along path using cumulative advance; use tangents for rotation; apply dy along normal; apply transforms after path placement.

4) Decorations per line and font
   - Use metrics of the chunk’s font for underline/strike; position after anchoring; transform decorations with baked matrix.

5) Font shaping and fallback
   - Keep current font selection, but when a chunk is fully covered by fallback, reshape with fallback to avoid zero-advance .notdef; mixed-script yields separate chunks.

6) Validation loop
   - Add deterministic t2p_compare (no HTML) on samples/test_text_to_path_advanced.svg vs Inkscape paths; track diff.
   - Micro-tests: single tspan anchor+dx/dy, scaled text, textPath center-aligned; compare vs Inkscape outputs.

7) Implementation order
   a) Chunk collection & line anchoring (plain SVG) → test.
   b) Decorations tied to line anchor/font metrics → test.
   c) TextPath anchor with transformed advances → test.
   d) Micro-tests + main advanced sample → measure diff.
