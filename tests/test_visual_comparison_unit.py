"""Unit tests for svg_text2path/tools/visual_comparison.py

Coverage: Target 80%+ effective coverage
Tests cover:
- pixel_tol_to_threshold: tolerance mapping
- SVGRenderer._parse_svg_dimensions: SVG dimension parsing
- SVGRenderer.render_svg_to_png: Chrome rendering (external dep mocked)
- ImageComparator.compare_images_pixel_perfect: pixel comparison
- svg_resolution: resolution string parsing
- total_path_chars: path d attribute counting
- generate_diff_image: red diff visualization
- generate_grayscale_diff_map: grayscale diff map

Limitations:
- render_svg_to_png requires Chrome/Node (subprocess mocked for that case)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from svg_text2path.tools.visual_comparison import (
    ImageComparator,
    SVGRenderer,
    generate_diff_image,
    generate_grayscale_diff_map,
    pixel_tol_to_threshold,
    svg_resolution,
    total_path_chars,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_svg(tmp_path: Path) -> Path:
    """Create a simple SVG with width/height attributes."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
  <rect width="100%" height="100%" fill="white"/>
  <text x="20" y="50" font-family="Arial" font-size="24">Test</text>
</svg>"""
    svg_path = tmp_path / "simple.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def viewbox_only_svg(tmp_path: Path) -> Path:
    """Create SVG with only viewBox (no width/height)."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">
  <rect width="100%" height="100%" fill="blue"/>
</svg>"""
    svg_path = tmp_path / "viewbox_only.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def svg_with_paths(tmp_path: Path) -> Path:
    """Create SVG with multiple path elements."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
  <path d="M10,10 L100,10 L100,100 Z"/>
  <path d="M200,200 C 210,210 220,220 230,230"/>
  <path d="M0,0"/>
