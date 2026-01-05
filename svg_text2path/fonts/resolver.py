#!/usr/bin/env python3
"""
Font resolution utilities.

This module provides helper functions for resolving fonts based on various criteria,
including proprietary font replacement and generic family fallback chains.
"""

# Default font replacements (proprietary -> libre equivalent)
DEFAULT_REPLACEMENTS: dict[str, str] = {
    "Arial": "Liberation Sans",
    "Helvetica": "Liberation Sans",
    "Times New Roman": "Liberation Serif",
    "Times": "Liberation Serif",
    "Courier New": "Liberation Mono",
    "Courier": "Liberation Mono",
    "Georgia": "DejaVu Serif",
    "Verdana": "DejaVu Sans",
    "Trebuchet MS": "DejaVu Sans",
    "Impact": "Noto Sans Display",
    "Comic Sans MS": "Comic Neue",
}

# Fallback chains for generic families
DEFAULT_FALLBACKS: dict[str, list[str]] = {
    "sans-serif": ["Liberation Sans", "DejaVu Sans", "Noto Sans", "FreeSans"],
    "serif": ["Liberation Serif", "DejaVu Serif", "Noto Serif", "FreeSerif"],
    "monospace": ["Liberation Mono", "DejaVu Sans Mono", "Noto Sans Mono", "FreeMono"],
    "cursive": ["Comic Neue", "URW Chancery L"],
    "fantasy": ["URW Bookman L", "Century Schoolbook L"],
}


def get_replacement(
    font_name: str, replacements: dict[str, str] | None = None
) -> str | None:
    """Get replacement font for a proprietary font name.

    Args:
        font_name: The font name to find replacement for
        replacements: Custom replacement mapping, defaults to DEFAULT_REPLACEMENTS

    Returns:
        Replacement font name or None if no replacement defined.
    """
    if replacements is None:
        replacements = DEFAULT_REPLACEMENTS

    # Case-insensitive lookup
    font_name_lower = font_name.lower()
    for key, value in replacements.items():
        if key.lower() == font_name_lower:
            return value

    return None


def get_fallback_chain(
    generic_family: str, fallbacks: dict[str, list[str]] | None = None
) -> list[str]:
    """Get fallback chain for a generic font family.

    Args:
        generic_family: The generic font family name (e.g., "sans-serif", "serif")
        fallbacks: Custom fallback mapping, defaults to DEFAULT_FALLBACKS

    Returns:
        List of font names to try in order, empty list if no fallbacks defined.
    """
    if fallbacks is None:
        fallbacks = DEFAULT_FALLBACKS

    # Case-insensitive lookup
    generic_family_lower = generic_family.lower()
    for key, value in fallbacks.items():
        if key.lower() == generic_family_lower:
            return value

    return []


def resolve_font(
    font_name: str,
    available_fonts: set[str],
    replacements: dict[str, str] | None = None,
    fallbacks: dict[str, list[str]] | None = None,
) -> str | None:
    """Resolve a font name to an available font.

    Tries in order:
    1. Original font name
    2. Replacement font
    3. Fallback chain (if font_name is generic family)

    Args:
        font_name: The font name to resolve
        available_fonts: Set of available font names
        replacements: Custom replacement mapping, defaults to DEFAULT_REPLACEMENTS
        fallbacks: Custom fallback mapping, defaults to DEFAULT_FALLBACKS

    Returns:
        Resolved font name or None if no match found.
    """
    # Create case-insensitive lookup for available fonts
    available_fonts_lower = {f.lower(): f for f in available_fonts}

    # 1. Try original font name (case-insensitive)
    font_name_lower = font_name.lower()
    if font_name_lower in available_fonts_lower:
        return available_fonts_lower[font_name_lower]

    # 2. Try replacement font
    replacement = get_replacement(font_name, replacements)
    if replacement:
        replacement_lower = replacement.lower()
        if replacement_lower in available_fonts_lower:
            return available_fonts_lower[replacement_lower]

    # 3. Try fallback chain (if font_name is generic family)
    fallback_chain = get_fallback_chain(font_name, fallbacks)
    for fallback_font in fallback_chain:
        fallback_font_lower = fallback_font.lower()
        if fallback_font_lower in available_fonts_lower:
            return available_fonts_lower[fallback_font_lower]

    # No match found
    return None
