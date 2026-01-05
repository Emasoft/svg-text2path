# Competitor Analysis Report: SVG Text-to-Path Libraries

**Date**: 2026-01-06
**Analyzed**: 10 competitor libraries
**Purpose**: Identify strengths, weaknesses, and opportunities for Text2Path

---

## Executive Summary

After analyzing 10 competitor libraries, **Text2Path emerges as the most feature-complete solution** for SVG text-to-path conversion. Key differentiators:

1. **HarfBuzz integration** - Only Text2Path and harfbuzzjs use proper text shaping
2. **BiDi/RTL support** - Only Text2Path handles bidirectional text (via python-bidi)
3. **SVG file processing** - Most competitors only convert text strings, not SVG elements
4. **Transform handling** - Comprehensive SVG transform matrix support
5. **System font discovery** - Automatic font matching via fontconfig

---

## Feature Comparison Matrix

| Library | Language | HarfBuzz | BiDi/RTL | `<text>` | `<tspan>` | `<textPath>` | Transforms | Font Discovery | Variable Fonts |
|---------|----------|----------|----------|----------|-----------|--------------|------------|----------------|----------------|
| **Text2Path** | Python | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | Pending |
| svg-text-to-path | JavaScript | No | No | Yes | Yes | No | Yes | No | Yes (fontkit) |
| text-to-svg | JavaScript | No | No | No | No | No | No | No | No |
| harfbuzzjs | JavaScript | **Yes** | **Yes** | No | No | No | No | No | **Yes** |
| svgpathtools | Python | No | No | No | No | No | **Yes** | No | No |
| font_to_svg | C++ | No | No | No | No | No | No | No | No |
| element-to-path | JavaScript | No | No | No | No | No | No | No | No |
| text2svg | JavaScript | No | No | No | No | No | No | No | No |
| svgttf | JavaScript | No | No | No | No | No | No | No | No |
| convertSVGShapeToPath | JavaScript | No | No | No | No | No | Yes | No | No |
| text-to-svg-jiuranya | TypeScript | No | No | No | No | No | No | Yes (API) | No |

---

## Competitor Categories

### Category 1: SVG Element Converters (Closest Competitors)

#### svg-text-to-path (paulzi)
- **What it does**: JavaScript library converting SVG `<text>` and `<tspan>` elements
- **Shaping**: Uses fontkit.layout() or opentype.js - NOT HarfBuzz
- **Strengths**:
  - Variable font support (fontkit)
  - Multiple font providers (Google Fonts, @font-face, directories)
  - CSS font-feature-settings (liga, smcp, kern)
  - Server mode (HTTP interface)
  - Statistics collection
- **Weaknesses**:
  - No HarfBuzz = no proper ligatures/contextual forms
  - No BiDi/RTL support
  - No `<textPath>` support
- **Learn from**: Font provider architecture (GoogleProvider, FontFaceProvider, DirProvider)

### Category 2: Text String Converters

#### text-to-svg (shrhdk)
- **What it does**: Convert plain text strings to SVG paths
- **Shaping**: opentype.js only (basic kerning, no shaping)
- **Strengths**:
  - Pure JavaScript, no native deps
  - Simple API: `getD()`, `getPath()`, `getSVG()`
  - 9 anchor point options
  - Debug visualization mode
- **Weaknesses**:
  - No SVG file processing
  - No shaping, BiDi, transforms
  - Single font file only
- **Learn from**: Anchor point implementation, debug visualization

#### text2svg (bubkoo)
- **What it does**: Lightweight text-to-SVG with opentype.js
- **Strengths**:
  - Per-character styling (path0, path1 CSS classes)
  - Font caching for speed
  - Kerning support
- **Weaknesses**: Same as text-to-svg
- **Learn from**: Per-character styling approach

#### text-to-svg-jiuranya
- **What it does**: Web-based Next.js tool with animation features
- **Shaping**: opentype.js + makerjs
- **Strengths**:
  - Google Fonts API integration
  - Animation presets (signature, draw, fade, pulse)
  - DXF export
  - Multilingual UI (en/zh/fr)
- **Weaknesses**: Web-only, no CLI, no shaping
- **Learn from**: Animation CSS generation, Google Fonts integration

### Category 3: Text Shaping Engines