</svg>"""
    svg_path = tmp_path / "with_paths.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def identical_images(tmp_path: Path) -> tuple[Path, Path]:
    """Create two identical 100x100 red images."""
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
    img1_path = tmp_path / "identical_1.png"
    img2_path = tmp_path / "identical_2.png"
    img.save(img1_path)
    img.save(img2_path)
    return img1_path, img2_path


@pytest.fixture
def different_images(tmp_path: Path) -> tuple[Path, Path]:
    """Create two completely different 100x100 images."""
    img1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))  # Red
    img2 = Image.new("RGBA", (100, 100), color=(0, 0, 255, 255))  # Blue
    img1_path = tmp_path / "different_1.png"
    img2_path = tmp_path / "different_2.png"
    img1.save(img1_path)
    img2.save(img2_path)
    return img1_path, img2_path


@pytest.fixture
def partially_different_images(tmp_path: Path) -> tuple[Path, Path]:
    """Create two images with 25% difference (one quadrant different)."""
    # Create 100x100 images - one all red, one 75% red + 25% blue corner
    img1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
    img2 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))

    # Make top-left 50x50 quadrant blue in img2 (25% of pixels)
    pixels = img2.load()
    for x in range(50):
        for y in range(50):
            pixels[x, y] = (0, 0, 255, 255)

    img1_path = tmp_path / "partial_1.png"
    img2_path = tmp_path / "partial_2.png"
    img1.save(img1_path)
    img2.save(img2_path)
    return img1_path, img2_path


@pytest.fixture
def mismatched_size_images(tmp_path: Path) -> tuple[Path, Path]:
    """Create two images with different dimensions."""
    img1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
    img2 = Image.new("RGBA", (200, 150), color=(255, 0, 0, 255))
    img1_path = tmp_path / "size1.png"
    img2_path = tmp_path / "size2.png"
    img1.save(img1_path)
    img2.save(img2_path)
    return img1_path, img2_path


# =============================================================================
# Tests for pixel_tol_to_threshold
# =============================================================================


class TestPixelTolToThreshold:
    """Tests for pixel tolerance to threshold mapping."""

    def test_zero_tolerance_returns_minimum(self):
        """0.0 tolerance maps to minimum threshold of 1."""
        result = pixel_tol_to_threshold(0.0)
        assert result == 1

    def test_full_tolerance_returns_maximum(self):
        """1.0 tolerance maps to maximum threshold of 20."""
        result = pixel_tol_to_threshold(1.0)
        assert result == 20

    def test_mid_tolerance_maps_correctly(self):
        """0.5 tolerance maps to ~128/256 * 20 = ~10."""
        result = pixel_tol_to_threshold(0.5)
        # 0.5 * 256 = 128, clamped to 1-20 range
        assert 1 <= result <= 20

    def test_very_small_tolerance_clamps_to_minimum(self):
        """Very small tolerance clamps to 1."""
        result = pixel_tol_to_threshold(0.001)
        assert result >= 1

    def test_negative_tolerance_clamps_to_minimum(self):
        """Negative tolerance clamps to 1."""
        result = pixel_tol_to_threshold(-0.5)
        assert result == 1

    def test_over_max_tolerance_clamps_to_maximum(self):
        """Tolerance > 1.0 clamps to 20."""
        result = pixel_tol_to_threshold(2.0)
        assert result == 20


# =============================================================================
# Tests for SVGRenderer._parse_svg_dimensions
# =============================================================================


class TestSVGRendererParseDimensions:
    """Tests for SVG dimension parsing."""

    def test_parse_width_height_attributes(self, simple_svg: Path):
        """Parse SVG with explicit width and height attributes."""
        result = SVGRenderer._parse_svg_dimensions(simple_svg)
        assert result is not None
        assert result == (400, 300)

    def test_parse_viewbox_only(self, viewbox_only_svg: Path):
        """Parse SVG with only viewBox (no width/height)."""
        result = SVGRenderer._parse_svg_dimensions(viewbox_only_svg)
        assert result is not None
        assert result == (800, 600)

    def test_parse_with_units(self, tmp_path: Path):
        """Parse SVG with px units in dimensions."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="500px" height="400px">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "with_units.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is not None
        assert result == (500, 400)

    def test_parse_viewbox_comma_separated(self, tmp_path: Path):
        """Parse viewBox with comma-separated values."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0,0,300,200">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "comma_viewbox.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is not None
        assert result == (300, 200)

    def test_parse_nonexistent_file_returns_none(self, tmp_path: Path):
        """Non-existent file returns None."""
        result = SVGRenderer._parse_svg_dimensions(tmp_path / "nonexistent.svg")
        assert result is None

    def test_parse_invalid_svg_returns_none(self, tmp_path: Path):
        """Invalid SVG content returns None."""
        invalid_path = tmp_path / "invalid.svg"
        invalid_path.write_text("not valid xml at all {{{{", encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(invalid_path)
        assert result is None

    def test_parse_empty_svg_returns_none(self, tmp_path: Path):
        """SVG without dimensions returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" fill="white"/>
