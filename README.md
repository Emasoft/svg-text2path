# Text-to-Path Converter

Python CLI suite to convert all SVG text (text/tspan/textPath) into outline paths with HarfBuzz shaping, and to compare results against Inkscape/reference renders.

## Features
- Unicode BiDi + HarfBuzz shaping (ligatures, RTL, complex scripts)
- Strict font matching (fails on missing fonts; no silent fallbacks)
- TextPath support with tangent-based placement
- Visual diff helper with HTML history (`t2p_compare`)

## Install

```bash
uv pip install -r requirements.txt
```

## CLI tools

- `t2p_convert input.svg [output.svg] [--precision N]` – convert text to paths; fails if any text remains or font is missing.
- `t2p_compare ref.svg ours.svg [--inkscape-svg ref_paths.svg] [--history-dir ./history] [--no-html]` – render+diff PNGs (Inkscape backend) and optional HTML summary.
- Diagnostics: `t2p_font_report`, `t2p_font_report_html`, `t2p_analyze_path`, `t2p_text_flow_test`.

## Current status (2025-11-21)
- Advanced sample diff: **7.99%** vs original (target ~0.2% like Inkscape reference at 0.1977%).
- Recent work: per-line chunk traversal fixed, textPath tangent placement, anchor pre-scaling removed. Remaining issues likely in RTL/inline-size flow and per-glyph dx/dy handling.

## Requirements
- `fonttools`, `python-bidi`, `uharfbuzz`
- Fontconfig (`fc-match`, `fc-list`) available on PATH
- `inkscape` for rendering/diff, `magick` optional for quick JPEG previews