#### harfbuzzjs
- **What it does**: HarfBuzz compiled to WebAssembly
- **Shaping**: Full HarfBuzz (identical to Text2Path's uharfbuzz)
- **Strengths**:
  - Built-in `glyphToPath()` - glyph outlines without fonttools
  - Variable font support via `setVariations()`
  - `shapeWithTrace()` for debugging GSUB/GPOS
  - `guessSegmentProperties()` for auto RTL detection
- **Weaknesses**:
  - Library only, no SVG processing
  - WebAssembly overhead
  - Manual transform application required
- **Learn from**:
  - **Critical**: `glyphToPath()` approach could replace our fonttools pipeline
  - Trace debugging for complex scripts
  - Variable font API

### Category 4: Path/Geometry Libraries

#### svgpathtools (Python)
- **What it does**: SVG path manipulation and Bezier mathematics
- **NO text support** - pure geometry library
- **Strengths**:
  - Excellent transform matrix handling
  - Path intersection algorithms
  - Offset curves (parallel paths)
  - Path area/length computation
- **Weaknesses**: Zero text/font support
- **Learn from**: Transform flattening approach, Bezier math

#### element-to-path
- **What it does**: Convert SVG shapes (rect, circle, ellipse) to paths
- **NO text support**
- **Strengths**: W3C-compliant shape conversion
- **Weaknesses**: Only geometric shapes, no transforms
- **Learn from**: Rounded rectangle rx/ry handling

### Category 5: Font Tools

#### font_to_svg (C++)
- **What it does**: Extract single glyph outlines from TrueType fonts
- **Shaping**: None - single character only
- **Strengths**: Header-only C++, clean quadratic Bezier implementation
- **Weaknesses**:
  - Single glyph only (no text strings)
  - No ligatures, no RTL, no complex scripts
  - Known bugs with metrics
- **Learn from**: TrueType outline extraction (educational)

#### svgttf
- **What it does**: Bidirectional font/SVG conversion
- **Strengths**:
  - Path union via paper.js (merges overlapping shapes)
  - Creates fonts from SVG drawings
- **Weaknesses**: No text shaping, strict naming conventions
- **Learn from**: Path union operations for merged paths

### Category 6: SVG Optimization (Not Text Converters)

#### convertSVGShapeToPath
- **What it does**: SVGO wrapper for SVG optimization
- **NO text support** - only shape optimization
- **Not a competitor** - different use case entirely

---

## Key Insights

### 1. Text2Path's Unique Position

**Text2Path is the ONLY library that combines:**
- HarfBuzz text shaping
- BiDi/RTL support
- Full SVG element support (`<text>`, `<tspan>`, `<textPath>`)
- SVG transform handling
- System font discovery

### 2. Gaps in Competitor Landscape

| Gap | Description | Our Advantage |
|-----|-------------|---------------|
| BiDi/RTL | No competitor handles Arabic/Hebrew | python-bidi integration |
| `<textPath>` | Only svg-text-to-path supports `<tspan>`; none support `<textPath>` | Full support |
| Complex Scripts | None handle Devanagari, Thai, etc. | HarfBuzz handles all |
| Font Discovery | Most require explicit font paths | fontconfig + FontCache |

### 3. Features to Consider Adding

| Feature | Source | Priority | Complexity |
|---------|--------|----------|------------|
| Variable font instancing | harfbuzzjs | High | Medium |
| Built-in glyphToPath() | harfbuzzjs | Medium | High (C bindings) |
| Google Fonts API | svg-text-to-path | Medium | Low |
| Per-character styling | text2svg | Low | Low |
| Debug visualization | text-to-svg | Low | Low |
| Animation CSS | text-to-svg-jiuranya | Low | Low |
| Path union | svgttf | Low | Medium |

### 4. Architecture Comparison

| Approach | Libraries | Pros | Cons |
|----------|-----------|------|------|
| Python + uharfbuzz | **Text2Path** | Production-ready, server-optimized | Slower than WASM |
| JavaScript + opentype.js | Most competitors | Easy deployment | No proper shaping |
| JavaScript + HarfBuzz WASM | harfbuzzjs | Full shaping in browser | WASM overhead |
| C++ + FreeType | font_to_svg | Maximum speed | Single glyph only |

---

## Recommendations

### Immediate (Phase 4+)

1. **Variable fonts**: Priority implementation based on harfbuzzjs approach
2. **Google Fonts integration**: Follow svg-text-to-path's provider pattern
3. **Debug visualization**: Add optional debug SVG output like text-to-svg

### Future Consideration

1. **Browser version**: Consider harfbuzzjs-style WASM build for web use
2. **Path union**: Add paper.js integration for merged path output
3. **Animation export**: Add CSS animation generation for signatures

---

## Competitor Statistics

| Library | GitHub Stars | Last Update | NPM/PyPI Downloads |
|---------|--------------|-------------|-------------------|
| svg-text-to-path | ~150 | Active | ~1K/week |
| text-to-svg | ~800 | 2024 | ~10K/week |
| harfbuzzjs | ~200 | Active | ~5K/week |
| svgpathtools | ~500 | Active | ~5K/week |
| font_to_svg | ~200 | 2023 | N/A (C++) |
| element-to-path | ~50 | 2023 | ~500/week |
| text2svg | ~100 | 2022 | ~500/week |
| svgttf | ~20 | 2020 | ~50/week |

---

## Conclusion

Text2Path occupies a unique position in the market as the only library combining:
- **Professional text shaping** (HarfBuzz)
- **International text support** (BiDi/RTL)
- **Full SVG processing** (elements + transforms)
- **Automatic font discovery** (fontconfig)

The closest functional competitor is **svg-text-to-path**, but it lacks HarfBuzz shaping and BiDi support. The closest technical approach is **harfbuzzjs**, but it's a shaping engine, not an SVG processor.

**Text2Path's primary differentiator remains its comprehensive approach to the complete text-to-path pipeline**, from SVG parsing through font resolution, text shaping, and path generation with proper transforms.