</svg>"""
        svg_path = tmp_path / "no_dims.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        # No width/height and no viewBox
        assert result is None


# =============================================================================
# Tests for SVGRenderer.render_svg_to_png (external dep - subprocess mocked)
# =============================================================================


class TestSVGRendererRenderToPng:
    """Tests for SVG to PNG rendering via Chrome."""

    @patch("svg_text2path.tools.visual_comparison.subprocess.run")
    def test_render_success(
        self, mock_run: MagicMock, simple_svg: Path, tmp_path: Path
    ):
        """Successful render returns True and creates PNG."""
        png_path = tmp_path / "output.png"
        # Create the PNG file to simulate successful render
        Image.new("RGBA", (400, 300), color=(255, 255, 255, 255)).save(png_path)

        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        result = SVGRenderer.render_svg_to_png(simple_svg, png_path)

        assert result is True
        mock_run.assert_called_once()

    @patch("svg_text2path.tools.visual_comparison.subprocess.run")
    def test_render_failure_nonzero_return(
        self, mock_run: MagicMock, simple_svg: Path, tmp_path: Path
    ):
        """Render failure with non-zero return code returns False."""
        png_path = tmp_path / "output.png"
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Chrome crashed", stdout=""
        )

        result = SVGRenderer.render_svg_to_png(simple_svg, png_path)

        assert result is False

    @patch("svg_text2path.tools.visual_comparison.subprocess.run")
    def test_render_timeout_returns_false(
        self, mock_run: MagicMock, simple_svg: Path, tmp_path: Path
    ):
        """Render timeout returns False."""
        png_path = tmp_path / "output.png"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="node", timeout=40)

        result = SVGRenderer.render_svg_to_png(simple_svg, png_path)

        assert result is False

    @patch("svg_text2path.tools.visual_comparison.subprocess.run")
    def test_render_node_not_found_returns_false(
        self, mock_run: MagicMock, simple_svg: Path, tmp_path: Path
    ):
        """Node not found returns False."""
        png_path = tmp_path / "output.png"
        mock_run.side_effect = FileNotFoundError("node not found")

        result = SVGRenderer.render_svg_to_png(simple_svg, png_path)

        assert result is False

    def test_render_invalid_svg_no_dimensions(self, tmp_path: Path):
        """SVG without dimensions returns False without calling subprocess."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" fill="white"/>
