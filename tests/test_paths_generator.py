"""Unit tests for svg_text2path.paths.generator module.

Tests cover:
- recording_pen_to_svg_path() / glyph_to_path() basic functionality
- Handling of empty recordings (empty glyphs)
- Path data format (M, L, Q, C, Z commands)
- Precision handling for coordinate formatting
- _parse_num_list() for SVG attribute parsing
"""

from svg_text2path.paths.generator import (
    _parse_num_list,
    glyph_to_path,
    recording_pen_to_svg_path,
)


class TestRecordingPenToSvgPath:
    """Tests for recording_pen_to_svg_path function."""

    def test_basic_moveto_lineto_closepath(self) -> None:
        """Verify basic M, L, Z commands from moveTo, lineTo, closePath ops."""
        # Realistic recording: a simple triangle path
        recording = [
            ("moveTo", ((0.0, 0.0),)),
            ("lineTo", ((100.0, 0.0),)),
            ("lineTo", ((50.0, 86.6),)),
            ("closePath", ()),
        ]
        result = recording_pen_to_svg_path(recording, precision=2)
        # Verify the path contains the expected commands
        assert result.startswith("M 0.00 0.00")
        assert "L 100.00 0.00" in result
        assert "L 50.00 86.60" in result
        assert result.endswith("Z")

    def test_empty_recording_returns_empty_string(self) -> None:
        """Verify empty glyph recording produces empty path string."""
        recording: list = []
        result = recording_pen_to_svg_path(recording)
        assert result == ""

    def test_quadratic_bezier_simple(self) -> None:
        """Verify simple quadratic Bezier curve (Q command) with one control point."""
        # Simple qCurveTo with one control point + end point
        recording = [
            ("moveTo", ((0.0, 0.0),)),
            ("qCurveTo", ((50.0, 100.0), (100.0, 0.0))),
            ("closePath", ()),
        ]
        result = recording_pen_to_svg_path(recording, precision=1)
        assert "M 0.0 0.0" in result
        assert "Q 50.0 100.0 100.0 0.0" in result
        assert "Z" in result

    def test_cubic_bezier_curveto(self) -> None:
        """Verify cubic Bezier curve (C command) with two control points."""
        # Cubic curveTo with 2 control points + end point
        recording = [
            ("moveTo", ((0.0, 0.0),)),
            ("curveTo", ((25.0, 100.0), (75.0, 100.0), (100.0, 0.0))),
            ("closePath", ()),
        ]
        result = recording_pen_to_svg_path(recording, precision=1)
        assert "M 0.0 0.0" in result
        assert "C 25.0 100.0 75.0 100.0 100.0 0.0" in result
        assert "Z" in result

    def test_precision_affects_decimal_places(self) -> None:
        """Verify precision parameter controls number of decimal places in output."""
        recording = [
            ("moveTo", ((1.123456789, 2.987654321),)),
        ]
        # Low precision
        result_low = recording_pen_to_svg_path(recording, precision=2)
        assert "M 1.12 2.99" in result_low
        # High precision
        result_high = recording_pen_to_svg_path(recording, precision=6)
        assert "M 1.123457 2.987654" in result_high


class TestGlyphToPathAlias:
    """Tests for glyph_to_path alias function."""

    def test_alias_is_same_function(self) -> None:
        """Verify glyph_to_path is an alias for recording_pen_to_svg_path."""
        assert glyph_to_path is recording_pen_to_svg_path

    def test_alias_produces_same_result(self) -> None:
        """Verify glyph_to_path produces identical output."""
        recording = [
            ("moveTo", ((10.0, 20.0),)),
            ("lineTo", ((30.0, 40.0),)),
            ("closePath", ()),
        ]
        result1 = recording_pen_to_svg_path(recording, precision=3)
        result2 = glyph_to_path(recording, precision=3)
        assert result1 == result2


class TestParseNumList:
    """Tests for _parse_num_list helper function."""

    def test_space_separated_numbers(self) -> None:
        """Verify parsing of space-separated number list."""
        result = _parse_num_list("1.5 2.0 3.5")
        assert result == [1.5, 2.0, 3.5]

    def test_comma_separated_numbers(self) -> None:
        """Verify parsing of comma-separated number list."""
        result = _parse_num_list("10,20,30")
        assert result == [10.0, 20.0, 30.0]

    def test_mixed_separators(self) -> None:
        """Verify parsing with mixed space and comma separators."""
        result = _parse_num_list("1.5, 2.0  3.5,4.0")
        assert result == [1.5, 2.0, 3.5, 4.0]

    def test_empty_string_returns_empty_list(self) -> None:
        """Verify empty input returns empty list."""
        result = _parse_num_list("")
        assert result == []

    def test_invalid_values_are_skipped(self) -> None:
        """Verify non-numeric values are silently skipped."""
        result = _parse_num_list("1.0 abc 2.0 def 3.0")
        assert result == [1.0, 2.0, 3.0]


class TestQCurveToMultipleControlPoints:
    """Tests for qCurveTo with multiple control points (implied on-curve points)."""

    def test_qcurveto_three_points_generates_two_q_commands(self) -> None:
        """Verify qCurveTo with 3 points creates implied on-curve point."""
        # TrueType can have multiple control points with implied on-curve points
        # 3 points: cp1, cp2, end -> generates 2 Q commands
        recording = [
            ("moveTo", ((0.0, 0.0),)),
            ("qCurveTo", ((20.0, 40.0), (40.0, 40.0), (60.0, 0.0))),
            ("closePath", ()),
        ]
        result = recording_pen_to_svg_path(recording, precision=1)
        # First Q uses cp1 and implied midpoint: (20+40)/2=30, (40+40)/2=40
        assert "Q 20.0 40.0 30.0 40.0" in result
        # Second Q uses cp2 and actual end point
        assert "Q 40.0 40.0 60.0 0.0" in result
