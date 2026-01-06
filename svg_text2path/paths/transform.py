"""SVG transform matrix parsing and application.

This module handles SVG transform attribute parsing and application to path coordinates.
Supports matrix(), translate(), and scale() transforms.
"""

import re


def parse_svg_transform(transform_str: str) -> tuple[float, float]:
    """Parse SVG transform attribute and return scale values."""
    if not transform_str:
        return (1.0, 1.0)

    # Parse scale(sx, sy) or scale(s)
    scale_match = re.search(
        r"scale\s*\(\s*([-+]?\d*\.?\d+)\s*(?:,\s*([-+]?\d*\.?\d+))?\s*\)", transform_str
    )
    if scale_match:
        sx = float(scale_match.group(1))
        sy = float(scale_match.group(2)) if scale_match.group(2) else sx
        return (sx, sy)

    # Parse matrix(a, b, c, d, e, f) - extract scale from a and d
    matrix_match = re.search(
        r"matrix\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,",
        transform_str,
    )
    if matrix_match:
        a = float(matrix_match.group(1))  # x-scale
        d = float(matrix_match.group(4))  # y-scale
        return (a, d)

    return (1.0, 1.0)


def parse_transform_matrix(
    transform_str: str,
) -> tuple[float, float, float, float, float, float] | None:
    """Parse SVG transform list into a single affine matrix (a,b,c,d,e,f).

    Supports matrix(), translate(), scale(). Returns None if unsupported
    transforms (rotate/skew) are present.
    """
    if not transform_str:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def mat_mul(
        m1: tuple[float, float, float, float, float, float],
        m2: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float]:
        a1, b1, c1, d1, e1, f1 = m1
        a2, b2, c2, d2, e2, f2 = m2
        return (
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    # Simple parser left-to-right
    for part in re.finditer(r"(matrix|translate|scale)\s*\(([^)]*)\)", transform_str):
        kind = part.group(1)
        nums = [
            float(x)
            for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", part.group(2))
        ]
        if kind == "matrix" and len(nums) == 6:
            m = mat_mul(m, (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5]))
        elif kind == "translate" and len(nums) >= 1:
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            m = mat_mul(m, (1.0, 0.0, 0.0, 1.0, tx, ty))
        elif kind == "scale" and len(nums) >= 1:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            m = mat_mul(m, (sx, 0.0, 0.0, sy, 0.0, 0.0))
        else:
            return None

    # If unsupported transforms appear (rotate/skew), bail out
    if re.search(r"rotate|skew", transform_str):
        return None

    return m


def apply_transform_to_path(path_d: str, scale_x: float, scale_y: float) -> str:
    """Apply scale transform to all coordinates in path data."""
    if scale_x == 1.0 and scale_y == 1.0:
        return path_d

    def scale_numbers(match: re.Match[str]) -> str:
        num = float(match.group(0))
        # Determine if this is an x or y coordinate based on position in string
        # This is approximate but works for our use case
        return f"{num:.2f}"

    # Split path into commands and coordinates
    result = []
    parts = re.split(r"([MLHVCSQTAZ])", path_d, flags=re.IGNORECASE)

    for part in parts:
        if not part or part.isspace():
            continue

        if part.upper() in "MLHVCSQTAZ":
            result.append(part)
        else:
            # This is a coordinate string
            coords = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", part)]
            scaled = []
            for j, val in enumerate(coords):
                if j % 2 == 0:  # x coordinate
                    scaled.append(val * scale_x)
                else:  # y coordinate
                    scaled.append(val * scale_y)
            result.append(" ".join(f"{v:.2f}" for v in scaled))

    return " ".join(result)


def _mat_mul(
    m1: tuple[float, float, float, float, float, float],
    m2: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    """Matrix multiplication helper for affine transforms."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _mat_apply_pt(
    m: tuple[float, float, float, float, float, float], x: float, y: float
) -> tuple[float, float]:
    """Apply matrix to point."""
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_scale_lengths(m: tuple[float, float, float, float, float, float]) -> float:
    """Return average scale from matrix for length attributes."""
    a, b, c, d, e, f = m
    sx = (a * a + b * b) ** 0.5
    sy = (c * c + d * d) ** 0.5
    return (sx + sy) / 2.0 if (sx or sy) else 1.0
