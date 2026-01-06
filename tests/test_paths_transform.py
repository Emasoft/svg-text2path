"""Unit tests for svg_text2path.paths.transform module.

Tests parse_transform_matrix() with translate, rotate, scale, and combined transforms.
Tests apply_transform_to_path() for path coordinate scaling.
"""

import pytest

from svg_text2path.paths.transform import (
    apply_transform_to_path,
    parse_transform_matrix,
)


class TestParseTransformMatrixTranslate:
    """Tests for parse_transform_matrix() with translate transforms."""

    def test_translate_xy_returns_correct_matrix(self):
        """Translate with x and y values produces correct translation matrix."""
        result = parse_transform_matrix("translate(10, 20)")
        assert result is not None
        a, b, c, d, e, f = result
        assert a == pytest.approx(1.0)
        assert b == pytest.approx(0.0)
        assert c == pytest.approx(0.0)
        assert d == pytest.approx(1.0)
        assert e == pytest.approx(10.0)
        assert f == pytest.approx(20.0)

    def test_translate_x_only_defaults_y_to_zero(self):
        """Translate with only x value defaults y translation to zero."""
        result = parse_transform_matrix("translate(15)")
        assert result is not None
        a, b, c, d, e, f = result
        assert e == pytest.approx(15.0)
        assert f == pytest.approx(0.0)

    def test_translate_negative_values(self):
        """Translate handles negative coordinate values."""
        result = parse_transform_matrix("translate(-5.5, -10.25)")
        assert result is not None
        _, _, _, _, e, f = result
        assert e == pytest.approx(-5.5)
        assert f == pytest.approx(-10.25)


class TestParseTransformMatrixRotate:
    """Tests for parse_transform_matrix() with rotate transforms."""

    def test_rotate_returns_none_unsupported(self):
        """Rotate transform is unsupported and returns None."""
        result = parse_transform_matrix("rotate(45)")
        assert result is None

    def test_rotate_with_origin_returns_none(self):
        """Rotate with origin point is unsupported and returns None."""
        result = parse_transform_matrix("rotate(30, 100, 100)")
        assert result is None


class TestParseTransformMatrixScale:
    """Tests for parse_transform_matrix() with scale transforms."""

    def test_scale_uniform_uses_same_value_for_xy(self):
        """Uniform scale applies same factor to x and y."""
        result = parse_transform_matrix("scale(2)")
        assert result is not None
        a, b, c, d, e, f = result
        assert a == pytest.approx(2.0)
        assert d == pytest.approx(2.0)
        assert b == pytest.approx(0.0)
        assert c == pytest.approx(0.0)

    def test_scale_nonuniform_uses_separate_xy_values(self):
        """Non-uniform scale applies different factors to x and y."""
        result = parse_transform_matrix("scale(3, 0.5)")
        assert result is not None
        a, b, c, d, e, f = result
        assert a == pytest.approx(3.0)
        assert d == pytest.approx(0.5)

    def test_scale_fractional_values(self):
        """Scale handles fractional scale factors."""
        result = parse_transform_matrix("scale(0.25, 1.75)")
        assert result is not None
        a, _, _, d, _, _ = result
        assert a == pytest.approx(0.25)
        assert d == pytest.approx(1.75)


class TestParseTransformMatrixCombined:
    """Tests for parse_transform_matrix() with combined transforms."""

    def test_translate_then_scale_applies_left_to_right(self):
        """Combined translate+scale applies transforms left-to-right."""
        result = parse_transform_matrix("translate(10, 20) scale(2)")
        assert result is not None
        a, b, c, d, e, f = result
        assert a == pytest.approx(2.0)
        assert d == pytest.approx(2.0)
        assert e == pytest.approx(10.0)
        assert f == pytest.approx(20.0)

    def test_scale_then_translate(self):
        """Scale then translate produces different result than translate then scale."""
        result = parse_transform_matrix("scale(2) translate(10, 20)")
        assert result is not None
        a, b, c, d, e, f = result
        assert a == pytest.approx(2.0)
        assert d == pytest.approx(2.0)
        assert e == pytest.approx(20.0)
        assert f == pytest.approx(40.0)

    def test_combined_with_rotate_returns_none(self):
        """Combined transforms containing rotate returns None."""
        result = parse_transform_matrix("translate(10, 20) rotate(45) scale(2)")
        assert result is None

    def test_empty_string_returns_identity(self):
        """Empty transform string returns identity matrix."""
        result = parse_transform_matrix("")
        assert result == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def test_none_input_returns_identity(self):
        """None input returns identity matrix."""
        result = parse_transform_matrix(None)
        assert result == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class TestApplyTransformToPath:
    """Tests for apply_transform_to_path() function."""

    def test_identity_scale_returns_unchanged_path(self):
        """Scale of 1.0 returns path unchanged."""
        path = "M 10 20 L 30 40"
        result = apply_transform_to_path(path, 1.0, 1.0)
        assert result == path

    def test_uniform_scale_multiplies_all_coordinates(self):
        """Uniform scale multiplies all coordinates by factor."""
        path = "M 10 20 L 30 40"
        result = apply_transform_to_path(path, 2.0, 2.0)
        assert "20.00" in result
        assert "40.00" in result
        assert "60.00" in result
        assert "80.00" in result

    def test_nonuniform_scale_applies_xy_separately(self):
        """Non-uniform scale applies x factor to x coords, y factor to y coords."""
        path = "M 10 20 L 30 40"
        result = apply_transform_to_path(path, 2.0, 0.5)
        parts = result.split()
        assert "M" in parts
        assert "20.00" in parts
        assert "10.00" in parts
        assert "60.00" in parts
        assert "20.00" in parts

    def test_preserves_path_commands(self):
        """Scaling preserves all SVG path commands."""
        path = "M 0 0 L 10 10 H 20 V 30 C 40 40 50 50 60 60 Z"
        result = apply_transform_to_path(path, 2.0, 2.0)
        assert "M" in result
        assert "L" in result
        assert "H" in result
        assert "V" in result
        assert "C" in result
        assert "Z" in result

    def test_handles_negative_coordinates(self):
        """Scaling handles negative coordinates correctly."""
        path = "M -10 -20 L 30 -40"
        result = apply_transform_to_path(path, 2.0, 2.0)
        assert "-20.00" in result
        assert "-40.00" in result
        assert "60.00" in result
        assert "-80.00" in result
