Inkscape text→path pipeline (plain SVG)
=======================================

This note distills the exact processing path Inkscape follows when converting `<text>` / `<tspan>` / `<textPath>` / flowed text to outlines. Source files: `path-chemistry.cpp`, `sp-text.cpp`, `sp-tspan.cpp`, `sp-flowtext.cpp`, `Layout-TNG-*.cpp`, `font-factory.cpp`, `font-instance.cpp`, `font-factory.cpp`, `OpenTypeUtil.cpp`.

High‑level flow
---------------
1) Document prep  
   * `convert_text_to_curves(SPDocument*)` (path-chemistry.cpp) collects every `SPText`/`SPFlowtext` recursively (skips `display:none`), calls `te_update_layout_now_recursive` to force layout.
2) Per‑object conversion  
   * `sp_text_to_curve_repr(SPItem*)` obtains the `Layout` via `te_get_layout`, converts each glyph to SVG paths (`Layout::convertToSVG`) or plain curves, groups them, reapplies style/transform, sets `aria-label` with original text, and returns a `<g>` (or single `<path>` when only one style run).
3) Replace in document  
   * `sp_item_list_to_curves` substitutes original nodes with the returned paths, keeping id/class/transform/style.

Layout input construction (`SPText::_buildLayoutInput`)
------------------------------------------------------
* Walks the `<text>` tree, accumulating OptionalTextTagAttrs (x,y,dx,dy,rotate,textLength,lengthAdjust).  
* `sodipodi:role="line"` tspans: strip x/y (except first), insert paragraph breaks, and synthesize empty spans to preserve y positioning.  
* SVG2 wrapping: shape-inside/inline-size disables x/y/dx/dy on descendants; optional inclusion/exclusion shapes added.  
* textLength on the root `<text>` sets `Layout::textLength` and `lengthAdjust`.  
* TextPath: clears x/y, keeps dx/dy/rotate; marks path fitting later.  
* Each SPString appends a text source with style pointer and positional vectors; control codes (line/para breaks) added where needed.

Layout calculation (Layout-TNG-Compute.cpp)
-------------------------------------------
1) Paragraph creation & itemization  
   * Input stream is segmented into paragraphs (newline/role=line).  
   * Pango itemization per paragraph yields `pango_items` (font run, bidi level, script).  
   * Builds `UnbrokenSpan` objects per Pango item, carrying: font size, metrics, text_orientation, writing mode, dx/dy/rotate at span start, optional x/y, and glyph string (Pango shaping).
2) Line fitting (`Calculator::_findChunksForLine`)  
   * ScanlineMaker supplies available horizontal runs (shape-inside / inline-size / infinite).  
   * `_buildChunksInScanRun` greedily fills each run:  
     - Measures spans with `_measureUnbrokenSpan` accumulating glyph advances + word-spacing on `is_expandable_space`, letter-spacing on every cursor position, and `textLengthIncrement`.  
     - Tracks whitespace_count to later redistribute justification.  
     - Ensures line height covers largest ascent/descent of spans (after line-height multiplier); may restart if too tall.  
     - Forces new chunk when span starts with explicit x/y.  
     - Keeps last valid break (mandatory break or last whitespace) and backs out overfull text.  
     - After fitting: trims trailing whitespace width and trailing letter-spacing from last broken span.  