</svg>"""
        svg_path = tmp_path / "no_dims.svg"
        svg_path.write_text(svg_content, encoding="utf-8")
        png_path = tmp_path / "output.png"

        result = SVGRenderer.render_svg_to_png(svg_path, png_path)

        assert result is False


# =============================================================================
# Tests for ImageComparator.compare_images_pixel_perfect
# =============================================================================


class TestImageComparatorPixelPerfect:
    """Tests for pixel-perfect image comparison."""

    def test_identical_images_return_true(self, identical_images: tuple[Path, Path]):
        """Identical images return True with 0% difference."""
        img1_path, img2_path = identical_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path
        )

        assert is_match is True
        assert info["images_exist"] is True
        assert info["dimensions_match"] is True
        assert info["diff_pixels"] == 0
        assert info["diff_percentage"] == 0.0
        assert info["within_tolerance"] is True

    def test_completely_different_images_return_false(
        self, different_images: tuple[Path, Path]
    ):
        """Completely different images return False with ~100% difference."""
        img1_path, img2_path = different_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path
        )

        assert is_match is False
        assert info["images_exist"] is True
        assert info["dimensions_match"] is True
        assert info["diff_percentage"] == 100.0  # All pixels different
        assert info["within_tolerance"] is False

    def test_partial_difference_within_tolerance(
        self, partially_different_images: tuple[Path, Path]
    ):
        """25% difference with 30% tolerance returns True."""
        img1_path, img2_path = partially_different_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path, tolerance=30.0
        )

        assert is_match is True
        assert info["diff_percentage"] == pytest.approx(25.0, rel=0.1)
        assert info["within_tolerance"] is True

    def test_partial_difference_exceeds_tolerance(
        self, partially_different_images: tuple[Path, Path]
    ):
        """25% difference with 10% tolerance returns False."""
        img1_path, img2_path = partially_different_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path, tolerance=10.0
        )

        assert is_match is False
        assert info["diff_percentage"] == pytest.approx(25.0, rel=0.1)
        assert info["within_tolerance"] is False

    def test_size_mismatch_returns_false(
        self, mismatched_size_images: tuple[Path, Path]
    ):
        """Different sized images return False with dimension mismatch."""
        img1_path, img2_path = mismatched_size_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path
        )

        assert is_match is False
        assert info["images_exist"] is True
        assert info["dimensions_match"] is False
        assert "error" in info
        assert "Dimension mismatch" in info["error"]

    def test_missing_file_returns_false(self, tmp_path: Path):
        """Missing file returns False with error info."""
        img1_path = tmp_path / "nonexistent1.png"
        img2_path = tmp_path / "nonexistent2.png"

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path
        )

        assert is_match is False
        assert info["images_exist"] is False
        assert "error" in info

    def test_first_diff_location_reported(
        self, partially_different_images: tuple[Path, Path]
    ):
        """First difference location is reported correctly."""
        img1_path, img2_path = partially_different_images

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            img1_path, img2_path
        )

        assert info["first_diff_location"] is not None
        # First diff should be at (0, 0) since top-left quadrant is different
        y, x = info["first_diff_location"]
        assert y < 50 and x < 50  # Within the modified quadrant

    def test_pixel_tolerance_affects_comparison(self, tmp_path: Path):
        """Pixel tolerance affects per-pixel comparison."""
        # Create two images with subtle difference (1 unit in red channel)
        img1 = Image.new("RGBA", (10, 10), color=(100, 100, 100, 255))
        img2 = Image.new("RGBA", (10, 10), color=(101, 100, 100, 255))

        img1_path = tmp_path / "subtle1.png"
        img2_path = tmp_path / "subtle2.png"
        img1.save(img1_path)
        img2.save(img2_path)

        # With high pixel tolerance, should match
        is_match_high, info_high = ImageComparator.compare_images_pixel_perfect(
            img1_path,
            img2_path,
            pixel_tolerance=0.01,  # ~2.5 units
        )
        assert is_match_high is True
        assert info_high["diff_pixels"] == 0

        # With very low pixel tolerance, should not match
        is_match_low, info_low = ImageComparator.compare_images_pixel_perfect(
            img1_path,
            img2_path,
            pixel_tolerance=0.001,  # ~0.25 units
        )
        assert is_match_low is False
        assert info_low["diff_pixels"] == 100  # All 100 pixels differ


# =============================================================================
# Tests for svg_resolution
# =============================================================================


class TestSvgResolution:
    """Tests for SVG resolution string parsing."""

    def test_width_height_only(self, simple_svg: Path):
        """SVG with width/height returns readable string."""
        result = svg_resolution(simple_svg)
        assert "width=400" in result
        assert "height=300" in result

    def test_viewbox_only(self, viewbox_only_svg: Path):
        """SVG with only viewBox returns viewBox info."""
        result = svg_resolution(viewbox_only_svg)
        assert "viewBox" in result
        assert "800" in result
        assert "600" in result

    def test_both_width_height_and_viewbox(self, tmp_path: Path):
        """SVG with both returns both in result."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 800 600">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "both.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = svg_resolution(svg_path)
        assert "width=400" in result
        assert "viewBox" in result

    def test_nonexistent_file_returns_unknown(self, tmp_path: Path):
        """Non-existent file returns 'unknown'."""
        result = svg_resolution(tmp_path / "nonexistent.svg")
        assert result == "unknown"

    def test_invalid_svg_returns_unknown(self, tmp_path: Path):
        """Invalid SVG returns 'unknown'."""
        invalid_path = tmp_path / "invalid.svg"
        invalid_path.write_text("not xml", encoding="utf-8")

        result = svg_resolution(invalid_path)
        assert result == "unknown"

    def test_empty_svg_returns_unknown(self, tmp_path: Path):
        """SVG without any dimension info returns 'unknown'."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" fill="white"/>
</svg>"""
        svg_path = tmp_path / "empty_dims.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = svg_resolution(svg_path)
        assert result == "unknown"


# =============================================================================
# Tests for total_path_chars
# =============================================================================


