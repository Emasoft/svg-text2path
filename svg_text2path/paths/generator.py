"""Glyph outline to SVG path conversion utilities."""

import re
from typing import Any


def recording_pen_to_svg_path(
    recording: list[tuple[str, tuple[Any, ...]]], precision: int = 28
) -> str:
    """Convert RecordingPen recording to SVG path commands.

    Precision is configurable; default 28 for maximum fidelity
    (matching previous behavior).
    """
    fmt = f"{{:.{precision}f}}"
    commands = []

    for op, args in recording:
        if op == "moveTo":
            x, y = args[0]
            commands.append(f"M {fmt.format(x)} {fmt.format(y)}")
        elif op == "lineTo":
            x, y = args[0]
            commands.append(f"L {fmt.format(x)} {fmt.format(y)}")
        elif op == "qCurveTo":
            # TrueType quadratic Bezier curve(s)
            # qCurveTo can have multiple points: (cp1, cp2, ..., cpN, end)
            # If more than 2 points, there are implied on-curve points
            # halfway between control points
            if len(args) == 2:
                # Simple case: one control point + end point
                x1, y1 = args[0]
                x, y = args[1]
                q_cmd = f"Q {fmt.format(x1)} {fmt.format(y1)}"
                q_cmd += f" {fmt.format(x)} {fmt.format(y)}"
                commands.append(q_cmd)
            else:
                # Multiple control points - need to add implied on-curve points
                # Last point is the end point, others are control points
                for i in range(len(args) - 1):
                    x1, y1 = args[i]
                    if i == len(args) - 2:
                        # Last control point - use actual end point
                        x, y = args[i + 1]
                    else:
                        # Implied on-curve point halfway to next control point
                        x2, y2 = args[i + 1]
                        x, y = (x1 + x2) / 2, (y1 + y2) / 2
                    q_cmd = f"Q {fmt.format(x1)} {fmt.format(y1)}"
                    q_cmd += f" {fmt.format(x)} {fmt.format(y)}"
                    commands.append(q_cmd)
        elif op == "curveTo":
            # Cubic Bezier curve
            if len(args) >= 3:
                x1, y1 = args[0]
                x2, y2 = args[1]
                x, y = args[2]
                c_cmd = f"C {fmt.format(x1)} {fmt.format(y1)}"
                c_cmd += f" {fmt.format(x2)} {fmt.format(y2)}"
                c_cmd += f" {fmt.format(x)} {fmt.format(y)}"
                commands.append(c_cmd)
        elif op == "closePath":
            commands.append("Z")

    return " ".join(commands)


def _parse_num_list(val: str) -> list[float]:
    """Parse a list of numbers from an SVG attribute (space/comma separated)."""
    nums: list[float] = []
    for part in re.split(r"[ ,]+", val.strip()):
        if part == "":
            continue
        try:
            nums.append(float(part))
        except Exception:
            continue
    return nums


# Alias for backward compatibility and clearer API
glyph_to_path = recording_pen_to_svg_path