3) Line output (`_outputLine`)  
   * Sets baseline_y from ScanlineMaker; adjusts for writing-mode (vertical uses em‑center).  
   * Alignment: chunk.left_x = start/mid/end using `text-anchor` or `text-align` precedence; for justify, computes `add_to_each_whitespace`.  
   * “Inkscape SVG” vs “plain SVG” handling: if first broken span of chunk starts at char 0 and has y set, y resets baseline (multiline tspans). Else y is treated as dy from previous line. `_y_offset` stores dy/y shifts per line.  
   * Initializes `current_x` (0 for LTR, text_width or scanrun_width for RTL justify).  
   * Applies span-level dx/dy/rotate once at span start.
   * Processes glyphs cluster by cluster:
     - Position (horizontal text): `x += geometry.x_offset`, `y += geometry.y_offset`; add dominant baseline offset.  
     - Position (vertical text): complex branch: upright vs sideways; Pango-version-specific fixes (1.44–1.48); applies hb v-origin when present; synthesizes vertical metrics if missing; compensates mark advances; RTL subtracts glyph width.  
     - Advance = glyph width (Pango geometry.width scaled) corrected for vertical quirks; reduced to 0 for newline or non-spacing marks when required.  
     - Adds letter-/word-spacing and textLength increments to `advance_width`; accumulates `current_x` with direction sign; stores `Character.x` relative to span start.  
     - Records rotation (glyph_rotate), per-cluster width, and maps character→glyph indices.
   * Sets `Span.x_start/x_end`, stores per-span font pointer, size, baseline_shift, direction.

Text-on-path fitting (`Layout::fitToPathAlign`)
-----------------------------------------------
* If textPath present, after layout it warps glyph positions onto the path:  
  - Computes startOffset (len or %) plus alignment shift (start/mid/end).  
  - For each cluster, computes midpoint on path, tangent; rotates glyphs accordingly.  
  - Updates span x_start/x_end by offset; hides glyphs if outside path.

Curves generation (`Layout::convertToSVG`)
------------------------------------------
* For each glyph in range:  
  - Get glyph outline: if OpenType SVG table exists, emits embedded SVG snippet with transform `Scale(1/em, -1/em) * glyph_matrix`. Else gets PathVector from FontInstance (cached outlines).  
  - `glyph_matrix` = translate by glyph.x/y + span.chunk.left_x + line.baseline_y, rotate by glyph.rotation, scale by `font_size / design_units`, flip Y, and optionally vertical_scale (textLength spacing-and-glyphs).  
* Returns PathVector plus list of SVG snippets to be imported (e.g., color glyphs).

Grouping & style preservation (`sp_text_to_curve_repr`)
------------------------------------------------------
* Walks glyph iterator; groups consecutive glyphs sharing same source object (`pos_obj`) to keep paint-order/filters.  
* Merges dying-parent styles up the tspan chain (`style->merge` up to item) to reflect cascade at conversion moment.  
* For each group emits `<path style=... d=...>`; wraps in `<g>` if multiple groups or color-SVG glyphs are present.  
* Copies original object attributes (id, class, transform, style diff against parent) and sets `aria-label` with original text content.

Font resolution
---------------
* CSS→Pango mapping: `ink_font_description_from_style` maps font-family, style (normal/italic/oblique), weight (100–900 with special mapping of 400/normal, 500/medium, etc.), stretch (ultra-condensed…ultra-expanded), variant (small-caps), variations string; size is forced to a huge constant (FontFactory::fontSize) to avoid hinting issues—actual scale applied later.  
* Font selection: `FontFactory::Face` loads via fontconfig (Fc) with `FC_OUTLINE` enforced; fallback to sans-serif if load fails.  
* Family name normalization: `sp_font_description_get_family` remaps Pango “Sans/Serif/Monospace” to CSS generics.  
* Style name normalization (important for matching): in `GetUIStyles`, styleUIName strings are rewritten: “Book”→“Normal”, “Semi-Light”→“Light”, “Ultra-Heavy”→“Heavy”; synthetic faces are rejected except for CSS generic families.  
* Variations: if `font-variation-settings` present, set on Pango description; OpenType variable axes read via HarfBuzz/FreeType in `readOpenTypeFvarAxes` and stored in FontInstance.  
* OpenType SVG glyphs: `readOpenTypeSVGTable` caches SVG glyphs; used automatically during convertToSVG.  
* Missing vertical metrics: vertical advances synthesized from em box; vertical anchor corrections applied per glyph.