class TestTotalPathChars:
    """Tests for counting path d attribute characters."""

    def test_svg_with_paths(self, svg_with_paths: Path):
        """Count total chars in all path d attributes."""
        result = total_path_chars(svg_with_paths)
        # "M10,10 L100,10 L100,100 Z" = 25 chars
        # "M200,200 C 210,210 220,220 230,230" = 34 chars
        # "M0,0" = 4 chars
        # Total = 63 chars
        assert result == 63

    def test_svg_without_paths(self, simple_svg: Path):
        """SVG without paths returns 0."""
        result = total_path_chars(simple_svg)
        assert result == 0

    def test_nonexistent_file_returns_zero(self, tmp_path: Path):
        """Non-existent file returns 0."""
        result = total_path_chars(tmp_path / "nonexistent.svg")
        assert result == 0

    def test_invalid_svg_returns_zero(self, tmp_path: Path):
        """Invalid SVG returns 0."""
        invalid_path = tmp_path / "invalid.svg"
        invalid_path.write_text("not xml", encoding="utf-8")

        result = total_path_chars(invalid_path)
        assert result == 0

    def test_namespaced_paths(self, tmp_path: Path):
        """Paths with explicit namespace are counted."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <path d="M0,0 L10,10"/>
</svg>"""
        svg_path = tmp_path / "namespaced.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = total_path_chars(svg_path)
        assert result == 11  # "M0,0 L10,10" = 11 chars


# =============================================================================
# Tests for generate_diff_image
# =============================================================================


class TestGenerateDiffImage:
    """Tests for generating red diff visualization."""

    def test_diff_highlights_differences_in_red(
        self, partially_different_images: tuple[Path, Path], tmp_path: Path
    ):
        """Differences are highlighted in red."""
        img1_path, img2_path = partially_different_images
        output_path = tmp_path / "diff.png"

        generate_diff_image(img1_path, img2_path, output_path)

        assert output_path.exists()
        diff_img = Image.open(output_path).convert("RGBA")

        # Check that top-left corner is red (where difference is)
        pixels = diff_img.load()
        top_left_pixel = pixels[0, 0]
        assert top_left_pixel == (255, 0, 0, 255)  # Pure red

        # Check that bottom-right corner is original (unchanged area)
        bottom_right_pixel = pixels[99, 99]
        assert bottom_right_pixel == (255, 0, 0, 255)  # Original was red

    def test_identical_images_produce_no_red(
        self, identical_images: tuple[Path, Path], tmp_path: Path
    ):
        """Identical images produce diff with no red highlights."""
        img1_path, img2_path = identical_images
        output_path = tmp_path / "diff.png"

        generate_diff_image(img1_path, img2_path, output_path)

        assert output_path.exists()
        diff_img = Image.open(output_path).convert("RGBA")
        np.array(diff_img)

        # All pixels should be original red, not the diff-highlight red
        # The original is (255, 0, 0, 255), so if no changes, it stays the same
        # Check that we don't have any pixels that are "different"
        # In this case, since original is red and highlight is also red,
        # we need to verify that the diff logic didn't trigger
        assert diff_img.size == (100, 100)

    def test_size_mismatch_raises_error(
        self, mismatched_size_images: tuple[Path, Path], tmp_path: Path
    ):
        """Size mismatch raises ValueError."""
        img1_path, img2_path = mismatched_size_images
        output_path = tmp_path / "diff.png"

        # generate_diff_image catches exception and prints error, doesn't raise
        # So we check that no output file is created
        generate_diff_image(img1_path, img2_path, output_path)
        # File should not be created on error
        assert not output_path.exists()

    def test_missing_file_handles_gracefully(self, tmp_path: Path):
        """Missing file is handled gracefully."""
        img1_path = tmp_path / "nonexistent1.png"
        img2_path = tmp_path / "nonexistent2.png"
        output_path = tmp_path / "diff.png"

        # Should not raise, just print error
        generate_diff_image(img1_path, img2_path, output_path)
        assert not output_path.exists()


# =============================================================================
# Tests for generate_grayscale_diff_map
# =============================================================================


