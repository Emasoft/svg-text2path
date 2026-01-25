"""BiDi (Bidirectional) text handling.

Implements Unicode BiDi algorithm support for proper handling of
mixed left-to-right and right-to-left text (Arabic, Hebrew, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from bidi.algorithm import (
        get_base_level,
        get_display,
        get_embedding_levels,
        get_empty_storage,
    )
except ImportError as e:
    raise ImportError(
        "python-bidi is required for BiDi support. "
        "Install with: uv pip install python-bidi"
    ) from e


@dataclass
class BiDiRun:
    """A run of text with consistent direction."""

    text: str
    start: int  # Start index in original string
    end: int  # End index in original string
    level: int  # BiDi embedding level (even=LTR, odd=RTL)
    direction: str  # "ltr" or "rtl"


def apply_bidi_algorithm(text: str, base_direction: str = "auto") -> str:
    """Apply Unicode BiDi algorithm to get visual ordering.

    Args:
        text: Text to reorder
        base_direction: Base direction ("ltr", "rtl", or "auto")

    Returns:
        Text in visual order (ready for display)
    """
    if not text:
        return text

    # Determine base direction
    if base_direction == "auto":
        # Auto-detect from first strong character
        base_dir = None
    elif base_direction == "rtl":
        base_dir = "R"
    else:
        base_dir = "L"

    result: str = get_display(text, base_dir=base_dir)  # type: ignore[reportAssignmentType]
    return result


def get_bidi_runs(text: str, base_direction: str = "auto") -> list[BiDiRun]:
    """Split text into runs with consistent direction.

    Each run contains characters that should be shaped together
    with the same direction.

    Args:
        text: Text to analyze
        base_direction: Base direction ("ltr", "rtl", or "auto")

    Returns:
        List of BiDiRun objects
    """
    if not text:
        return []

    # Get embedding levels for each character using python-bidi
    # python-bidi requires a properly initialized storage dict
    storage = get_empty_storage()
    storage["base_level"] = get_base_level(text)

    # get_embedding_levels populates storage['chars'] with level info
    get_embedding_levels(text, storage)

    # Extract levels from the populated storage
    chars = storage.get("chars", [])
    if not chars:
        # Fallback: treat as single LTR run
        return [BiDiRun(text=text, start=0, end=len(text), level=0, direction="ltr")]

    levels = [ch["level"] for ch in chars]

    runs: list[BiDiRun] = []
    if not levels:
        # Fallback: treat as single LTR run
        return [BiDiRun(text=text, start=0, end=len(text), level=0, direction="ltr")]

    # Group consecutive characters with same level
    current_start = 0
    current_level = levels[0]

    for i, level in enumerate(levels[1:], 1):
        if level != current_level:
            # End current run
            run_text = text[current_start:i]
            direction = "rtl" if current_level % 2 == 1 else "ltr"
            runs.append(
                BiDiRun(
                    text=run_text,
                    start=current_start,
                    end=i,
                    level=current_level,
                    direction=direction,
                )
            )
            current_start = i
            current_level = level

    # Add final run
    run_text = text[current_start:]
    direction = "rtl" if current_level % 2 == 1 else "ltr"
    runs.append(
        BiDiRun(
            text=run_text,
            start=current_start,
            end=len(text),
            level=current_level,
            direction=direction,
        )
    )

    return runs


def get_visual_runs(text: str, base_direction: str = "auto") -> list[BiDiRun]:
    """Get runs in visual order (left-to-right on screen).

    This reorders runs according to the BiDi algorithm so they
    appear in the correct visual sequence.

    Args:
        text: Text to analyze
        base_direction: Base direction

    Returns:
        List of BiDiRun objects in visual order
    """
    runs = get_bidi_runs(text, base_direction)

    if not runs:
        return runs

    # Get maximum embedding level
    max_level = max(run.level for run in runs)

    # Reorder runs according to BiDi algorithm
    # L2: From highest level to lowest, reverse runs at that level
    for level in range(max_level, 0, -1):
        i = 0
        while i < len(runs):
            # Find start of sequence at this level or higher
            if runs[i].level >= level:
                start = i
                # Find end of sequence
                while i < len(runs) and runs[i].level >= level:
                    i += 1
                # Reverse this sequence
                runs[start:i] = reversed(runs[start:i])
            else:
                i += 1

    return runs


def is_rtl_script(text: str) -> bool:
    """Check if text contains primarily RTL script characters.

    Args:
        text: Text to check

    Returns:
        True if text is primarily RTL
    """
    rtl_count = 0
    ltr_count = 0

    for char in text:
        code = ord(char)
        # Arabic range
        if (
            0x0600 <= code <= 0x06FF
            or 0x0750 <= code <= 0x077F
            or 0x0590 <= code <= 0x05FF
        ):
            rtl_count += 1
        # Latin/common LTR
        elif 0x0041 <= code <= 0x007A:
            ltr_count += 1

    return rtl_count > ltr_count


def detect_base_direction(text: str) -> str:
    """Detect the base direction for text.

    Uses the first strong directional character to determine
    the paragraph direction.

    Args:
        text: Text to analyze

    Returns:
        "ltr" or "rtl"
    """
    for char in text:
        code = ord(char)
        # RTL scripts
        if (
            0x0590 <= code <= 0x05FF  # Hebrew
            or 0x0600 <= code <= 0x06FF  # Arabic
            or 0x0750 <= code <= 0x077F  # Arabic Supplement
            or 0x08A0 <= code <= 0x08FF  # Arabic Extended-A
        ):
            return "rtl"
        # LTR scripts (Latin, etc.)
        if 0x0041 <= code <= 0x007A or 0x00C0 <= code <= 0x024F:
            return "ltr"

    return "ltr"  # Default