Spacing, lengthAdjust, justification details
--------------------------------------------
* Measurement includes word-spacing on Pango `is_expandable_space` and letter-spacing on `is_cursor_position`; the last trailing whitespace and trailing letter-spacing are subtracted from the chunk width to avoid overhanging space.  
* `textLength`:  
  - LENGTHADJUST_SPACING → adds `textLengthIncrement` (precomputed difference/num_chars) to every advance.  
  - LENGTHADJUST_SPACINGANDGLYPHS → scales font size horizontally by `textLengthMultiplier`; vertical scaling undone by `glyph.vertical_scale = 1 / multiplier` during output.  
* Justify: `add_to_each_whitespace = (scanrun_width - text_width)/whitespace_count` distributed only over expandable spaces.  
* dx/dy/rotate applied at span start (char_byte==0); y/dy reset per new line (see `_y_offset` logic); x/y on spans break chunks to new columns/lines.

Baseline and orientation
------------------------
* Baseline per line: horizontal text uses typographic ascent; vertical uses em‑center unless text-orientation overrides.  
* Dominant baseline: defaults to alphabetic (horizontal) or central (vertical) unless overridden; applied per glyph via font baselines table.  
* RTL handling: current_x starts at text_width (or scanrun_width when justified) and decreases by advances; additional cluster width correction subtracts geometry.width per glyph (post 2005 fix).  
* Writing modes: block progression TOP_TO_BOTTOM, LEFT_TO_RIGHT, RIGHT_TO_LEFT supported; orthogonal detection controls text-on-path rotation choice.

Special cases
-------------
* Control codes (LINE_BREAK, PARAGRAPH_BREAK) stored with width/ascent/descent; participate in layout but emit no glyphs.  
* Soft hyphen: drawn only if at line end; otherwise skipped while still creating Character records.  
* textLength + textPath: after fitting to path, spans’ x_start/x_end shifted by startOffset+alignment.  
* Flowed text (flowRoot/flowPara) uses same machinery but wrap shapes from flow region paths; overflow handled by InfiniteScanlineMaker.

Why spaces aren’t double-counted
--------------------------------
* `_measureUnbrokenSpan` adds spacing to advances; `_buildChunksInScanRun` trims final whitespace and final letter-spacing so alignment anchoring uses visual ink width, not trailing space; `_outputLine` then re-applies spacing while emitting characters/glyphs (including justify increment and textLength increment).

Where to look in code
---------------------
* parse & layout input: `sp-text.cpp::_buildLayoutInput`, `sp-textpath.cpp`, `sp-tspan.cpp`, `sp-flowtext.cpp`  
* layout engine core: `Layout-TNG-Compute.cpp` (Calculator, Chunk/Span/Glyph creation), `Layout-TNG-Input.cpp`, `Layout-TNG-Output.cpp`  
* text→path entrypoints: `path-chemistry.cpp::convert_text_to_curves`, `sp_text_to_curve_repr`  
* font matching/loading: `font-factory.cpp`, `font-instance.cpp`, `font-collections.cpp`, `font-substitution.cpp`  
* OpenType extras: `OpenTypeUtil.cpp` (fvar axes, SVG table), `nr-svgfonts.cpp` (SVG fonts)  
* Drawing of glyph outlines: `font-instance.cpp::PathVector`, `Layout::convertToSVG/convertToCurves`

Key takeaways for reproducing Inkscape fidelity
-----------------------------------------------
* Always run full Layout pipeline; never reuse raw x/y/dx/dy without applying spacing/justification/textLength trims.  
* Anchor per-chunk after measuring text_width with trailing-space removal.  
* Apply dx/dy/rotate only at span start; reset dy per line when sodipodi role indicates multiline.  
* For RTL, subtract glyph geometry.width per glyph when positioning.  
* Keep Pango/HarfBuzz version quirks for vertical text in mind (advance and origin fixes).  
* When fitting to path: shift by alignment, center the cluster, rotate by path tangent; hide glyphs outside path.  
* Preserve style per tspan branch; merge ancestor styles when creating paths; keep aria-label.