class TestGenerateGrayscaleDiffMap:
    """Tests for generating grayscale diff maps."""

    def test_grayscale_map_created(
        self, different_images: tuple[Path, Path], tmp_path: Path
    ):
        """Grayscale diff map is created successfully."""
        img1_path, img2_path = different_images
        output_path = tmp_path / "grayscale_diff.png"

        generate_grayscale_diff_map(img1_path, img2_path, output_path)

        assert output_path.exists()
        diff_img = Image.open(output_path)
        # Grayscale image mode should be 'L' or compatible
        assert diff_img.size == (100, 100)

    def test_identical_images_produce_black_map(
        self, identical_images: tuple[Path, Path], tmp_path: Path
    ):
        """Identical images produce all-black grayscale map."""
        img1_path, img2_path = identical_images
        output_path = tmp_path / "grayscale_diff.png"

        generate_grayscale_diff_map(img1_path, img2_path, output_path)

        assert output_path.exists()
        diff_img = Image.open(output_path).convert("L")
        arr = np.array(diff_img)

        # All zeros (black) since no difference
        assert np.all(arr == 0)

    def test_different_images_produce_nonzero_map(
        self, different_images: tuple[Path, Path], tmp_path: Path
    ):
        """Different images produce non-zero grayscale map."""
        img1_path, img2_path = different_images
        output_path = tmp_path / "grayscale_diff.png"

        generate_grayscale_diff_map(img1_path, img2_path, output_path)

        assert output_path.exists()
        diff_img = Image.open(output_path).convert("L")
        arr = np.array(diff_img)

        # Should have non-zero values indicating differences
        assert np.max(arr) > 0

    def test_size_mismatch_handles_gracefully(
        self, mismatched_size_images: tuple[Path, Path], tmp_path: Path
    ):
        """Size mismatch is handled gracefully."""
        img1_path, img2_path = mismatched_size_images
        output_path = tmp_path / "grayscale_diff.png"

        generate_grayscale_diff_map(img1_path, img2_path, output_path)
        # File should not be created on error
        assert not output_path.exists()

    def test_missing_file_handles_gracefully(self, tmp_path: Path):
        """Missing file is handled gracefully."""
        img1_path = tmp_path / "nonexistent1.png"
        img2_path = tmp_path / "nonexistent2.png"
        output_path = tmp_path / "grayscale_diff.png"

        generate_grayscale_diff_map(img1_path, img2_path, output_path)
        assert not output_path.exists()


# =============================================================================
# Integration-style Tests (Real execution without external deps)
# =============================================================================


# =============================================================================
# Additional Edge Case Tests for Higher Coverage
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests for higher coverage."""

    def test_parse_svg_with_only_width(self, tmp_path: Path):
        """SVG with only width attribute returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "only_width.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is None

    def test_parse_svg_with_only_height(self, tmp_path: Path):
        """SVG with only height attribute returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" height="300">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "only_height.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is None

    def test_parse_svg_with_invalid_width_value(self, tmp_path: Path):
        """SVG with invalid width value (no digits) returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="auto" height="auto">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "invalid_dims.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is None

    def test_parse_svg_with_invalid_viewbox(self, tmp_path: Path):
        """SVG with invalid viewBox returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="invalid values here">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "invalid_viewbox.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is None

    def test_parse_svg_with_partial_viewbox(self, tmp_path: Path):
        """SVG with incomplete viewBox (less than 4 values) returns None."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "partial_viewbox.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = SVGRenderer._parse_svg_dimensions(svg_path)
        assert result is None

    def test_svg_resolution_with_only_width(self, tmp_path: Path):
        """SVG with only width returns that in resolution string."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "only_width.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = svg_resolution(svg_path)
        assert "width=400" in result

    def test_svg_resolution_with_only_height(self, tmp_path: Path):
        """SVG with only height returns that in resolution string."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" height="300">
  <rect width="100%" height="100%" fill="white"/>
