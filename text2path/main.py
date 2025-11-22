#!/usr/bin/env python3
"""
Text-to-Path Converter V4

Key features:
- Unicode BiDi support for RTL text (Arabic, Hebrew)
- HarfBuzz text shaping for proper ligatures and contextual forms
- Visual run processing like the Rust version
- Transform attribute handling to avoid rendering differences
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import sys
import re
import math
from dataclasses import dataclass
try:
    from svg.path import parse_path
except ImportError:
    print("Error: svg.path is required. Install with:")
    print("  pip install svg.path")
    sys.exit(1)


def parse_svg_transform(transform_str):
    """Parse SVG transform attribute and return scale values."""
    if not transform_str:
        return (1.0, 1.0)

    # Parse scale(sx, sy) or scale(s)
    scale_match = re.search(r'scale\s*\(\s*([-+]?\d*\.?\d+)\s*(?:,\s*([-+]?\d*\.?\d+))?\s*\)', transform_str)
    if scale_match:
        sx = float(scale_match.group(1))
        sy = float(scale_match.group(2)) if scale_match.group(2) else sx
        return (sx, sy)

    # Parse matrix(a, b, c, d, e, f) - extract scale from a and d
    matrix_match = re.search(r'matrix\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,', transform_str)
    if matrix_match:
        a = float(matrix_match.group(1))  # x-scale
        d = float(matrix_match.group(4))  # y-scale
        return (a, d)

    return (1.0, 1.0)


def parse_transform_matrix(transform_str: str) -> tuple[float, float, float, float, float, float] | None:
    """Parse SVG transform list into a single affine matrix (a,b,c,d,e,f).

    Supports matrix(), translate(), scale(). Returns None if unsupported
    transforms (rotate/skew) are present.
    """
    if not transform_str:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def mat_mul(m1, m2):
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
    for part in re.finditer(r'(matrix|translate|scale)\s*\(([^)]*)\)', transform_str):
        kind = part.group(1)
        nums = [float(x) for x in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', part.group(2))]
        if kind == 'matrix' and len(nums) == 6:
            m = mat_mul(m, tuple(nums))
        elif kind == 'translate' and len(nums) >= 1:
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            m = mat_mul(m, (1.0, 0.0, 0.0, 1.0, tx, ty))
        elif kind == 'scale' and len(nums) >= 1:
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            m = mat_mul(m, (sx, 0.0, 0.0, sy, 0.0, 0.0))
        else:
            return None

    # If unsupported transforms appear (rotate/skew), bail out
    if re.search(r'rotate|skew', transform_str):
        return None

    return m


def apply_transform_to_path(path_d, scale_x, scale_y):
    """Apply scale transform to all coordinates in path data."""
    if scale_x == 1.0 and scale_y == 1.0:
        return path_d

    def scale_numbers(match):
        num = float(match.group(0))
        # Determine if this is an x or y coordinate based on position in string
        # This is approximate but works for our use case
        return f'{num:.2f}'

    # Split path into commands and coordinates
    result = []
    parts = re.split(r'([MLHVCSQTAZ])', path_d, flags=re.IGNORECASE)

    for i, part in enumerate(parts):
        if not part or part.isspace():
            continue

        if part.upper() in 'MLHVCSQTAZ':
            result.append(part)
        else:
            # This is a coordinate string
            coords = [float(x) for x in re.findall(r'[-+]?\d*\.?\d+', part)]
            scaled = []
            for j, val in enumerate(coords):
                if j % 2 == 0:  # x coordinate
                    scaled.append(val * scale_x)
                else:  # y coordinate
                    scaled.append(val * scale_y)
            result.append(' '.join(f'{v:.2f}' for v in scaled))

    return ' '.join(result)


def _mat_mul(m1, m2):
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


def _mat_apply_pt(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_scale_lengths(m):
    """Return average scale from matrix for length attributes."""
    a, b, c, d, e, f = m
    sx = (a * a + b * b) ** 0.5
    sy = (c * c + d * d) ** 0.5
    return (sx + sy) / 2.0 if (sx or sy) else 1.0


def flatten_transforms(root):
    """
    Precompute (bake) transforms into coordinates.
    This simplifies anchoring/debugging and avoids inherited transforms shifting text.
    """
    def recurse(el, parent_m):
        # Parse this element transform
        m = parse_transform_matrix(el.get('transform', '')) or (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        combined = _mat_mul(parent_m, m)

        # apply to key attributes
        tag = el.tag.split('}')[-1]
        length_scale = _mat_scale_lengths(combined)

        def _apply_list(attr):
            if attr in el.attrib:
                nums = _parse_num_list(el.get(attr))
                pts = []
                # pair x,y if both, else treat as x list
                if attr in ('dx', 'x'):
                    pts = [(_mat_apply_pt(combined, v, 0.0)[0]) for v in nums]
                elif attr in ('dy', 'y'):
                    pts = [(_mat_apply_pt(combined, 0.0, v)[1]) for v in nums]
                el.set(attr, ' '.join(str(v) for v in pts))

        if tag in ('text', 'tspan', 'textPath'):
            _apply_list('x'); _apply_list('y'); _apply_list('dx'); _apply_list('dy')
            # scale font-size and spacing
            for attr in ('font-size', 'letter-spacing', 'word-spacing', 'stroke-width'):
                if attr in el.attrib:
                    try:
                        val = float(re.findall(r'[-+]?\\d*\\.?\\d+', el.attrib[attr])[0])
                        el.set(attr, str(val * length_scale))
                    except Exception:
                        pass
            el.attrib.pop('transform', None)

        if tag == 'path' and 'd' in el.attrib:
            try:
                p = parse_path(el.get('d'))
                for seg in p:
                    for name in ('start', 'end', 'control', 'control1', 'control2', 'radius'):
                        if hasattr(seg, name):
                            pt = getattr(seg, name)
                            if isinstance(pt, complex):
                                x, y = _mat_apply_pt(combined, pt.real, pt.imag)
                                setattr(seg, name, complex(x, y))
                el.set('d', p.d())
            except Exception:
                pass
            el.attrib.pop('transform', None)

        for ch in list(el):
            recurse(ch, combined)

    recurse(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    # Drop residual transforms to avoid inherited shifts later in the pipeline.
    for el in root.iter():
        if 'transform' in el.attrib:
            el.attrib.pop('transform', None)

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import RecordingPen
except ImportError:
    print("Error: fontTools is required. Install with:")
    print("  uv pip install fonttools")
    sys.exit(1)

try:
    from bidi.algorithm import get_display, get_embedding_levels
    import uharfbuzz as hb
except ImportError:
    print("Error: python-bidi and uharfbuzz are required. Install with:")
    print("  uv pip install python-bidi uharfbuzz")
    sys.exit(1)


@dataclass
class MissingFontError(Exception):
    family: str
    weight: int
    style: str
    stretch: str
    message: str


class FontCache:
    """Cache loaded fonts using fontconfig for proper font matching."""

    def __init__(self):
        self._fonts: dict[str, tuple[TTFont, bytes, int]] = {}  # Cache: font_spec -> (TTFont, bytes, face_index)

    def _parse_inkscape_spec(self, inkscape_spec: str) -> tuple[str, str | None]:
        """Parse Inkscape font specification like 'Futura, Medium' or '.New York, Italic'."""
        s = inkscape_spec.strip().strip("'\"")
        if ',' in s:
            family, rest = s.split(',', 1)
            return family.strip(), rest.strip() or None
        else:
            return s, None

    def _weight_to_style(self, weight: int) -> str | None:
        """Map CSS font-weight to font style name.

        This is needed because some fonts (like Futura) use style names
        instead of numeric weights in fontconfig.
        """
        weight_map = {
            100: 'Thin',
            200: 'ExtraLight',
            300: 'Light',
            400: 'Regular',
            500: 'Medium',
            600: 'SemiBold',
            700: 'Bold',
            800: 'ExtraBold',
            900: 'Black'
        }
        return weight_map.get(weight)

    _fc_cache: list[tuple[Path, list[str], list[str], str]] | None = None

    def _load_fc_cache(self):
        """Load fontconfig list once, caching tuples (path, families, styles, postscript)."""
        if self._fc_cache is not None:
            return
        import subprocess
        entries = []
        try:
            result = subprocess.run(
                ['fc-list', '--format=%{file}:%{family}:%{style}:%{postscriptname}\\n'],
                capture_output=True,
                text=True,
                timeout=8
            )
            if result.returncode != 0:
                self._fc_cache = []
                return
            for line in result.stdout.splitlines():
                if ':' not in line:
                    continue
                parts = line.split(':')
                if len(parts) < 3:
                    continue
                path_str, fam_str, style_str, ps_name = parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ''
                p = Path(path_str.strip())
                if not p.exists():
                    continue
                fams = [f.strip().lower() for f in fam_str.split(',') if f.strip()]
                styles = [s.strip().lower() for s in style_str.split(',') if s.strip()]
                entries.append((p, fams, styles, ps_name.strip().lower()))
        except Exception:
            entries = []
        self._fc_cache = entries


    def _split_words(self, name: str) -> set[str]:
        """Split a font name into lowercase word tokens (camelCase, underscores, spaces)."""
        import re
        tokens = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        tokens = tokens.replace('_', ' ')
        parts = [p.strip().lower() for p in tokens.split() if p.strip()]
        return set(parts)

    def _style_weight_class(self, styles: list[str]) -> int:
        """Rough weight class from style tokens."""
        s = ' '.join(styles)
        if any(tok in s for tok in ['black', 'heavy', 'ultra', 'extra bold']):
            return 800
        if 'bold' in s:
            return 700
        if any(tok in s for tok in ['semi', 'demi']):
            return 600
        if any(tok in s for tok in ['light', 'thin', 'hair']):
            return 300
        return 400

    def _style_slant(self, styles: list[str]) -> str:
        s = ' '.join(styles)
        if 'italic' in s or 'oblique' in s:
            return 'italic'
        return 'normal'

    def _normalize_style_name(self, name: str) -> str:
        n = name.lower().strip()
        # Inkscape canonicalization
        n = n.replace("semi-light", "light")
        n = n.replace("book", "normal")
        n = n.replace("ultra-heavy", "heavy")
        # Treat Medium/Regular/Plain as Normal
        n = n.replace("medium", "normal")
        if n in ("regular", "plain", "roman"):
            n = "normal"
        return n

    def _style_token_set(self, style_str: str) -> set[str]:
        tokens = re.sub(r'([a-z])([A-Z])', r'\1 \2', style_str)
        tokens = tokens.replace('-', ' ').replace('_', ' ')
        parts = [self._normalize_style_name(p) for p in tokens.split() if p.strip()]
        return set(parts)

    def _build_style_label(self, weight: int, style: str, stretch: str = 'normal') -> str:
        base = []
        # weight
        if weight >= 800:
            base.append("heavy")
        elif weight >= 700:
            base.append("bold")
        elif weight >= 600:
            base.append("semibold")
        elif weight >= 500:
            base.append("medium")
        elif weight <= 300:
            base.append("light")
        else:
            base.append("normal")
        # slant
        st = style.lower()
        if st in ("italic", "oblique"):
            base.append("italic")
        elif st not in ("normal", ""):
            base.append(st)
        # stretch
        if stretch and stretch.lower() not in ("normal", ""):
            base.append(stretch.lower())
        return ' '.join(base)

    def _match_exact(self, font_family: str, weight: int, style: str, stretch: str, ps_hint: str | None) -> tuple[Path, int] | None:
        """Strict match: family must exist; weight/style must match token sets; no substitution."""
        self._load_fc_cache()
        fam_norm = font_family.strip().lower()
        ps_norm = ps_hint.strip().lower() if ps_hint else None
        desired_style_tokens = self._style_token_set(self._build_style_label(weight, style, stretch))

        fallback_candidate = None
        for path, fams, styles, ps in self._fc_cache:
            fam_hit = any(fam_norm == f or fam_norm.lstrip('.') == f.lstrip('.') for f in fams) or fam_norm == ps or fam_norm.lstrip('.') == ps.lstrip('.')
            ps_hit = ps_norm and ps_norm == ps
            if not fam_hit and not ps_hit:
                continue
            for st in styles or ['normal']:
                st_tokens = self._style_token_set(st)
                if desired_style_tokens.issubset(st_tokens):
                    return (path, 0)
        return None

    def _match_font_with_fc(self, font_family: str, weight: int = 400, style: str = 'normal', stretch: str = 'normal') -> tuple[Path, int] | None:
        """Use fontconfig to match fonts exactly as browsers do.

        Args:
            font_family: Font family name
            weight: CSS font-weight (100-900)
            style: CSS font-style ('normal', 'italic', 'oblique')
            stretch: CSS font-stretch ('normal', 'condensed', etc.')

        Returns:
            (font_file_path, font_number) tuple, or None
        """
        import subprocess

        def stretch_token(stretch: str) -> str | None:
            s = stretch.lower()
            mapping = {
                'ultra-condensed': 'ultracondensed',
                'extra-condensed': 'extracondensed',
                'condensed': 'condensed',
                'semi-condensed': 'semicondensed',
                'normal': None,
                'semi-expanded': 'semiexpanded',
                'expanded': 'expanded',
                'extra-expanded': 'extraexpanded',
                'ultra-expanded': 'ultraexpanded',
            }
            return mapping.get(s)

        # Build candidate patterns from specific to generic to prefer Regular when available
        style_name = self._weight_to_style(weight)
        patterns = []
        if weight == 400 and style == 'normal':
            patterns.append(f"{font_family}:style=Regular:weight=400")
        if weight == 400 and style == 'italic':
            patterns.append(f"{font_family}:style=Italic:weight=400:slant=italic")
        if style_name and weight != 400:
            patterns.append(f"{font_family}:style={style_name}")
        if weight != 400:
            patterns.append(f"{font_family}:weight={weight}")

        base = f"{font_family}"
        if style == 'italic':
            base += ":slant=italic"
        elif style == 'oblique':
            base += ":slant=oblique"
        st_tok = stretch_token(stretch)
        if st_tok:
            base += f":width={st_tok}"
        if stretch != 'normal':
            base += f":width={stretch}"
        patterns.append(base)

        # Special-case Arial regular to avoid Bold fallback on some systems
        if font_family.lower() == 'arial' and weight == 400 and style == 'normal':
            patterns.insert(0, "Arial:style=Regular")

        for pattern in patterns:
            try:
                result = subprocess.run(
                    ['fc-match', '--format=%{file}\\n%{index}', pattern],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        font_file = Path(lines[0])
                        font_index = int(lines[1]) if lines[1].isdigit() else 0
                        if font_file.exists():
                            return (font_file, font_index)
            except Exception as e:
                continue

        return None

    def get_font(self, font_family: str, weight: int = 400, style: str = 'normal', stretch: str = 'normal', inkscape_spec: str | None = None, strict_family: bool = True):
        """Load font strictly; if exact face not found, return None (caller must abort unless strict_family=False).

        Args:
            font_family: Font family name
            weight: CSS font-weight (100-900)
            style: CSS font-style
            stretch: CSS font-stretch
            inkscape_spec: Optional Inkscape font specification hint (e.g., 'Futura Medium')

        Returns:
            (TTFont, font_blob_bytes, face_index) or None
        """
        # Normalize generic Pango family names to CSS generics (but do NOT substitute specific faces)
        generic_map = {
            'sans': 'sans-serif',
            'sans-serif': 'sans-serif',
            'serif': 'serif',
            'monospace': 'monospace',
            'mono': 'monospace',
        }
        font_family = generic_map.get(font_family.strip().lower(), font_family.strip())

        cache_key = f"{font_family}:{weight}:{style}:{stretch}:{inkscape_spec}".lower()

        if cache_key not in self._fonts:
            match_result = None
            ink_ps = None
            if inkscape_spec:
                ink_family, ink_style = self._parse_inkscape_spec(inkscape_spec)
                font_family = ink_family or font_family
                if ink_style:
                    style = ink_style
            # strict exact match from fc cache by family/style/postscript
            match_result = self._match_exact(font_family, weight, style, stretch, ink_ps)

            if match_result is None:
                # Fallback to fontconfig best match (non-strict) to honor installed fonts
                match_result = self._match_font_with_fc(font_family, weight, style, stretch)
            if match_result is None and font_family in ("sans-serif", "sans"):
                match_result = self._match_font_with_fc("sans", weight, style, stretch)
            if match_result is None:
                return None

            font_path, font_index = match_result

            try:
                # Load font
                if font_index > 0 or str(font_path).endswith('.ttc'):
                    ttfont = TTFont(font_path, fontNumber=font_index)
                else:
                    ttfont = TTFont(font_path)

                with open(font_path, 'rb') as f:
                    font_blob = f.read()

                # Verify family match strictly against name table
                def _name(tt, ids):
                    for nid in ids:
                        for rec in tt["name"].names:
                            if rec.nameID == nid:
                                try:
                                    return str(rec.toUnicode()).strip().lower()
                                except Exception:
                                    return str(rec.string, errors="ignore").strip().lower()
                    return None

                fam_candidate = (_name(ttfont, [16, 1]) or _name(ttfont, [1]) or "").lower()
                sub_candidate = (_name(ttfont, [17, 2]) or "").lower()
                def _norm(s: str) -> str:
                    import re
                    return re.sub(r'[^a-z0-9]+', '', s.lower().lstrip('.'))
                if strict_family and font_family.lower() not in ("sans-serif", "sans"):
                    if _norm(fam_candidate) != _norm(font_family):
                        # Allow subset match
                        if _norm(font_family) not in _norm(fam_candidate):
                            print(f"✗ Loaded font '{font_path.name}' but family mismatch ({fam_candidate}) for requested '{font_family}'")
                            return None

                self._fonts[cache_key] = (ttfont, font_blob, font_index)
                print(f"✓ Loaded: {font_family} w={weight} s={style} st={stretch} → {font_path.name}:{font_index}")

            except Exception as e:
                print(f"✗ Failed to load {font_path}:{font_index}: {e}")
                return None

        return self._fonts.get(cache_key)


def recording_pen_to_svg_path(recording, precision: int = 28) -> str:
    """Convert RecordingPen recording to SVG path commands.

    Precision is configurable; default 28 for maximum fidelity (matching previous behavior).
    """
    fmt = f"{{:.{precision}f}}"
    commands = []

    for op, args in recording:
        if op == 'moveTo':
            x, y = args[0]
            commands.append(f"M {fmt.format(x)} {fmt.format(y)}")
        elif op == 'lineTo':
            x, y = args[0]
            commands.append(f"L {fmt.format(x)} {fmt.format(y)}")
        elif op == 'qCurveTo':
            # TrueType quadratic Bezier curve(s)
            # qCurveTo can have multiple points: (cp1, cp2, ..., cpN, end)
            # If more than 2 points, there are implied on-curve points halfway between control points
            if len(args) == 2:
                # Simple case: one control point + end point
                x1, y1 = args[0]
                x, y = args[1]
                commands.append(f"Q {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x)} {fmt.format(y)}")
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
                    commands.append(f"Q {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x)} {fmt.format(y)}")
        elif op == 'curveTo':
            # Cubic Bezier curve
            if len(args) >= 3:
                x1, y1 = args[0]
                x2, y2 = args[1]
                x, y = args[2]
                commands.append(f"C {fmt.format(x1)} {fmt.format(y1)} {fmt.format(x2)} {fmt.format(y2)} {fmt.format(x)} {fmt.format(y)}")
        elif op == 'closePath':
            commands.append("Z")

    return ' '.join(commands)


def _parse_num_list(val: str) -> list[float]:
    """Parse a list of numbers from an SVG attribute (space/comma separated)."""
    nums: list[float] = []
    for part in re.split(r'[ ,]+', val.strip()):
        if part == '':
            continue
        try:
            nums.append(float(part))
        except Exception:
            continue
    return nums


def text_to_path_rust_style(text_elem: ET.Element, font_cache: FontCache, path_obj=None, path_offset=0.0, precision: int = 28, dx_list: list[float] | None = None, dy_list: list[float] | None = None):
    """
    Convert text element to path element.

    Follows the Rust text2path implementation exactly:
    1. Unicode BiDi analysis to get visual runs
    2. HarfBuzz shaping for each run
    3. Glyph positioning from shaper

    Args:
        text_elem: The text element to convert
        font_cache: Font cache
        path_obj: Optional svg.path.Path object for textPath support
        path_offset: Starting offset along the path (in user units)

    Note: Transform attributes are NOT applied during conversion.
    They are copied from the text element to the path element.
    """

    # 1. Extract text content (including from tspan children)
    text_content = text_elem.text or ""

    # If no direct text, check for tspan elements
    if not text_content:
        # Get text from all tspan children
        tspan_texts = []
        for child in text_elem:
            tag = child.tag
            if '}' in tag:
                tag = tag.split('}')[1]
            if tag == 'tspan' and child.text:
                tspan_texts.append(child.text)

        if tspan_texts:
            text_content = ''.join(tspan_texts)  # Join tspans directly without space

    if not text_content:
        print("  ✗ No text content after extracting tspans")
        return None

    # 2. Extract attributes
    def get_attr(elem, key, default=None):
        # Check style string first
        style = elem.get('style', '')
        match = re.search(f'{key}:([^;]+)', style)
        if match:
            return match.group(1).strip()
        # Check direct attribute
        return elem.get(key, default)

    x_attr = text_elem.get('x')
    y_attr = text_elem.get('y')
    dx_attr = text_elem.get('dx')
    dy_attr = text_elem.get('dy')

    # If x/y are missing, they default to 0 in SVG, but for tspans they should flow.
    # However, since we are processing this as an isolated element (for now), 
    # we rely on the caller to handle flow or explicit coordinates.
    x = float(x_attr) if x_attr else 0.0
    y = float(y_attr) if y_attr else 0.0

    # Parse per-glyph dx/dy lists (do NOT pre-apply; handled per-glyph)
    if dx_list is None and dx_attr:
        dx_list = _parse_num_list(dx_attr)
    if dy_list is None and dy_attr:
        dy_list = _parse_num_list(dy_attr)
    
    # Get text alignment
    # Per SVG 2 spec (https://www.w3.org/TR/SVG2/text.html#TextAnchoringProperties):
    # - text-anchor is the ONLY alignment property for SVG text elements
    # - text-align is CSS-only and NOT part of SVG spec for text elements
    # - Valid values: start (default), middle, end
    #
    # However, many SVG authoring tools (including Inkscape) incorrectly use
    # text-align:center instead of text-anchor="middle". Since we're converting
    # to paths anyway, we handle both cases to apply correct alignment regardless
    # of whether the source SVG uses correct or incorrect syntax.
    text_anchor = text_elem.get('text-anchor', 'start')

    # Check for text-align in style (common mistake in SVG authoring tools)
    # Map CSS text-align to SVG text-anchor values
    style = text_elem.get('style', '')
    text_align_match = re.search(r'text-align:\s*(center|left|right)', style)
    if text_align_match and text_anchor == 'start':  # Only use if text-anchor not explicitly set
        text_align_map = {'center': 'middle', 'left': 'start', 'right': 'end'}
        text_anchor = text_align_map.get(text_align_match.group(1), 'start')

    # Precompute transform matrix (may be None if unsupported)
    transform_attr = text_elem.get('transform')
    baked_matrix = parse_transform_matrix(transform_attr) if transform_attr else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    preserve_transform = transform_attr is not None and baked_matrix is None

    # Parse font-family
    raw_font = get_attr(text_elem, 'font-family', 'Arial')
    font_family = raw_font.split(',')[0].strip().strip("'\"")

    # Parse font-size
    raw_size = get_attr(text_elem, 'font-size', '16')
    # Handle units (px is default, pt needs conversion)
    if 'pt' in raw_size:
        font_size = float(re.search(r'([\d.]+)', raw_size).group(1)) * 1.3333
    else:
        font_size = float(re.search(r'([\d.]+)', raw_size).group(1))

    # Spacing
    # IMPORTANT (✱ gain ~50% diff reduction when spacing present):
    # In earlier runs we failed to parse letter/word-spacing like "10" and treated them as 0,
    # causing anchor widths to collapse and large left shifts (e.g., diff 14%→7%). Keep this robust parser.
    raw_letter_spacing = get_attr(text_elem, 'letter-spacing', None)
    letter_spacing = 0.0
    if raw_letter_spacing and raw_letter_spacing != 'normal':
        m_num = re.search(r'([-+]?[\d.]+)', raw_letter_spacing)
        if m_num:
            try:
                letter_spacing = float(m_num.group(1))
            except Exception:
                letter_spacing = 0.0

    raw_word_spacing = get_attr(text_elem, 'word-spacing', None)
    word_spacing = 0.0
    if raw_word_spacing and raw_word_spacing != 'normal':
        m_num = re.search(r'([-+]?[\d.]+)', raw_word_spacing)
        if m_num:
            try:
                word_spacing = float(m_num.group(1))
            except Exception:
                word_spacing = 0.0

    # Parse font-variation settings (optional)
    fv_settings_str = get_attr(text_elem, 'font-variation-settings', None)
    variation_wght = None
    variation_settings: list[tuple[str, float]] = []
    if fv_settings_str:
        for tag, val in re.findall(r"'([A-Za-z0-9]{4})'\\s*([\\d\\.]+)", fv_settings_str):
            try:
                num_val = float(val)
                variation_settings.append((tag, num_val))
                if tag.lower() == 'wght':
                    variation_wght = num_val
            except Exception:
                pass

    # Parse font-weight (use wght variation if present)
    raw_weight = get_attr(text_elem, 'font-weight', '400')
    if raw_weight == 'normal': font_weight = 400
    elif raw_weight == 'bold': font_weight = 700
    else: font_weight = int(re.search(r'(\\d+)', raw_weight).group(1)) if re.search(r'(\\d+)', raw_weight) else 400
    if variation_wght:
        try:
            font_weight = int(max(100, min(900, variation_wght)))
        except Exception:
            pass

    # Parse font-style
    font_style = get_attr(text_elem, 'font-style', 'normal')

    # Parse font-stretch
    font_stretch = get_attr(text_elem, 'font-stretch', 'normal')

    # Extract inkscape-font-specification hint if present
    # This helps with font matching, especially for TTC files where weight matching can fail
    inkscape_spec = get_attr(text_elem, '-inkscape-font-specification', None)
    if inkscape_spec:
        # Clean up: remove quotes and extra info
        inkscape_spec = inkscape_spec.strip("'\"").split(',')[0].strip()

    # Note: We do NOT handle text-anchor/text-align here!
    # The x, y coordinates in the SVG are already positioned correctly by the SVG renderer.
    # Applying text-anchor adjustments would incorrectly shift the glyphs.
    # We just use raw x, y coordinates and copy the transform attribute.
    # The transform attribute (if any) will be copied to the path element later.
    print(f"  ▶ text run '{text_content[:40]}' font={font_family} size={font_size} w={font_weight} style={font_style} stretch={font_stretch} inkscape_spec={inkscape_spec}")

    # 3. Load font using CSS properties (fontconfig matches like browsers do)
    font_data = font_cache.get_font(font_family, weight=font_weight, style=font_style, stretch=font_stretch, inkscape_spec=inkscape_spec)
    if not font_data:
        raise MissingFontError(font_family, font_weight, font_style, font_stretch, f"Font '{font_family}' w={font_weight} s={font_style} st={font_stretch} not found")

    ttfont, font_blob, font_index = font_data

    # Ensure all characters have glyphs in this font
    cmap = ttfont.getBestCmap() or {}
    missing_chars = [ch for ch in text_content if ord(ch) not in cmap or cmap.get(ord(ch), 0) == 0]
    fallback_glyph_set = None
    fallback_scale = None
    fallback_ttfont = None
    fallback_cmap = None
    if missing_chars:
        # Script-based fallback selection (single fallback per run)
        def pick_fallback(chars: list[str]) -> list[str]:
            for ch in chars:
                code = ord(ch)
                if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
                    return [":lang=ar", "Geeza Pro", "Noto Sans Arabic", "Apple Symbols", "Arial Unicode MS", "Last Resort"]
                if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
                    return [":lang=zh-cn", "Hiragino Sans GB", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", "Arial Unicode MS", "Last Resort"]
                if 0x2600 <= code <= 0x27FF or 0x1F300 <= code <= 0x1FAFF:
                    return ["Apple Symbols", "Symbola", "Segoe UI Symbol", "Arial Unicode MS", "Last Resort"]
                if code > 0x1000:
                    return ["Apple Symbols", "Arial Unicode MS", "Last Resort"]
            return ["Apple Symbols", "Arial Unicode MS", "Last Resort"]

        fb_names = pick_fallback(missing_chars)
        fallback_font = None
        fallback_cmap = None
        best_cover = -1
        missing_set = set(missing_chars)

        def coverage(candidate_tt, cmap):
            return sum(1 for ch in missing_set if ord(ch) in cmap and cmap.get(ord(ch), 0) != 0)

        for fb in fb_names:
            candidate = None
            if fb.startswith(":lang="):
                match = font_cache._match_font_with_fc(fb, weight=font_weight, style=font_style, stretch='normal')
                if match:
                    try:
                        fp, findex = match
                        tt = TTFont(fp, fontNumber=findex) if fp.suffix.lower() == '.ttc' or findex > 0 else TTFont(fp)
                        with open(fp, 'rb') as f:
                            fb_blob = f.read()
                        candidate = (tt, fb_blob, findex)
                    except Exception:
                        candidate = None
            else:
                candidate = font_cache.get_font(fb, weight=font_weight, style=font_style, stretch='normal', inkscape_spec=None, strict_family=False)

            if candidate:
                tt_test, blob_test, idx_test = candidate
                cmap_test = tt_test.getBestCmap() or {}
                cov = coverage(tt_test, cmap_test)
                if cov > best_cover:
                    best_cover = cov
                    fallback_font = candidate
                    fallback_cmap = cmap_test
                if cov == len(missing_set):
                    break

        if fallback_font:
            fallback_ttfont, fallback_blob, fallback_index = fallback_font
            fallback_units_per_em = fallback_ttfont['head'].unitsPerEm
            fallback_scale = font_size / fallback_units_per_em
            fallback_glyph_set = fallback_ttfont.getGlyphSet()
        if missing_chars and (not fallback_font or best_cover <= 0):
            uniq = ''.join(sorted(set(missing_chars)))
            raise MissingFontError(font_family, font_weight, font_style, font_stretch, f"Glyphs missing for chars '{uniq}' in font '{font_family}' and fallback")

    # 4. Get font metrics
    units_per_em = ttfont['head'].unitsPerEm
    scale = font_size / units_per_em
    # Note: transform_sx and transform_sy will be applied when generating path coordinates
    # but NOT to the font_size itself (transform is on the element, not the font)

    # Font coordinates have Y going up, SVG has Y going down
    # We need to flip Y, so we'll negate in the transform

    # 5. Unicode BiDi analysis and script detection
    # Split text into runs by BOTH direction (LTR/RTL) AND script (Latin/Arab/etc)
    
    # Get explicit direction from SVG attributes
    svg_direction = get_attr(text_elem, 'direction', 'ltr').lower()
    base_dir = 'RTL' if svg_direction == 'rtl' else 'LTR'

    try:
        import unicodedata

        runs = []
        if not text_content:
            runs = [(0, 0, base_dir, 'Latn')]
        else:
            # Get direction and script for each character
            char_props = []  # List of (direction, script)

            for char in text_content:
                # Determine direction
                bidi_class = unicodedata.bidirectional(char)
                if bidi_class in ('R', 'AL', 'RLE', 'RLO'):
                    direction = 'RTL'
                elif bidi_class in ('L', 'LRE', 'LRO'):
                    direction = 'LTR'
                else:
                    direction = None  # Neutral

                # Determine script (simplified - just Latin vs Arabic for now)
                if bidi_class in ('R', 'AL'):
                    script = 'Arab'
                elif '\u0600' <= char <= '\u06FF':  # Arabic Unicode range
                    script = 'Arab'
                elif char.isalpha():
                    script = 'Latn'
                else:
                    script = None  # Neutral (numbers, punctuation, spaces)

                char_props.append((direction, script))

            # Resolve neutrals - inherit from previous non-neutral or base direction
            current_dir = base_dir
            current_script = 'Latn'

            for i, (d, s) in enumerate(char_props):
                if d is not None:
                    current_dir = d
                if s is not None:
                    current_script = s

                # Fill in neutrals
                if char_props[i][0] is None:
                    char_props[i] = (current_dir, char_props[i][1])
                if char_props[i][1] is None:
                    char_props[i] = (char_props[i][0], current_script)

            # Extract runs - split when EITHER direction OR script changes
            run_start = 0
            current_dir, current_script = char_props[0]

            for i in range(1, len(char_props)):
                char_dir, char_script = char_props[i]
                if char_dir != current_dir or char_script != current_script:
                    # Direction or script changed, finish current run
                    runs.append((run_start, i, current_dir, current_script))
                    run_start = i
                    current_dir = char_dir
                    current_script = char_script

            # Add the final run
            runs.append((run_start, len(text_content), current_dir, current_script))

    except Exception as e:
        print(f"  ⚠️  BiDi/script analysis failed: {e}")
        runs = [(0, len(text_content), base_dir, 'Latn')]

    # 6. Create HarfBuzz font
    try:
        # Ensure fallback_font is defined for later HB setup
        fallback_font = None if 'fallback_font' not in locals() else fallback_font
        fallback_hb_font = None
        hb_blob = hb.Blob(font_blob)
        hb_face = hb.Face(hb_blob, font_index)  # CRITICAL: Must specify face index for TTC files
        hb_font = hb.Font(hb_face)
        hb_font.scale = (units_per_em, units_per_em)
        if variation_settings:
            # Clamp variations to axis ranges if available
            try:
                if 'fvar' in ttfont:
                    axes = {ax.axisTag: ax for ax in ttfont['fvar'].axes}
                    clamped = []
                    for tag, val in variation_settings:
                        if tag in axes:
                            ax = axes[tag]
                            v = min(max(val, ax.minValue), ax.maxValue)
                            clamped.append((tag, v))
                        else:
                            clamped.append((tag, val))
                    variation_settings = clamped
            except Exception:
                pass
            try:
                hb_font.set_variations(variation_settings)
            except Exception as e:
                print(f"  ⚠️  Failed to apply font variations {variation_settings}: {e}")

        # Fallback HB font (if needed later)
        if fallback_font:
            fb_tt, fb_blob, fb_idx = fallback_font
            try:
                fb_face = hb.Face(hb.Blob(fb_blob), fb_idx)
                fb_font = hb.Font(fb_face)
                fb_units = fb_tt['head'].unitsPerEm
                fb_font.scale = (fb_units, fb_units)
                fallback_hb_font = fb_font
            except Exception:
                fallback_hb_font = None

        # DEBUG: Verify face index
        if text_content and len(text_content) == 1 and text_content in '☰':
            print(f"    DEBUG icon '{text_content}': font_index={font_index}, ttfont_face={ttfont}, hb_face_index={hb_face.index}")
    except Exception as e:
        print(f"  ✗ Failed to create HarfBuzz font: {e}")
        return None

    def _hb_features(n_bytes: int):
        feats = {}
        for tag, val in feature_settings:
            try:
                feats[tag] = val
            except Exception:
                continue
        return feats

    # Collect font-feature-settings (before shaping)
    feature_settings: list[tuple[str, int]] = []
    feat_raw = get_attr(text_elem, 'font-feature-settings', None)
    if feat_raw:
        try:
            # format: 'kern' 0, "liga" 1, etc.
            for tag, val in re.findall(r"[\"']?([A-Za-z0-9]{4})[\"']?\\s+(-?\\d+)", feat_raw):
                feature_settings.append((tag, int(val)))
        except Exception:
            feature_settings = []

    # 7. Chunk layout and anchor computation (per Inkscape plain-SVG behavior)
    # Split runs into chunks by font coverage and accumulate widths before anchoring.
    # This also gives us per-chunk metrics for underline placement.
    chunk_list = []  # list of dicts: {start,end,font_key,width,positions,infos,ttfont,glyph_set,scale,cmap}

    import bisect

    # Precompute glyph set for primary
    glyph_set_primary = ttfont.getGlyphSet()
    # Build global byte offsets for dx/dy mapping
    byte_offsets_global = [0]
    acc_global = 0
    for ch in text_content:
        acc_global += len(ch.encode('utf-8'))
        byte_offsets_global.append(acc_global)

    for run_start, run_end, direction, script in runs:
        run_text = text_content[run_start:run_end]

        # Segment run by font coverage (primary vs fallback)
        segments = []
        current_font = None
        seg_start = 0
        for idx, ch in enumerate(run_text):
            cp = ord(ch)
            if cp in cmap and cmap.get(cp, 0) != 0:
                font_key = 'primary'
            elif fallback_cmap and cp in fallback_cmap and fallback_cmap.get(cp, 0) != 0:
                font_key = 'fallback'
            else:
                raise MissingFontError(font_family, font_weight, font_style, font_stretch, f"Glyph {repr(ch)} missing in primary and fallback fonts")
            if current_font is None:
                current_font = font_key
                seg_start = idx
            elif font_key != current_font:
                segments.append((current_font, seg_start, idx))
                current_font = font_key
                seg_start = idx
        if current_font is not None:
            segments.append((current_font, seg_start, len(run_text)))

        # Shape each segment and store
        for font_key, s, e in segments:
            seg_text = run_text[s:e]
            if font_key == 'primary':
                seg_ttfont = ttfont
                seg_scale = scale
                seg_hb_font = hb_font
                seg_glyph_set = glyph_set_primary
                seg_cmap = cmap
            else:
                seg_ttfont = fallback_ttfont
                seg_scale = fallback_scale
                seg_hb_font = fallback_hb_font
                seg_glyph_set = fallback_glyph_set
                seg_cmap = fallback_cmap

            buf = hb.Buffer()
            buf.add_str(seg_text)
            buf.direction = 'rtl' if direction == 'RTL' else 'ltr'
            buf.guess_segment_properties()
            hb.shape(seg_hb_font, buf, features=_hb_features(len(seg_text.encode('utf-8'))))
            seg_infos = buf.glyph_infos
            seg_positions = buf.glyph_positions
            width = sum(p.x_advance for p in seg_positions) * (seg_scale or 1.0)

            chunk_list.append({
                'run_start': run_start,
                'start': run_start + s,
                'end': run_start + e,
                'font_key': font_key,
                'width': width,
                'infos': seg_infos,
                'positions': seg_positions,
                'ttfont': seg_ttfont,
                'glyph_set': seg_glyph_set,
                'scale': seg_scale,
                'cmap': seg_cmap,
                'direction': direction,
                'buf': buf,
                'local_offset': s,
                'run_text': run_text,
                'local_byte_offsets': None,
            })

    # 8. Shape text with HarfBuzz and render glyphs (chunk-based, anchor once)
    import bisect
    all_paths = []
    advance_x = 0.0  # legacy total advance across lines
    line_decors: list[tuple[float, float, float]] = []  # (start_x, end_x, baseline_y)

    path_len = path_obj.length() if path_obj is not None else None

    # Group chunks by baseline (y) to anchor per line (handles multiple tspans sharing a line)
    lines: list[list[dict]] = []
    current_line = []
    last_y = y
    for chunk in chunk_list:
        # Assume same y for now; text in this converter uses explicit y per text/tspan
        # If y changes (different tspans), start new line
        if current_line and chunk.get('line_y') is not None and chunk['line_y'] != last_y:
            lines.append(current_line)
            current_line = []
        current_line.append(chunk)
        chunk['line_y'] = y  # preserve baseline
        last_y = y
    if current_line:
        lines.append(current_line)

    def _measure_line_width(line_chunks: list[dict]) -> float:
        """Compute visual line width like Inkscape: sum advances & dx/spacing; trim trailing spacing."""
        width = 0.0
        last_letter = 0.0
        last_word = 0.0
        for chunk in line_chunks:
            seg_scale = chunk['scale'] or 1.0
            seg_infos = chunk['infos']
            seg_positions = chunk['positions']
            run_text = chunk['run_text']
            local_offset = chunk['local_offset']
            seg_len = chunk['end'] - chunk['start']
            seg_text = run_text[local_offset:local_offset + seg_len]

            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode('utf-8'))
                local_byte_offsets.append(acc_local)

            cursor = 0.0
            for info, pos in zip(seg_infos, seg_positions):
                cluster = info.cluster
                char_idx_local = max(0, bisect.bisect_right(local_byte_offsets, cluster) - 1)
                char_idx = chunk['start'] + char_idx_local
                current_dx = dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                add_spacing = letter_spacing
                is_space = text_content[char_idx:char_idx + 1] == ' '
                if is_space:
                    add_spacing += word_spacing
                    last_word = word_spacing
                else:
                    last_word = 0.0
                adv = (pos.x_advance * seg_scale) + current_dx + add_spacing
                if chunk.get('direction', 'LTR') == 'RTL':
                    cursor -= adv
                else:
                    cursor += adv
                last_letter = letter_spacing
            width += abs(cursor)

        width -= last_letter
        width -= last_word
        return width

    for line_chunks in lines:
        line_dir = line_chunks[0].get('direction', 'LTR') if line_chunks else 'LTR'
        line_width = _measure_line_width(line_chunks)
        if text_anchor == 'middle':
            line_anchor_offset = -line_width / 2.0
        elif text_anchor == 'end':
            line_anchor_offset = 0.0 if line_dir == 'RTL' else -line_width
        else:
            line_anchor_offset = -line_width if line_dir == 'RTL' else 0.0

        advance_x_line_ltr = 0.0
        advance_x_line_rtl = 0.0
        advance_x_line = 0.0  # legacy cursor (kept to avoid breakage; replace in RTL refactor)
        line_baseline = line_chunks[0].get('line_y', y) if line_chunks else y

        def _chunk_width(chunk: dict) -> float:
            seg_scale = chunk['scale'] or 1.0
            seg_infos = chunk['infos']
            seg_positions = chunk['positions']
            run_text = chunk['run_text']
            local_offset = chunk['local_offset']
            seg_len = chunk['end'] - chunk['start']
            seg_text = run_text[local_offset:local_offset + seg_len]
            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode('utf-8'))
                local_byte_offsets.append(acc_local)
            cursor = 0.0
            for info, pos in zip(seg_infos, seg_positions):
                cluster = info.cluster
                char_idx_local = max(0, bisect.bisect_right(local_byte_offsets, cluster) - 1)
                char_idx = chunk['start'] + char_idx_local
                current_dx = dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                add_spacing = letter_spacing
                if text_content[char_idx:char_idx + 1] == ' ':
                    add_spacing += word_spacing
                cursor += (pos.x_advance * seg_scale) + current_dx + add_spacing
            return abs(cursor - letter_spacing)

        for chunk in line_chunks:
            seg_ttfont = chunk['ttfont']
            seg_scale = chunk['scale'] or 1.0
            seg_infos = chunk['infos']
            seg_positions = chunk['positions']
            seg_glyph_set = chunk['glyph_set']
            run_text = chunk['run_text']
            local_offset = chunk['local_offset']
            seg_len = chunk['end'] - chunk['start']
            seg_text = run_text[local_offset:local_offset + seg_len]

            # Byte offsets local to this segment
            local_byte_offsets = [0]
            acc_local = 0
            for ch in seg_text:
                acc_local += len(ch.encode('utf-8'))
                local_byte_offsets.append(acc_local)

            chunk_width = _chunk_width(chunk)
            chunk_dir = chunk.get('direction', 'LTR')
            if chunk_dir == 'RTL':
                chunk_start = line_width - advance_x_line_rtl - chunk_width
                cursor_chunk = chunk_width
            else:
                chunk_start = advance_x_line_ltr
                cursor_chunk = 0.0

            for info, pos in zip(seg_infos, seg_positions):
                cluster = info.cluster
                char_idx_local = max(0, bisect.bisect_right(local_byte_offsets, cluster) - 1)
                char_idx = chunk['start'] + char_idx_local
                current_dx = dx_list[char_idx] if dx_list and char_idx < len(dx_list) else 0.0
                current_dy = dy_list[char_idx] if dy_list and char_idx < len(dy_list) else 0.0

                glyph_id = info.codepoint
                try:
                    glyph_name = seg_ttfont.getGlyphName(glyph_id)
                except Exception:
                    glyph_name = None
                glyph_missing = glyph_name in ('.notdef', 'missing', 'null') or glyph_id == 0
                glyph = seg_glyph_set.get(glyph_name) if (glyph_name and not glyph_missing) else None
                if glyph is None:
                    adv_na = (pos.x_advance * seg_scale) + current_dx + letter_spacing
                    if text_content[char_idx:char_idx + 1] == ' ':
                        adv_na += word_spacing
                    if chunk_dir == 'RTL':
                        cursor_chunk -= adv_na
                    else:
                        cursor_chunk += adv_na
                    continue

                pen = RecordingPen()
                try:
                    glyph.draw(pen)
                except Exception:
                    adv_na = (pos.x_advance * seg_scale) + current_dx + letter_spacing
                    if text_content[char_idx:char_idx + 1] == ' ':
                        adv_na += word_spacing
                    if chunk_dir == 'RTL':
                        cursor_chunk -= adv_na
                    else:
                        cursor_chunk += adv_na
                    continue
                recording = pen.value

                glyph_offset = 0.0

                if path_obj is not None and path_len and path_len > 0:
                    arc_pos = path_offset + line_anchor_offset + advance_x_line + current_dx + (pos.x_offset * seg_scale) - glyph_offset
                    if arc_pos < 0:
                        arc_pos = 0.0
                    if arc_pos > path_len:
                        arc_pos = path_len
                    frac = arc_pos / path_len
                    try:
                        base_point = path_obj.point(frac)
                        tangent = path_obj.tangent(frac)
                    except Exception:
                        base_point = complex(0, 0)
                        tangent = complex(1, 0)
                    if tangent == 0:
                        tangent = complex(1, 0)
                    # Normalized vectors
                    t_len = abs(tangent)
                    tangent_unit = tangent / t_len
                    normal_unit = complex(-tangent_unit.imag, tangent_unit.real)
                    offset_normal = (pos.y_offset * seg_scale) + current_dy
                    base_x = base_point.real + normal_unit.real * offset_normal
                    base_y = base_point.imag + normal_unit.imag * offset_normal

                    cos_t = tangent_unit.real
                    sin_t = tangent_unit.imag

                    transformed_recording = []
                    for op, args in recording:
                        if op in ['moveTo', 'lineTo']:
                            px, py = args[0]
                            lx = px * seg_scale
                            ly = -py * seg_scale
                            rx = lx * cos_t - ly * sin_t
                            ry = lx * sin_t + ly * cos_t
                            new_x = base_x + rx
                            new_y = base_y + ry
                            if baked_matrix:
                                a,b,c,d,e,f = baked_matrix
                                new_x, new_y = (a*new_x + c*new_y + e, b*new_x + d*new_y + f)
                            transformed_recording.append((op, [(new_x, new_y)]))
                        elif op == 'qCurveTo':
                            new_args = []
                            for px, py in args:
                                lx = px * seg_scale
                                ly = -py * seg_scale
                                rx = lx * cos_t - ly * sin_t
                                ry = lx * sin_t + ly * cos_t
                                nx = base_x + rx
                                ny = base_y + ry
                                if baked_matrix:
                                    a,b,c,d,e,f = baked_matrix
                                    nx, ny = (a*nx + c*ny + e, b*nx + d*ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == 'curveTo':
                            new_args = []
                            for px, py in args:
                                lx = px * seg_scale
                                ly = -py * seg_scale
                                rx = lx * cos_t - ly * sin_t
                                ry = lx * sin_t + ly * cos_t
                                nx = base_x + rx
                                ny = base_y + ry
                                if baked_matrix:
                                    a,b,c,d,e,f = baked_matrix
                                    nx, ny = (a*nx + c*ny + e, b*nx + d*ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == 'closePath':
                            transformed_recording.append((op, args))
                else:
                    glyph_x = x + line_anchor_offset + advance_x_line + current_dx + (pos.x_offset * seg_scale) - glyph_offset
                    glyph_y = line_baseline + (pos.y_offset * seg_scale) + current_dy

                    transformed_recording = []
                    for op, args in recording:
                        if op in ['moveTo', 'lineTo']:
                            px, py = args[0]
                            new_x = px * seg_scale + glyph_x
                            new_y = -py * seg_scale + glyph_y
                            if baked_matrix:
                                a,b,c,d,e,f = baked_matrix
                                new_x, new_y = (a*new_x + c*new_y + e, b*new_x + d*new_y + f)
                            transformed_recording.append((op, [(new_x, new_y)]))
                        elif op == 'qCurveTo':
                            new_args = []
                            for px, py in args:
                                nx = px * seg_scale + glyph_x
                                ny = -py * seg_scale + glyph_y
                                if baked_matrix:
                                    a,b,c,d,e,f = baked_matrix
                                    nx, ny = (a*nx + c*ny + e, b*nx + d*ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == 'curveTo':
                            new_args = []
                            for px, py in args:
                                nx = px * seg_scale + glyph_x
                                ny = -py * seg_scale + glyph_y
                                if baked_matrix:
                                    a,b,c,d,e,f = baked_matrix
                                    nx, ny = (a*nx + c*ny + e, b*nx + d*ny + f)
                                new_args.append((nx, ny))
                            transformed_recording.append((op, new_args))
                        elif op == 'closePath':
                            transformed_recording.append((op, args))

                path_data = recording_pen_to_svg_path(transformed_recording, precision)
                if path_data:
                    all_paths.append(path_data)

                add_spacing = letter_spacing
                if text_content[char_idx:char_idx+1] == ' ':
                    add_spacing += word_spacing
                advance_x_line += pos.x_advance * seg_scale + current_dx + add_spacing

        # Track per-line geometry for decorations
        if path_obj is None:
            start_x_line = x + line_anchor_offset
            end_x_line = start_x_line + advance_x_line
            line_decors.append((start_x_line, end_x_line, line_baseline))
        advance_x = max(advance_x, advance_x_line)

    # Generate text decorations (underline, line-through)
    decoration = get_attr(text_elem, 'text-decoration', 'none')
    # Also check style for text-decoration
    style_decoration = re.search(r'text-decoration:\s*([^;]+)', text_elem.get('style', ''))
    if style_decoration:
        decoration = style_decoration.group(1)

    if decoration and decoration != 'none' and line_decors:
        # Get font metrics for decoration
        # Default values if metrics are missing
        underline_position = -0.1 * units_per_em
        underline_thickness = 0.05 * units_per_em
        strikeout_position = 0.3 * units_per_em
        strikeout_thickness = 0.05 * units_per_em

        # Use metrics from the dominant chunk font (first chunk) for decoration
        dom_tt = chunk_list[0]['ttfont'] if chunk_list else ttfont
        try:
            post = dom_tt['post']
            if hasattr(post, 'underlinePosition'):
                underline_position = post.underlinePosition
            if hasattr(post, 'underlineThickness'):
                underline_thickness = post.underlineThickness
            if 'OS/2' in dom_tt:
                os2 = dom_tt['OS/2']
                if hasattr(os2, 'yStrikeoutPosition'):
                    strikeout_position = os2.yStrikeoutPosition
                if hasattr(os2, 'yStrikeoutSize'):
                    strikeout_thickness = os2.yStrikeoutSize
        except Exception:
            pass

        fmt = f"{{:.{precision}f}}"

        for start_x, end_x, baseline_y in line_decors:
            deco_paths = []
            if 'underline' in decoration:
                y_pos = baseline_y - (underline_position * scale)
                thickness = underline_thickness * scale
                deco_paths.append([(start_x, y_pos), (end_x, y_pos), (end_x, y_pos+thickness), (start_x, y_pos+thickness)])

            if 'line-through' in decoration:
                y_pos = baseline_y - (strikeout_position * scale)
                thickness = strikeout_thickness * scale
                deco_paths.append([(start_x, y_pos), (end_x, y_pos), (end_x, y_pos+thickness), (start_x, y_pos+thickness)])

            for rect in deco_paths:
                pts = []
                for (px, py) in rect:
                    if baked_matrix:
                        a,b,c,d,e,f = baked_matrix
                        px, py = (a*px + c*py + e, b*px + d*py + f)
                    pts.append((px, py))
                deco_path = f"M {fmt.format(pts[0][0])} {fmt.format(pts[0][1])} L {fmt.format(pts[1][0])} {fmt.format(pts[1][1])} L {fmt.format(pts[2][0])} {fmt.format(pts[2][1])} L {fmt.format(pts[3][0])} {fmt.format(pts[3][1])} Z"
                all_paths.append(deco_path)

    if not all_paths:
        print(f"  ✗ No path data generated for text '{text_content}'")
        return None

    # 8. Create path element with SVG namespace
    path_elem = ET.Element('{http://www.w3.org/2000/svg}path')
    path_elem.set('d', ' '.join(all_paths))

    # 9. Copy ID
    if 'id' in text_elem.attrib:
        path_elem.set('id', text_elem.get('id'))

    # 10. Bake transform when possible; otherwise preserve
    transform_attr = text_elem.get('transform')
    baked_matrix = parse_transform_matrix(transform_attr) if transform_attr else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    preserve_transform = transform_attr is not None and baked_matrix is None
    if preserve_transform:
        path_elem.set('transform', transform_attr)

    # Compute stroke scale for baked transforms (affects stroke-width)
    stroke_scale = 1.0
    if transform_attr and baked_matrix:
        a, b, c, d, e, f = baked_matrix
        scale_x = math.hypot(a, b)
        scale_y = math.hypot(c, d)
        if scale_x > 0 and scale_y > 0:
            stroke_scale = (scale_x + scale_y) / 2.0
        else:
            stroke_scale = max(scale_x, scale_y, 1.0)

    # 11. Preserve styling (full style plus common stroke/fill attributes)
    if 'style' in text_elem.attrib:
        style_val = text_elem.get('style')
        # If stroke-width present in style and we baked transform, scale it
        if stroke_scale != 1.0 and style_val and 'stroke-width' in style_val:
            def _scale_sw(match):
                try:
                    num = float(match.group(1))
                    return f"stroke-width:{num * stroke_scale}"
                except Exception:
                    return match.group(0)
            style_val = re.sub(r'stroke-width:([\\d\\.]+)', _scale_sw, style_val)
        path_elem.set('style', style_val)
    for attr_name in (
        'fill', 'stroke', 'stroke-width', 'stroke-linejoin', 'stroke-linecap',
        'stroke-miterlimit', 'fill-opacity', 'stroke-opacity', 'opacity',
        'stroke-dasharray', 'stroke-dashoffset'
    ):
        if attr_name in text_elem.attrib:
            val = text_elem.get(attr_name)
            if attr_name == 'stroke-width' and stroke_scale != 1.0:
                try:
                    val = str(float(val) * stroke_scale)
                except Exception:
                    pass
            path_elem.set(attr_name, val)

    # 12. Preserve animations
    # Copy animate, animateTransform, set, animateMotion children
    for child in text_elem:
        tag = child.tag
        if '}' in tag:
            tag = tag.split('}')[1]
        
        if tag in ('animate', 'animateTransform', 'set', 'animateMotion'):
            # Clone the animation element
            import copy
            anim_clone = copy.deepcopy(child)
            path_elem.append(anim_clone)

    # Return both the path element and the total advance width
    return path_elem, advance_x


def convert_svg_text_to_paths(svg_path: Path, output_path: Path, precision: int = 28) -> None:
    """Convert all text elements in SVG to paths."""
    print(f"Converting text to paths (Rust-style) in: {svg_path}")

    # 1. Parse SVG
    ET.register_namespace('', 'http://www.w3.org/2000/svg')  # Default namespace, no prefix

    tree = ET.parse(svg_path)
    root = tree.getroot()

    # Bake transforms up front to eliminate inherited transform-induced shifts.
    # This was critical to reduce anchor drift across the document.
    flatten_transforms(root)

    # Reject Inkscape SVG (sodipodi namespace)
    if any('sodipodi' in (elem.tag or '') for elem in root.iter()):
        raise RuntimeError("please export the file from inkscape using the plain svg option!")

    # 2. Create font cache
    font_cache = FontCache()
    
    # 2b. Collect path definitions for textPath
    path_map = {} # id -> svg.path.Path
    
    def find_paths_recursive(element):
        for child in element:
            tag = child.tag
            if '}' in tag:
                tag = tag.split('}')[1]
            
            if tag == 'path':
                path_id = child.get('id')
                d = child.get('d')
                if path_id and d:
                    try:
                        path_map[path_id] = parse_path(d)
                    except Exception as e:
                        print(f"Warning: Failed to parse path {path_id}: {e}")
            
            find_paths_recursive(child)
            
    find_paths_recursive(root)
    print(f"Found {len(path_map)} path definitions")

    # 3. Find all text elements
    text_elements = []

    def find_text_recursive(element):
        """Recursively find text elements."""
        for child in element:
            tag = child.tag
            if '}' in tag:
                tag = tag.split('}')[1]

            if tag == 'text':
                text_elements.append((element, child))
            else:
                find_text_recursive(child)

    find_text_recursive(root)

    print(f"Found {len(text_elements)} text elements")

    # 4. Convert each text element to path
    converted = 0
    failed = 0
    missing_fonts: list[MissingFontError] = []

    for parent, text_elem in text_elements:
        elem_id = text_elem.get('id', '?')

        try:
            # Check for textPath
            text_path_elem = None
            for child in text_elem:
                tag = child.tag
                if '}' in tag:
                    tag = tag.split('}')[1]
                if tag == 'textPath':
                    text_path_elem = child
                    break
            
            # Determine content source (textPath or direct/tspans)
            content_elem = text_path_elem if text_path_elem is not None else text_elem
            
            # Check if text has tspan children
            tspans = []
            for child in content_elem:
                tag = child.tag
                if '}' in tag:
                    tag = tag.split('}')[1]
                if tag == 'tspan':
                    tspans.append(child)

            # Get preview text for logging
            if tspans:
                preview_text = (tspans[0].text or "")[:50]
            else:
                preview_text = (content_elem.text or "")[:50]

            print(f"  Converting text '{preview_text}' (id={elem_id}, {len(tspans)} tspan(s))...")
            
            # Setup textPath info if present
            path_obj = None
            path_start_offset = 0.0
            
            if text_path_elem is not None:
                # Get href
                href = text_path_elem.get('{http://www.w3.org/1999/xlink}href')
                if not href:
                    href = text_path_elem.get('href')
                
                if href and href.startswith('#'):
                    path_id = href[1:]
                    path_obj = path_map.get(path_id)
                    
                    if path_obj:
                        # Calculate startOffset
                        start_offset_attr = text_path_elem.get('startOffset', '0')
                        path_len = path_obj.length()
                        
                        if '%' in start_offset_attr:
                            pct = float(start_offset_attr.strip('%')) / 100.0
                            path_start_offset = path_len * pct
                        else:
                            path_start_offset = float(start_offset_attr)
                    else:
                        print(f"    ⚠️  Referenced path '{path_id}' not found")

            # Handle multi-tspan text elements (or single textPath with tspans)
            if tspans:
                # Create a group to hold multiple paths
                group_elem = ET.Element('{http://www.w3.org/2000/svg}g')
                group_elem.set('id', elem_id + '_group')

                # Copy transform from text to group if it exists
                if 'transform' in text_elem.attrib:
                    group_elem.set('transform', text_elem.get('transform'))

                # Track cursor position for flow
                base_x = float(text_elem.get('x', '0'))
                base_y = float(text_elem.get('y', '0'))
                cursor_x = 0.0 if path_obj else base_x
                cursor_y = base_y
                current_path_offset = path_start_offset if path_obj else 0.0

                parent_style = text_elem.get('style', '')
                inline_size = None  # plain SVG: do not auto-wrap; rely on explicit x/y or tspans

                def merge_style(p_style: str, c_style: str) -> str:
                    if p_style and c_style:
                        p_props = dict(prop.split(':', 1) for prop in p_style.split(';') if ':' in prop)
                        c_props = dict(prop.split(':', 1) for prop in c_style.split(';') if ':' in prop)
                        merged = {**p_props, **c_props}
                        return ';'.join(f"{k}:{v}" for k, v in merged.items())
                    return c_style or p_style

                def strip_anchor(style_str: str) -> str:
                    if not style_str:
                        return style_str
                    props = []
                    for prop in style_str.split(';'):
                        if ':' not in prop:
                            continue
                        k, v = prop.split(':', 1)
                        k = k.strip()
                        if k in ('text-anchor', 'text-align'):
                            continue
                        props.append(f"{k}:{v.strip()}")
                    return ';'.join(props)

                tspan_converted = 0
                temp_id_counter = 0

                leaf_items = []

                # Resolve parent anchor once
                parent_anchor = text_elem.get('text-anchor', None)
                if not parent_anchor:
                    # check style on text_elem
                    style_anchor_match = re.search(r'text-anchor:\s*(start|middle|end)', text_elem.get('style', ''))
                    if style_anchor_match:
                        parent_anchor = style_anchor_match.group(1)
                text_align_match_parent = re.search(r'text-align:\s*(center|left|right)', text_elem.get('style', ''))
                if text_align_match_parent and not parent_anchor:
                    text_align_map = {'center': 'middle', 'left': 'start', 'right': 'end'}
                    parent_anchor = text_align_map.get(text_align_match_parent.group(1))
                if not parent_anchor:
                    parent_anchor = 'start'

                def span_anchor(span: ET.Element, fallback: str) -> str:
                    anchor = span.get('text-anchor', None)
                    if not anchor:
                        style_anchor_match = re.search(r'text-anchor:\s*(start|middle|end)', span.get('style', ''))
                        if style_anchor_match:
                            anchor = style_anchor_match.group(1)
                    text_align_match = re.search(r'text-align:\s*(center|left|right)', span.get('style', ''))
                    if text_align_match and not anchor:
                        text_align_map = {'center': 'middle', 'left': 'start', 'right': 'end'}
                        anchor = text_align_map.get(text_align_match.group(1))
                    return anchor or fallback

                def process_span(span: ET.Element, cx: float, cy: float, p_offset: float, inherited_style: str) -> tuple[float, float, float, int]:
                    nonlocal temp_id_counter, tspan_converted

                    # Resolve x/y
                    if 'x' in span.attrib:
                        cx = float(span.get('x'))
                    if 'y' in span.attrib:
                        cy = float(span.get('y'))

                    # Collect per-glyph shifts (do not pre-apply; text_to_path_rust_style handles them)
                    dx_list_span = _parse_num_list(span.get('dx', '')) if 'dx' in span.attrib else None
                    dy_list_span = _parse_num_list(span.get('dy', '')) if 'dy' in span.attrib else None

                    # Effective style
                    span_style = merge_style(inherited_style, span.get('style', ''))

                    # If this span has direct text, convert it
                    text_content = span.text or ""
                    has_child_tspan = any((c.tag.split('}',1)[-1] == 'tspan') for c in list(span))
                    if text_content.strip() and not has_child_tspan:
                        leaf_items.append({
                            "text": text_content,
                            "x": cx,
                            "y": cy,
                            "explicit_xy": ('x' in span.attrib) or ('y' in span.attrib),
                            "anchor": span_anchor(span, parent_anchor),
                            "style": span_style,
                            "dx_list": dx_list_span,
                            "dy_list": dy_list_span,
                            "p_offset": p_offset,
                        })

                    # Recurse into children
                    for child in list(span):
                        cx, cy, p_offset, _ = process_span(child, cx, cy, p_offset, span_style)
                        # Handle tail text after child
                        if child.tail and child.tail.strip():
                            tail_text = child.tail
                            temp_text = ET.Element('{http://www.w3.org/2000/svg}text')
                            temp_text.set('x', str(cx))
                            temp_text.set('y', str(cy))
                            if span_style:
                                temp_text.set('style', span_style)
                            temp_text.text = tail_text
                            result_tail = text_to_path_rust_style(temp_text, font_cache, path_obj, p_offset, precision)
                            if result_tail is not None:
                                path_elem, width = result_tail
                                if 'transform' in path_elem.attrib:
                                    del path_elem.attrib['transform']
                                path_elem.set('id', f"{elem_id}_tspan{temp_id_counter}")
                                temp_id_counter += 1
                                group_elem.append(path_elem)
                                tspan_converted += 1
                                cx += width
                                if path_obj:
                                    p_offset += width

                    return cx, cy, p_offset, tspan_converted

                # Walk each top-level tspan
                for i, tspan in enumerate(tspans):
                    t_preview = (tspan.text or "").strip().replace("\n", " ") or "(nested)"
                    print(f"      tspan {i}: '{t_preview[:40]}'")
                    cursor_x, cursor_y, current_path_offset, _ = process_span(tspan, cursor_x, cursor_y, current_path_offset, parent_style)

                has_explicit_xy = any('x' in t.attrib or 'y' in t.attrib for t in tspans)

                # If inline-size specified, no textPath, and no explicit x/y on tspans, perform wrapping
                if inline_size and not path_obj and leaf_items and not has_explicit_xy:
                    line_height = float(re.search(r'([\\d\\.]+)', text_elem.get('font-size','16')).group(1)) * 1.2 if re.search(r'([\\d\\.]+)', text_elem.get('font-size','16')) else 16*1.2

                    lines = []
                    current_line = []
                    current_width = 0.0

                    def measure_leaf(li):
                        temp_text = ET.Element('{http://www.w3.org/2000/svg}text')
                        temp_text.set('x', str(0))
                        temp_text.set('y', str(0))
                        if li["style"]:
                            temp_text.set('style', strip_anchor(li["style"]))
                        temp_text.text = li["text"]
                        res = text_to_path_rust_style(temp_text, font_cache, None, 0.0, precision, dx_list=li["dx_list"], dy_list=li["dy_list"])
                        if res is None:
                            return 0.0, None
                        path_elem, width = res
                        return width, path_elem

                    measured_paths = []
                    for li in leaf_items:
                        w, p_elem = measure_leaf(li)
                        measured_paths.append((li, w, p_elem))
                        if current_width + w > inline_size and current_width > 0:
                            lines.append((current_line, current_width))
                            current_line = []
                            current_width = 0.0
                        current_line.append((li, w, p_elem))
                        current_width += w
                    if current_line:
                        lines.append((current_line, current_width))

                    # Place lines honoring text-anchor
                    anchor = text_elem.get('text-anchor', 'start')
                    base_x = float(text_elem.get('x','0'))
                    base_y = float(text_elem.get('y','0'))

                    line_index = 0
                    for line_items, lw in lines:
                        if anchor == 'middle':
                            line_x = base_x - lw/2
                        elif anchor == 'end':
                            line_x = base_x - lw
                        else:
                            line_x = base_x
                        line_y = base_y + line_index * line_height
                        cursor = 0.0
                        for li, w, p_elem in line_items:
                            if p_elem is None:
                                continue
                            # translate path by line_x + cursor, line_y
                            # wrap p_elem in group with translate
                            g = ET.Element('{http://www.w3.org/2000/svg}g')
                            g.set('transform', f"translate({line_x + cursor},{line_y})")
                            g.append(p_elem)
                            g.set('id', f"{elem_id}_tspan{temp_id_counter}")
                            temp_id_counter += 1
                            group_elem.append(g)
                            cursor += w
                            tspan_converted += 1
                        line_index += 1
                else:
                    # No wrapping; convert collected leafs. If not a textPath, apply anchor once per line.
                    if path_obj:
                        cursor = 0.0
                        for li in leaf_items:
                            li_x = li["x"]
                            li_y = li["y"]
                            li_anchor = li.get("anchor") or parent_anchor
                            temp_text = ET.Element('{http://www.w3.org/2000/svg}text')
                            temp_text.set('x', str(li_x))
                            temp_text.set('y', str(li_y))
                            if 'transform' in text_elem.attrib:
                                temp_text.set('transform', text_elem.get('transform'))
                            if li["style"]:
                                temp_text.set('style', strip_anchor(li["style"]))
                            if li_anchor:
                                temp_text.set('text-anchor', li_anchor)
                            if 'direction' in text_elem.attrib:
                                temp_text.set('direction', text_elem.get('direction'))
                            temp_text.text = li["text"]
                            result_inner = text_to_path_rust_style(
                                temp_text,
                                font_cache,
                                path_obj,
                                li["p_offset"],
                                precision,
                                dx_list=li["dx_list"],
                                dy_list=li["dy_list"],
                            )
                            if result_inner is not None:
                                path_elem, width = result_inner
                                if 'transform' in path_elem.attrib:
                                    del path_elem.attrib['transform']
                                path_elem.set('id', f"{elem_id}_tspan{temp_id_counter}")
                                temp_id_counter += 1
                                group_elem.append(path_elem)
                                tspan_converted += 1
                                cursor += width
                            else:
                                raise RuntimeError(f"Failed to convert span in element {elem_id}")
                    else:
                        # Group spans by their y coordinate (lines)
                        lines: list[list[dict]] = []
                        for li in leaf_items:
                            if not lines or abs(li["y"] - lines[-1][0]["y"]) > 1e-6:
                                lines.append([])
                            lines[-1].append(li)

                        for line_items in lines:
                            # Base x for the line comes from the first explicit x if present, else parent x
                            explicit_starts = [li for li in line_items if li["explicit_xy"]]
                            line_base_x = explicit_starts[0]["x"] if explicit_starts else base_x
                            line_anchor = parent_anchor

                            # Measure widths with anchor=start to avoid double shifting
                            measured: list[tuple[dict, float]] = []  # (leaf, width)
                            for li in line_items:
                                temp_measure = ET.Element('{http://www.w3.org/2000/svg}text')
                                temp_measure.set('x', '0')
                                temp_measure.set('y', '0')
                                if 'transform' in text_elem.attrib:
                                    temp_measure.set('transform', text_elem.get('transform'))
                                if li["style"]:
                                    temp_measure.set('style', li["style"])
                                temp_measure.set('text-anchor', 'start')
                                if 'direction' in text_elem.attrib:
                                    temp_measure.set('direction', text_elem.get('direction'))
                                temp_measure.text = li["text"]
                                res = text_to_path_rust_style(
                                    temp_measure,
                                    font_cache,
                                    None,
                                    0.0,
                                    precision,
                                    dx_list=li["dx_list"],
                                    dy_list=li["dy_list"],
                                )
                                width = res[1] if res is not None else 0.0
                                measured.append((li, width))

                            # Widths already include dx/spacing from text_to_path_rust_style.
                            total_width = sum(w for _, w in measured)
                            # Keep parent anchor but avoid double shifts on children.
                            # This change removed a major left drift on some lines (~14%→7% diff overall).
                            parent_shift = 0.0
                            if line_anchor == 'middle':
                                parent_shift = -total_width / 2.0
                            elif line_anchor == 'end':
                                parent_shift = -total_width

                            cursor = 0.0
                            for li, width in measured:
                                temp_text = ET.Element('{http://www.w3.org/2000/svg}text')
                                anchor_shift = 0.0
                                leaf_anchor = li.get("anchor") or line_anchor
                                if leaf_anchor != line_anchor:
                                    if leaf_anchor == 'middle':
                                        anchor_shift = -width / 2.0
                                    elif leaf_anchor == 'end':
                                        anchor_shift = -width

                                # If leaf anchor overrides parent, do not reapply parent_shift to avoid double anchoring.
                                effective_parent_shift = 0.0 if leaf_anchor != line_anchor else parent_shift

                                temp_text.set('x', str(line_base_x + effective_parent_shift + cursor + anchor_shift))
                                temp_text.set('y', str(li["y"]))
                                if 'transform' in text_elem.attrib:
                                    temp_text.set('transform', text_elem.get('transform'))
                                if li["style"]:
                                    temp_text.set('style', strip_anchor(li["style"]))
                                temp_text.set('text-anchor', 'start')
                                if 'direction' in text_elem.attrib:
                                    temp_text.set('direction', text_elem.get('direction'))
                                temp_text.text = li["text"]
                                result_inner = text_to_path_rust_style(
                                    temp_text,
                                    font_cache,
                                    None,
                                    li["p_offset"],
                                    precision,
                                    dx_list=li["dx_list"],
                                    dy_list=li["dy_list"],
                                )
                                if result_inner is not None:
                                    path_elem, _ = result_inner
                                    if 'transform' in path_elem.attrib:
                                        del path_elem.attrib['transform']
                                    path_elem.set('id', f"{elem_id}_tspan{temp_id_counter}")
                                    temp_id_counter += 1
                                    group_elem.append(path_elem)
                                    tspan_converted += 1
                                else:
                                    raise RuntimeError(f"Failed to convert span in element {elem_id}")
                                cursor += width

                if tspan_converted > 0:
                    if 'transform' in group_elem.attrib:
                        del group_elem.attrib['transform']
                    idx = list(parent).index(text_elem)
                    parent.remove(text_elem)
                    parent.insert(idx, group_elem)
                    converted += 1
                    print(f"    ✓ Converted successfully ({tspan_converted} leaf span(s))")
                else:
                    failed += 1
                    raise RuntimeError(f"Failed to convert tspans for element id={elem_id}")
            else:
                # Single text element (or textPath without tspans)
                
                # If textPath, we need to create a temp text element with the content from textPath
                if text_path_elem is not None:
                    temp_text = ET.Element('{http://www.w3.org/2000/svg}text')
                    # Copy attributes from text_elem
                    for k, v in text_elem.attrib.items():
                        temp_text.set(k, v)
                    # Set text content from textPath
                    temp_text.text = text_path_elem.text or ""
                    
                    # Use temp_text for conversion
                    target_elem = temp_text
                else:
                    target_elem = text_elem

                result = text_to_path_rust_style(target_elem, font_cache, path_obj, path_start_offset, precision)

                if result is not None:
                    path_elem, _ = result
                    # Replace text element with path
                    idx = list(parent).index(text_elem)
                    parent.remove(text_elem)
                    parent.insert(idx, path_elem)
                    converted += 1
                    print(f"    ✓ Converted successfully")
                else:
                    failed += 1
                    raise RuntimeError(f"Conversion failed for text id={elem_id}")

        except Exception as e:
            if isinstance(e, MissingFontError):
                missing_fonts.append(e)
                print(f"✗ Missing font for element {elem_id}: {e.message}")
                continue
            import traceback
            print(f"\n✗ FATAL ERROR converting text element '{elem_id}':")
            print(f"   Preview: '{preview_text}'")
            print(f"   Error: {e}")
            print(f"\nTraceback:")
            traceback.print_exc()
            sys.exit(1)

    if missing_fonts:
        print("\n✗ Missing fonts detected (conversion aborted):")
        print(" family | weight | style | stretch ")
        print("------------------------------------")
        seen = set()
        for mf in missing_fonts:
            key = (mf.family, mf.weight, mf.style, mf.stretch)
            if key in seen:
                continue
            seen.add(key)
            print(f" {mf.family} | {mf.weight} | {mf.style} | {mf.stretch}")
        sys.exit(1)

    # 5. Sanity check: ensure no <text> elements remain
    leftover = []
    def find_texts(el):
        for ch in el:
            tag = ch.tag.split('}')[-1] if '}' in ch.tag else ch.tag
            if tag == 'text':
                leftover.append(ch.get('id', ''))
            find_texts(ch)
    find_texts(root)
    if leftover:
        raise RuntimeError(f"Unconverted text elements remain: {leftover}")

    # 6. Write output SVG
    tree.write(output_path, encoding='utf-8', xml_declaration=True)

    print(f"\n✓ Conversion complete (Rust-style):")
    print(f"  Converted: {converted} text elements")
    print(f"  Failed: {failed} text elements")
    print(f"  Output: {output_path}")

    # 6. Convert to JPEG for visual comparison
    print(f"\nConverting SVGs to JPEG for visual comparison...")
    import subprocess

    original_jpg = output_path.parent / (output_path.stem + "_original.jpg")
    converted_jpg = output_path.parent / (output_path.stem + "_converted.jpg")

    try:
        subprocess.run(['magick', '-density', '300', str(svg_path), str(original_jpg)],
                      check=True, capture_output=True)
        subprocess.run(['magick', '-density', '300', str(output_path), str(converted_jpg)],
                      check=True, capture_output=True)
        print(f"  Original JPEG: {original_jpg}")
        print(f"  Converted JPEG: {converted_jpg}")
        print(f"\n  View the JPEGs to verify the conversion quality!")
    except Exception as e:
        print(f"  ⚠️  Failed to create JPEG comparison: {e}")


def main():
    """CLI entry for t2p_convert."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="t2p_convert",
        description="Convert all SVG <text>/<tspan>/<textPath> to <path> outlines using HarfBuzz shaping.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  t2p_convert samples/test_text_to_path.svg\n"
               "  t2p_convert samples/test_text_to_path.svg /tmp/out.svg --precision 6\n",
    )
    parser.add_argument("input_svg", help="Input SVG file")
    parser.add_argument("output_svg", nargs="?", help="Output SVG file (default: <input>_rust_paths.svg)")
    parser.add_argument(
        "--precision",
        type=int,
        default=28,
        help="Decimal places for generated path coordinates (use 6 to roughly match Inkscape path size).",
    )
    args = parser.parse_args()

    input_path = Path(args.input_svg)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    output_path = Path(args.output_svg) if args.output_svg else input_path.parent / f"{input_path.stem}_rust_paths{input_path.suffix}"

    convert_svg_text_to_paths(input_path, output_path, precision=args.precision)


if __name__ == "__main__":
    main()
