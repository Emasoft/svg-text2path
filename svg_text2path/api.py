"""Main API for svg-text2path.

Provides the Text2PathConverter class for converting SVG text elements to paths.

Example:
    >>> from svg_text2path import Text2PathConverter
    >>> converter = Text2PathConverter()
    >>> converter.convert_file("input.svg", "output.svg")
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import (
    Element,
    ElementTree,
)
from xml.etree.ElementTree import (
    register_namespace as _register_namespace,
)

from fontTools.pens.recordingPen import RecordingPen  # type: ignore[import-untyped]
from svg.path import parse_path

from svg_text2path.config import Config
from svg_text2path.exceptions import FontNotFoundError, SVGParseError
from svg_text2path.fonts.cache import FontCache
from svg_text2path.shaping.bidi import BiDiRun, detect_base_direction, get_visual_runs
from svg_text2path.shaping.harfbuzz import create_hb_font, shape_run
from svg_text2path.svg.parser import (
    SVG_NS,
    XLINK_NS,
    get_tag_name,
    parse_svg,
    parse_svg_string,
    write_svg,
)

# Element and ElementTree are imported directly above (needed for runtime cast())


@dataclass
class ConversionResult:
    """Result of a text-to-path conversion."""

    success: bool
    """Whether conversion completed without errors."""

    input_format: str
    """Detected input format (e.g., 'file', 'string', 'element')."""

    output: Path | str | Element | None
    """Output path, string, or element depending on conversion method."""

    errors: list[str] = field(default_factory=list)
    """List of error messages if conversion failed."""

    warnings: list[str] = field(default_factory=list)
    """List of warning messages (conversion may still succeed)."""

    text_count: int = 0
    """Number of text elements found in input."""

    path_count: int = 0
    """Number of text elements successfully converted to paths."""

    missing_fonts: list[str] = field(default_factory=list)
    """List of font specifications that could not be resolved."""

    input_valid: bool | None = None
    """Whether input SVG passed validation (None if not validated)."""

    output_valid: bool | None = None
    """Whether output SVG passed validation (None if not validated)."""

    validation_issues: list[str] = field(default_factory=list)
    """List of SVG validation issues found."""


class Text2PathConverter:
    """Main converter class for SVG text-to-path conversion.

    This class provides the primary API for converting SVG text elements
    to vector path outlines using HarfBuzz text shaping.

    Example:
        >>> converter = Text2PathConverter()
        >>> result = converter.convert_file("input.svg", "output.svg")
        >>> print(f"Converted {result.path_count} text elements")

    Attributes:
        font_cache: FontCache instance for font resolution.
        precision: Decimal precision for path coordinates.
        preserve_styles: Whether to preserve font metadata on paths.
        config: Full configuration object.
    """

    def __init__(
        self,
        font_cache: FontCache | None = None,
        precision: int = 6,
        preserve_styles: bool = False,
        log_level: str = "WARNING",
        config: Config | None = None,
        auto_download_fonts: bool = False,
        validate_svg: bool = False,
    ) -> None:
        """Initialize the converter.

        Args:
            font_cache: Optional FontCache to reuse across calls.
                       If None, a new one will be created.
            precision: Decimal precision for path coordinates (default 6).
            preserve_styles: Keep font metadata on converted paths.
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
            config: Optional full Config object. If provided, overrides
                   individual precision/preserve_styles/log_level args.
            auto_download_fonts: If True, attempt to download missing fonts
                using fontget or fnt tools.
            validate_svg: If True, validate input and output SVG files
                using svg-matrix (requires Bun).
        """
        self.config = config or Config.load()
        self.auto_download_fonts = auto_download_fonts
        self.validate_svg = validate_svg

        # Override config with explicit args if provided
        if precision != 6:
            self.config.conversion.precision = precision
        if preserve_styles:
            self.config.conversion.preserve_styles = preserve_styles
        if log_level != "WARNING":
            self.config.log_level = log_level

        self._font_cache = font_cache
        self._path_map: dict[str, Any] = {}  # id -> svg.path.Path for textPath
        self._hb_font_cache: dict[
            tuple[int, int, float], Any
        ] = {}  # HarfBuzz font cache

    @property
    def font_cache(self) -> FontCache:
        """Get or create the FontCache instance."""
        if self._font_cache is None:
            self._font_cache = FontCache()
        return self._font_cache

    @property
    def precision(self) -> int:
        """Get path coordinate precision."""
        return self.config.conversion.precision

    @property
    def preserve_styles(self) -> bool:
        """Get preserve_styles setting."""
        return self.config.conversion.preserve_styles

    def convert_file(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
    ) -> ConversionResult:
        """Convert all text elements in an SVG file to paths.

        Args:
            input_path: Path to input SVG file.
            output_path: Path for output SVG. If None, uses
                        {name}_text2path.svg in same directory.

        Returns:
            ConversionResult with conversion details.

        Raises:
            FileNotFoundError: If input file doesn't exist.
            SVGParseError: If SVG parsing fails.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input SVG not found: {input_path}")

        # Default output path
        if output_path is None:
            suffix = self.config.conversion.output_suffix
            output_path = input_path.with_stem(input_path.stem + suffix)
        else:
            output_path = Path(output_path)

        # Validate input SVG if enabled
        if self.validate_svg:
            from svg_text2path.tools.svg_validator import validate_svg_file

            input_validation = validate_svg_file(input_path)
            # Store validation results (will be added to result later)
            input_valid = input_validation.valid
            input_issues = [
                f"Input: {i.get('reason', str(i))}" for i in input_validation.issues
            ]
            if input_validation.error:
                input_issues.append(f"Input validation error: {input_validation.error}")
        else:
            input_valid = None
            input_issues = []

        # Parse SVG
        try:
            tree = parse_svg(input_path)
        except Exception as e:
            raise SVGParseError(
                f"Failed to parse SVG: {e}", source=str(input_path)
            ) from e

        # Convert
        result = self._convert_tree(tree, input_format="file")

        # Write output
        if result.success or result.path_count > 0:
            write_svg(tree, output_path)
            result.output = output_path

            # Validate output SVG if enabled
            if self.validate_svg:
                from svg_text2path.tools.svg_validator import validate_svg_file

                output_validation = validate_svg_file(output_path)
                result.output_valid = output_validation.valid
                for issue in output_validation.issues:
                    input_issues.append(f"Output: {issue.get('reason', str(issue))}")
                if output_validation.error:
                    input_issues.append(
                        f"Output validation error: {output_validation.error}"
                    )
            else:
                result.output_valid = None

        # Set validation results on result object
        result.input_valid = input_valid
        result.validation_issues = input_issues

        return result

    def convert_string(
        self, svg_content: str, return_result: bool = False
    ) -> str | tuple[str, ConversionResult]:
        """Convert all text elements in an SVG string to paths.

        Args:
            svg_content: SVG content as string.
            return_result: If True, also return ConversionResult with
                validation info. Default False for backward compatibility.

        Returns:
            Converted SVG as string, or tuple of (string, ConversionResult)
            if return_result is True.

        Raises:
            SVGParseError: If SVG parsing fails.
        """
        # Validate input SVG if enabled
        input_valid = None
        input_issues: list[str] = []
        if self.validate_svg:
            from svg_text2path.tools.svg_validator import validate_svg_string

            input_validation = validate_svg_string(svg_content)
            input_valid = input_validation.valid
            input_issues = [
                f"Input: {i.get('reason', str(i))}" for i in input_validation.issues
            ]
            if input_validation.error:
                input_issues.append(f"Input validation error: {input_validation.error}")

        # Parse SVG string
        try:
            root = parse_svg_string(svg_content)
            # Wrap in ElementTree for consistent handling (use std lib, not defusedxml)
            tree = ElementTree(root)
        except Exception as e:
            raise SVGParseError(f"Failed to parse SVG string: {e}") from e

        # Convert
        result = self._convert_tree(tree, input_format="string")

        # Serialize back to string
        # Register namespaces
        _register_namespace("", SVG_NS)
        _register_namespace("xlink", XLINK_NS)

        buffer = StringIO()
        tree.write(buffer, encoding="unicode", xml_declaration=True)
        output_svg = buffer.getvalue()

        # Validate output SVG if enabled
        output_valid = None
        if self.validate_svg:
            from svg_text2path.tools.svg_validator import validate_svg_string

            output_validation = validate_svg_string(output_svg)
            output_valid = output_validation.valid
            for issue in output_validation.issues:
                input_issues.append(f"Output: {issue.get('reason', str(issue))}")
            if output_validation.error:
                input_issues.append(
                    f"Output validation error: {output_validation.error}"
                )

        # Set validation results
        result.input_valid = input_valid
        result.output_valid = output_valid
        result.validation_issues = input_issues
        result.output = output_svg

        if return_result:
            return output_svg, result
        return output_svg

    def convert_tree(self, tree: ElementTree) -> ElementTree:
        """Convert all text elements in an ElementTree to paths.

        Args:
            tree: ElementTree containing SVG.

        Returns:
            Modified ElementTree with text converted to paths.
        """
        self._convert_tree(tree, input_format="tree")
        return tree

    def convert_element(self, text_elem: Element) -> Element | None:
        """Convert a single text element to a path element.

        Args:
            text_elem: A <text> element to convert.

        Returns:
            A <path> or <g> element containing the converted paths,
            or None if conversion failed.
        """
        return self._convert_single_text(text_elem)

    def convert_batch(
        self,
        inputs: list[Path | str],
        output_dir: Path | None = None,
    ) -> list[ConversionResult]:
        """Convert multiple SVG files in batch.

        Unlike single file conversion, batch mode continues on errors
        and logs them instead of raising exceptions.

        Args:
            inputs: List of input file paths.
            output_dir: Directory for output files. If None, outputs
                       are placed alongside inputs.

        Returns:
            List of ConversionResult objects, one per input.
        """
        results: list[ConversionResult] = []

        for input_item in inputs:
            input_path = Path(input_item)

            # Determine output path
            if output_dir:
                suffix = self.config.conversion.output_suffix
                output_path = output_dir / (input_path.stem + suffix + ".svg")
            else:
                output_path = None

            try:
                result = self.convert_file(input_path, output_path)
            except Exception as e:
                result = ConversionResult(
                    success=False,
                    input_format="file",
                    output=None,
                    errors=[str(e)],
                )

            results.append(result)

        return results

    def _convert_tree(self, tree: ElementTree, input_format: str) -> ConversionResult:
        """Internal method to convert all text in an ElementTree."""
        root = tree.getroot()
        if root is None:
            raise SVGParseError(
                "Failed to parse SVG: empty or invalid XML document", source="tree"
            )

        result = ConversionResult(
            success=True,
            input_format=input_format,
            output=None,
        )

        # Build path map for textPath references
        self._path_map.clear()
        self._collect_paths(root)

        # Find all text elements
        text_elements = self._collect_text_with_parents(root)
        result.text_count = len(text_elements)

        # Convert each text element
        for parent, text_elem in text_elements:
            try:
                converted = self._convert_single_text(text_elem)
                if converted is not None:
                    # Replace text element with converted path(s)
                    idx = list(parent).index(text_elem)
                    parent.remove(text_elem)
                    parent.insert(idx, converted)
                    result.path_count += 1
            except FontNotFoundError as e:
                result.warnings.append(f"Missing font: {e.font_family}")
                result.missing_fonts.append(f"{e.font_family} (weight={e.weight})")
            except Exception as e:
                elem_id = text_elem.get("id", "unknown")
                result.warnings.append(f"Failed to convert {elem_id}: {e}")

        if result.path_count < result.text_count:
            result.success = False

        return result

    def _collect_paths(self, root: Element) -> None:
        """Collect all path definitions for textPath references."""
        for elem in root.iter():
            tag = get_tag_name(elem)
            if tag == "path":
                path_id = elem.get("id")
                d = elem.get("d")
                if path_id and d:
                    with contextlib.suppress(Exception):
                        self._path_map[path_id] = parse_path(d)

    def _collect_text_with_parents(
        self, root: Element
    ) -> list[tuple[Element, Element]]:
        """Collect (parent, text_element) tuples."""
        text_elements: list[tuple[Element, Element]] = []

        def collect(parent: Element) -> None:
            for child in parent:
                tag = get_tag_name(child)
                if tag == "text":
                    text_elements.append((parent, child))
                collect(child)

        collect(root)
        return text_elements

    def _convert_single_text(self, text_elem: Element) -> Element | None:
        """Convert a single text element to path(s)."""
        # Extract text content
        text_content = self._extract_text_content(text_elem)
        if not text_content:
            return None

        # Get styling attributes with defaults
        font_family = self._get_attr(text_elem, "font-family", "Arial")
        if font_family is None:
            font_family = "Arial"
        font_family = font_family.split(",")[0].strip().strip("'\"")

        raw_size = self._get_attr(text_elem, "font-size", "16")
        if raw_size is None:
            raw_size = "16"
        font_size = self._parse_font_size(raw_size)

        font_weight = self._get_attr(text_elem, "font-weight", "400")
        if font_weight is None:
            font_weight = "400"
        try:
            weight = int(font_weight)
        except ValueError:
            weight_map = {
                "normal": 400,
                "bold": 700,
                "lighter": 300,
                "bolder": 700,
            }
            weight = weight_map.get(font_weight.lower(), 400)

        font_style = self._get_attr(text_elem, "font-style", "normal")
        if font_style is None:
            font_style = "normal"

        # Get position
        x = float(text_elem.get("x", "0"))
        y = float(text_elem.get("y", "0"))

        # Get text anchor
        text_anchor = self._get_attr(text_elem, "text-anchor", "start")
        if text_anchor is None:
            text_anchor = "start"

        # Get font from cache (with optional auto-download of missing fonts)
        try:
            font_result = self.font_cache.get_font(
                font_family,
                weight=weight,
                style=font_style,
                auto_download=self.auto_download_fonts,
            )
            if font_result is None:
                # Font not found, return None to indicate conversion not possible
                return None
            tt_font, font_blob, face_idx = font_result
        except FontNotFoundError:
            raise

        # Create HarfBuzz font (with caching to avoid recreating for each text element)
        cache_key = (id(font_blob), face_idx, font_size)
        if cache_key not in self._hb_font_cache:
            self._hb_font_cache[cache_key] = create_hb_font(
                font_blob, face_idx, font_size
            )
        hb_font = self._hb_font_cache[cache_key]

        # Get font metrics for scaling
        units_per_em = tt_font["head"].unitsPerEm
        scale = font_size / units_per_em

        # Skip BiDi processing for pure ASCII text (performance optimization)
        if text_content.isascii():
            # Pure ASCII - single LTR run, no BiDi processing needed
            runs = [
                BiDiRun(
                    text=text_content,
                    start=0,
                    end=len(text_content),
                    level=0,
                    direction="ltr",
                )
            ]
        else:
            # Detect text direction for non-ASCII text
            base_direction = detect_base_direction(text_content)
            # Get visual runs for BiDi (handles RTL, mixed direction)
            runs = get_visual_runs(text_content, base_direction)

        # Shape each run and collect glyphs
        all_paths: list[str] = []
        cursor_x = x
        cursor_y = y

        # Pre-fetch glyph set once (performance optimization: O(1) instead of O(n))
        glyph_set = tt_font.getGlyphSet()

        for run in runs:
            glyphs = shape_run(
                run.text,
                hb_font,
                direction=run.direction,
            )

            # Generate path for each glyph
            for glyph in glyphs:
                if glyph.glyph_id == 0:
                    continue  # Skip .notdef

                # Get glyph outline
                glyph_name = tt_font.getGlyphName(glyph.glyph_id)

                if glyph_name not in glyph_set:
                    # HarfBuzz advances are already in pixels
                    cursor_x += glyph.x_advance
                    continue

                # Record glyph outline
                pen = RecordingPen()
                glyph_set[glyph_name].draw(pen)

                if pen.value:
                    # Transform and position glyph (HarfBuzz offsets in pixels)
                    glyph_x = cursor_x + glyph.x_offset
                    glyph_y = cursor_y - glyph.y_offset  # SVG y is inverted

                    path_d = self._transform_glyph(
                        pen.value,
                        glyph_x,
                        glyph_y,
                        scale,  # Glyph outlines need scaling (font units → pixels)
                        -scale,  # Flip Y
                    )

                    if path_d:
                        all_paths.append(path_d)

                # HarfBuzz advances are already in pixels (font scaled, positions /64)
                cursor_x += glyph.x_advance
                cursor_y += glyph.y_advance

        if not all_paths:
            return None

        # Apply text anchor adjustment
        total_width = cursor_x - x
        anchor_offset = 0.0
        if text_anchor == "middle":
            anchor_offset = -total_width / 2
        elif text_anchor == "end":
            anchor_offset = -total_width

        # Create path element (standard Element, not defusedxml - parsing only)
        path_elem = Element(f"{{{SVG_NS}}}path")
        path_elem.set("d", " ".join(all_paths))

        # Copy relevant attributes
        elem_id = text_elem.get("id")
        if elem_id:
            path_elem.set("id", elem_id + "_path")

        # Apply anchor offset via transform
        transform = text_elem.get("transform", "")
        if anchor_offset != 0:
            if transform:
                transform = f"translate({anchor_offset}, 0) {transform}"
            else:
                transform = f"translate({anchor_offset}, 0)"

        if transform:
            path_elem.set("transform", transform)

        # Copy fill/stroke styling
        for attr in ["fill", "stroke", "stroke-width", "opacity", "fill-opacity"]:
            val = self._get_attr(text_elem, attr)
            if val:
                path_elem.set(attr, val)

        return path_elem

    def _extract_text_content(self, elem: Element) -> str:
        """Extract text content from text element and tspans."""
        content = elem.text or ""

        # Check for tspan children
        for child in elem:
            tag = get_tag_name(child)
            if tag in ("tspan", "textPath"):
                if child.text:
                    content += child.text
                if child.tail:
                    content += child.tail

        return content.strip()

    def _get_attr(
        self, elem: Element, key: str, default: str | None = None
    ) -> str | None:
        """Get attribute from element, checking style string first."""
        # Check style string
        style = elem.get("style", "")
        match = re.search(rf"{key}:\s*([^;]+)", style)
        if match:
            return match.group(1).strip()

        # Check direct attribute
        return elem.get(key, default)

    def _parse_font_size(self, raw_size: str) -> float:
        """Parse font-size value with unit conversion."""
        raw_size = raw_size.strip()

        # Handle pt units
        if "pt" in raw_size:
            match = re.search(r"([\d.]+)", raw_size)
            if match:
                return float(match.group(1)) * 1.3333

        # Handle em units
        if "em" in raw_size:
            match = re.search(r"([\d.]+)", raw_size)
            if match:
                return float(match.group(1)) * 16  # Assume 16px base

        # Default px
        match = re.search(r"([\d.]+)", raw_size)
        if match:
            return float(match.group(1))

        return 16.0

    def _transform_glyph(
        self,
        recording: list[tuple[str, tuple[Any, ...]]],
        x: float,
        y: float,
        scale_x: float,
        scale_y: float,
    ) -> str:
        """Transform glyph recording to SVG path at position with scale."""
        precision = self.precision
        fmt = f"{{:.{precision}f}}"

        commands: list[str] = []

        for op, args in recording:
            if op == "moveTo":
                px, py = args[0]
                tx = x + px * scale_x
                ty = y + py * scale_y
                commands.append(f"M {fmt.format(tx)} {fmt.format(ty)}")

            elif op == "lineTo":
                px, py = args[0]
                tx = x + px * scale_x
                ty = y + py * scale_y
                commands.append(f"L {fmt.format(tx)} {fmt.format(ty)}")

            elif op == "qCurveTo":
                # Quadratic curves
                if len(args) == 2:
                    x1, y1 = args[0]
                    px, py = args[1]
                    tx1 = x + x1 * scale_x
                    ty1 = y + y1 * scale_y
                    tx = x + px * scale_x
                    ty = y + py * scale_y
                    q_cmd = f"Q {fmt.format(tx1)} {fmt.format(ty1)}"
                    q_cmd += f" {fmt.format(tx)} {fmt.format(ty)}"
                    commands.append(q_cmd)
                else:
                    # Multiple control points with implied on-curve points
                    for i in range(len(args) - 1):
                        x1, y1 = args[i]
                        if i == len(args) - 2:
                            px, py = args[i + 1]
                        else:
                            x2, y2 = args[i + 1]
                            px, py = (x1 + x2) / 2, (y1 + y2) / 2

                        tx1 = x + x1 * scale_x
                        ty1 = y + y1 * scale_y
                        tx = x + px * scale_x
                        ty = y + py * scale_y
                        q_cmd = f"Q {fmt.format(tx1)} {fmt.format(ty1)}"
                        q_cmd += f" {fmt.format(tx)} {fmt.format(ty)}"
                        commands.append(q_cmd)

            elif op == "curveTo":
                # Cubic curves
                if len(args) >= 3:
                    x1, y1 = args[0]
                    x2, y2 = args[1]
                    px, py = args[2]
                    tx1 = x + x1 * scale_x
                    ty1 = y + y1 * scale_y
                    tx2 = x + x2 * scale_x
                    ty2 = y + y2 * scale_y
                    tx = x + px * scale_x
                    ty = y + py * scale_y
                    c_cmd = f"C {fmt.format(tx1)} {fmt.format(ty1)}"
                    c_cmd += f" {fmt.format(tx2)} {fmt.format(ty2)}"
                    c_cmd += f" {fmt.format(tx)} {fmt.format(ty)}"
                    commands.append(c_cmd)

            elif op == "closePath":
                commands.append("Z")

        return " ".join(commands)