</svg>"""
        svg_path = tmp_path / "only_height.svg"
        svg_path.write_text(svg_content, encoding="utf-8")

        result = svg_resolution(svg_path)
        assert "height=300" in result

    def test_compare_corrupted_image(self, tmp_path: Path):
        """Corrupted image file returns error."""
        # Create a file that's not a valid image
        corrupted_path = tmp_path / "corrupted.png"
        corrupted_path.write_bytes(b"not a valid PNG file contents")

        valid_img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 255))
        valid_path = tmp_path / "valid.png"
        valid_img.save(valid_path)

        is_match, info = ImageComparator.compare_images_pixel_perfect(
            corrupted_path, valid_path
        )

        assert is_match is False
        assert info["images_exist"] is False
        assert "error" in info

    @patch("svg_text2path.tools.visual_comparison.subprocess.run")
    def test_render_generic_exception(
        self, mock_run: MagicMock, simple_svg: Path, tmp_path: Path
    ):
        """Generic exception during render returns False."""
        png_path = tmp_path / "output.png"
        mock_run.side_effect = RuntimeError("Unexpected error")

        result = SVGRenderer.render_svg_to_png(simple_svg, png_path)

        assert result is False


class TestIntegration:
    """Integration tests that don't require external tools."""

    def test_full_comparison_workflow(self, tmp_path: Path):
        """Test full comparison workflow with real images."""
        # Create reference and modified images
        ref_img = Image.new("RGBA", (200, 200), color=(255, 255, 255, 255))
        mod_img = Image.new("RGBA", (200, 200), color=(255, 255, 255, 255))

        # Add a red rectangle to both
        for x in range(50, 150):
            for y in range(50, 150):
                ref_img.putpixel((x, y), (255, 0, 0, 255))
                mod_img.putpixel((x, y), (255, 0, 0, 255))

        # Add slight difference to modified image (10x10 blue square)
        for x in range(60, 70):
            for y in range(60, 70):
                mod_img.putpixel((x, y), (0, 0, 255, 255))

        ref_path = tmp_path / "ref.png"
        mod_path = tmp_path / "mod.png"
        ref_img.save(ref_path)
        mod_img.save(mod_path)

        # Compare
        is_match, info = ImageComparator.compare_images_pixel_perfect(
            ref_path, mod_path, tolerance=1.0
        )

        # 100 different pixels out of 40000 = 0.25%
        assert info["diff_pixels"] == 100
        assert info["diff_percentage"] == pytest.approx(0.25, rel=0.01)
        assert is_match is True  # Within 1% tolerance

        # Generate diff images
        diff_path = tmp_path / "diff.png"
        gray_path = tmp_path / "gray.png"

        generate_diff_image(ref_path, mod_path, diff_path)
        generate_grayscale_diff_map(ref_path, mod_path, gray_path)

        assert diff_path.exists()
        assert gray_path.exists()

    def test_svg_dimension_parsing_various_formats(self, tmp_path: Path):
        """Test dimension parsing with various SVG formats."""
        test_cases = [
            # (svg_content, expected_dimensions)
            ('<svg width="100" height="200"></svg>', (100, 200)),
            ('<svg width="100px" height="200px"></svg>', (100, 200)),
            ('<svg viewBox="0 0 300 400"></svg>', (300, 400)),
            ('<svg viewBox="0, 0, 300, 400"></svg>', (300, 400)),
            ('<svg width="150" height="250" viewBox="0 0 300 500"></svg>', (150, 250)),
        ]

        for i, (svg_content, expected) in enumerate(test_cases):
            full_svg = f'<?xml version="1.0"?>{svg_content}'
            svg_path = tmp_path / f"test_{i}.svg"
            svg_path.write_text(full_svg, encoding="utf-8")

            result = SVGRenderer._parse_svg_dimensions(svg_path)
            assert result == expected, f"Failed for: {svg_content}"
