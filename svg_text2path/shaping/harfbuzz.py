"""HarfBuzz text shaping wrapper.

Provides text shaping for proper ligatures, contextual forms,
and complex script handling (Arabic, Devanagari, etc.).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import uharfbuzz as hb  # type: ignore[import-untyped]


@dataclass
class ShapedGlyph:
    """Result of shaping a single glyph."""

    glyph_id: int
    cluster: int
    x_advance: float
    y_advance: float
    x_offset: float
    y_offset: float
    codepoint: int | None = None


@dataclass
class ShapingResult:
    """Result of shaping a text run."""

    glyphs: list[ShapedGlyph]
    direction: str  # "ltr" or "rtl"
    script: str
    language: str | None


def create_hb_font(
    font_blob: bytes,
    font_index: int = 0,
    font_size: float = 16.0,
    variations: dict[str, float] | None = None,
) -> Any:
    """Create a HarfBuzz font from font data.

    Args:
        font_blob: Font file bytes
        font_index: Face index for TTC/OTC collections
        font_size: Font size in pixels
        variations: Optional font variation settings (e.g., {"wght": 700})

    Returns:
        HarfBuzz Font object
    """
    blob = hb.Blob(font_blob)  # type: ignore[attr-defined]
    face = hb.Face(blob, font_index)  # type: ignore[attr-defined]
    font = hb.Font(face)  # type: ignore[attr-defined]

    # Scale is in 26.6 fixed-point format (multiply by 64)
    scale = int(font_size * 64)
    font.scale = (scale, scale)

    if variations:
        with contextlib.suppress(Exception):
            font.set_variations(variations)

    return font


def shape_text(
    text: str,
    font_blob: bytes,
    font_index: int = 0,
    font_size: float = 16.0,
    direction: str | None = None,
    script: str | None = None,
    language: str | None = None,
    features: dict[str, bool] | None = None,
    variations: dict[str, float] | None = None,
) -> ShapingResult:
    """Shape text using HarfBuzz.

    Args:
        text: Text to shape
        font_blob: Font file bytes
        font_index: Face index for TTC/OTC collections
        font_size: Font size in pixels
        direction: Text direction ("ltr" or "rtl"), auto-detected if None
        script: Script tag (e.g., "Latn", "Arab"), auto-detected if None
        language: Language tag (e.g., "en", "ar"), auto-detected if None
        features: OpenType features to enable/disable
        variations: Font variation settings

    Returns:
        ShapingResult with shaped glyphs
    """
    hb_font = create_hb_font(font_blob, font_index, font_size, variations)

    # Create buffer
    buf = hb.Buffer()  # type: ignore[attr-defined]
    buf.add_str(text)

    # Set direction (uharfbuzz uses string values for direction)
    if direction:
        buf.direction = "rtl" if direction == "rtl" else "ltr"
    else:
        buf.guess_segment_properties()

    # Set script if provided
    if script:
        with contextlib.suppress(Exception):
            buf.script = script

    # Set language if provided
    if language:
        with contextlib.suppress(Exception):
            buf.language = language

    # Build features dict
    hb_features = {}
    if features:
        for feature, enabled in features.items():
            hb_features[feature] = enabled

    # Shape the text
    hb.shape(hb_font, buf, hb_features)  # type: ignore[attr-defined]

    # Extract results
    infos = buf.glyph_infos
    positions = buf.glyph_positions

    glyphs: list[ShapedGlyph] = []
    for info, pos in zip(infos, positions, strict=True):
        glyphs.append(
            ShapedGlyph(
                glyph_id=info.codepoint,
                cluster=info.cluster,
                x_advance=pos.x_advance / 64.0,  # Convert from 26.6 fixed-point
                y_advance=pos.y_advance / 64.0,
                x_offset=pos.x_offset / 64.0,
                y_offset=pos.y_offset / 64.0,
            )
        )

    # Determine final direction (direction is already a string in uharfbuzz)
    final_direction = buf.direction if buf.direction in ("ltr", "rtl") else "ltr"

    return ShapingResult(
        glyphs=glyphs,
        direction=final_direction,
        script=str(buf.script) if buf.script else "Zyyy",
        language=str(buf.language) if buf.language else None,
    )


def shape_run(
    text: str,
    hb_font: Any,
    direction: str = "ltr",
    script: str | None = None,
    language: str | None = None,
    features: dict[str, bool] | None = None,
) -> list[ShapedGlyph]:
    """Shape a single text run with an existing HarfBuzz font.

    This is a lower-level function for when you've already created
    a HarfBuzz font and want to shape multiple runs with it.

    Args:
        text: Text to shape
        hb_font: Pre-created HarfBuzz font
        direction: Text direction
        script: Script tag
        language: Language tag
        features: OpenType features

    Returns:
        List of shaped glyphs
    """
    buf = hb.Buffer()  # type: ignore[attr-defined]
    buf.add_str(text)
    # uharfbuzz uses string values for direction
    buf.direction = "rtl" if direction == "rtl" else "ltr"

    if script:
        with contextlib.suppress(Exception):
            buf.script = script

    if language:
        with contextlib.suppress(Exception):
            buf.language = language

    hb_features = {}
    if features:
        for feature, enabled in features.items():
            hb_features[feature] = enabled

    hb.shape(hb_font, buf, hb_features)  # type: ignore[attr-defined]

    infos = buf.glyph_infos
    positions = buf.glyph_positions

    glyphs: list[ShapedGlyph] = []
    for info, pos in zip(infos, positions, strict=True):
        glyphs.append(
            ShapedGlyph(
                glyph_id=info.codepoint,
                cluster=info.cluster,
                x_advance=pos.x_advance / 64.0,
                y_advance=pos.y_advance / 64.0,
                x_offset=pos.x_offset / 64.0,
                y_offset=pos.y_offset / 64.0,
            )
        )

    return glyphs
