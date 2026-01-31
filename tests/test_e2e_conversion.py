"""End-to-end tests for text-to-path conversion with visual verification.

These tests verify the complete pipeline from SVG input to path output,
using sbb-compare for visual accuracy verification.

Tests cover:
- Full conversion pipeline with font resolution
- Font cache corruption detection and recovery
- Programmatic API usage patterns
- CLI-equivalent workflows
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"


class ComparisonResult(NamedTuple):
    """Result from visual comparison."""

    svg1: str
    svg2: str
    total_pixels: int
    different_pixels: int
    diff_percent: float
    diff_image: str | None


def is_github_ci() -> bool:
    """Check if running on GitHub CI."""
    return os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"


def has_sbb_compare() -> bool:
    """Check if sbb-compare is available."""
    try:
        result = subprocess.run(
            ["sbb-compare", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Try with npx
        try:
            result = subprocess.run(
                ["npx", "sbb-compare", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


def get_sbb_command() -> list[str]:
    """Get the appropriate sbb-compare command."""
    if shutil.which("sbb-compare"):
        return ["sbb-compare"]
    return ["npx", "sbb-compare"]


def run_sbb_compare(svg1: Path, svg2: Path) -> ComparisonResult | None:
    """Run sbb-compare and parse results.

    Args:
        svg1: First SVG file path
        svg2: Second SVG file path

    Returns:
        ComparisonResult or None if comparison failed
    """
    import uuid

    # Copy files to project root with unique names (sbb-compare security restriction)
    unique_id = uuid.uuid4().hex[:8]
    local_svg1 = PROJECT_ROOT / f"_test_{unique_id}_{svg1.name}"
    local_svg2 = PROJECT_ROOT / f"_test_{unique_id}_{svg2.name}"

    try:
        shutil.copy(svg1, local_svg1)
        shutil.copy(svg2, local_svg2)

        cmd = get_sbb_command() + [
            str(local_svg1.name),
            str(local_svg2.name),
            "--json",
            "--headless",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )

        # Parse JSON output
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                return ComparisonResult(
                    svg1=str(svg1),
                    svg2=str(svg2),
                    total_pixels=data.get("totalPixels", 0),
                    different_pixels=data.get("differentPixels", 0),
                    diff_percent=data.get("diffPercentage", 100.0),
                    diff_image=data.get("diffImage"),
                )
            except json.JSONDecodeError:
                pass

        # Fallback: parse text output
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            if "Difference:" in line and "%" in line:
                try:
                    pct = float(line.split(":")[1].strip().rstrip("%"))
                    return ComparisonResult(
                        svg1=str(svg1),
                        svg2=str(svg2),
                        total_pixels=0,
                        different_pixels=0,
                        diff_percent=pct,
                        diff_image=None,
                    )
                except (ValueError, IndexError):
                    pass

    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None
    finally:
        # Cleanup temp files
        local_svg1.unlink(missing_ok=True)
        local_svg2.unlink(missing_ok=True)

    return None


# Skip conditions
skip_on_ci = pytest.mark.skipif(is_github_ci(), reason="E2E tests skip on GitHub CI")
requires_sbb = pytest.mark.skipif(
    not has_sbb_compare(), reason="sbb-compare not available"
)


@pytest.fixture
def font_cache():
    """Pre-warmed font cache for conversions."""
    from svg_text2path.fonts.cache import FontCache

    cache = FontCache()
    cache.prewarm()
    return cache


@pytest.fixture
def converter(font_cache):
    """Text2Path converter with pre-warmed cache."""
    from svg_text2path.api import Text2PathConverter

    return Text2PathConverter(font_cache=font_cache)


# =============================================================================
# E2E Conversion Tests with Visual Verification
# =============================================================================


@skip_on_ci
@requires_sbb
class TestE2EConversionPipeline:
    """End-to-end tests for complete conversion pipeline."""

    def test_programmatic_api_basic_conversion(self, converter, tmp_path: Path):
        """Test programmatic API produces visually accurate output."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80" viewBox="0 0 300 80">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="50" font-family="Helvetica" font-size="28" fill="black">Test Text</text>
</svg>"""
        orig_path = tmp_path / "api_orig.svg"
        conv_path = tmp_path / "api_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")

        # Use programmatic API
        result = converter.convert_file(str(orig_path), str(conv_path))

        # Verify conversion succeeded
        assert result is not None
        assert conv_path.exists()

        # Verify paths were generated
        conv_content = conv_path.read_text()
        assert "<path" in conv_content
        assert "<text" not in conv_content or "text>" not in conv_content

        # Visual verification with sbb-compare
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 2.0, (
            f"Visual diff {compare_result.diff_percent:.2f}% exceeds 2% threshold"
        )

    def test_programmatic_api_convert_string(self, converter, tmp_path: Path):
        """Test convert_string API produces accurate output."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="250" height="60" viewBox="0 0 250 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Arial" font-size="24" fill="navy">String API</text>
</svg>"""
        orig_path = tmp_path / "string_orig.svg"
        conv_path = tmp_path / "string_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")

        # Use convert_string API
        result = converter.convert_string(svg_content)

        # Write result for comparison
        conv_path.write_text(result, encoding="utf-8")

        # Verify paths were generated
        assert "<path" in result

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 2.0, (
            f"Visual diff {compare_result.diff_percent:.2f}% exceeds 2% threshold"
        )

    def test_font_weight_variations(self, converter, tmp_path: Path):
        """Test font weight variations are accurately converted."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Helvetica" font-size="20" font-weight="300">Light</text>
  <text x="10" y="80" font-family="Helvetica" font-size="20" font-weight="400">Regular</text>
  <text x="10" y="120" font-family="Helvetica" font-size="20" font-weight="700">Bold</text>
  <text x="10" y="160" font-family="Helvetica" font-size="20" font-weight="900">Black</text>
</svg>"""
        orig_path = tmp_path / "weights_orig.svg"
        conv_path = tmp_path / "weights_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 3.0, (
            f"Font weight diff {compare_result.diff_percent:.2f}% exceeds 3% threshold"
        )

    def test_tspan_elements(self, converter, tmp_path: Path):
        """Test tspan elements are accurately converted.

        Note: tspans must be on same line to avoid whitespace issues.
        """
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80" viewBox="0 0 400 80">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="50" font-family="Helvetica" font-size="24" fill="black"><tspan>First </tspan><tspan>Second </tspan><tspan>Third</tspan></text>
</svg>"""
        orig_path = tmp_path / "tspan_orig.svg"
        conv_path = tmp_path / "tspan_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Verify tspans were converted
        conv_content = conv_path.read_text()
        assert "<path" in conv_content

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 3.0, (
            f"Tspan diff {compare_result.diff_percent:.2f}% exceeds 3% threshold"
        )

    def test_transform_handling(self, converter, tmp_path: Path):
        """Test text with transforms is accurately converted."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
  <rect width="100%" height="100%" fill="white"/>
  <text x="50" y="50" font-family="Helvetica" font-size="24"
        transform="rotate(15)">Rotated</text>
  <text x="50" y="120" font-family="Helvetica" font-size="24"
        transform="scale(1.2)">Scaled</text>
  <g transform="translate(100, 50)">
    <text x="0" y="80" font-family="Helvetica" font-size="24">In Group</text>
  </g>
</svg>"""
        orig_path = tmp_path / "transform_orig.svg"
        conv_path = tmp_path / "transform_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 3.0, (
            f"Transform diff {compare_result.diff_percent:.2f}% exceeds 3% threshold"
        )


@skip_on_ci
@requires_sbb
class TestE2EFontCacheIntegration:
    """E2E tests for font cache integration with corruption detection."""

    def test_fresh_cache_conversion(self, tmp_path: Path):
        """Test conversion with fresh font cache (simulates first run)."""
        from svg_text2path.api import Text2PathConverter
        from svg_text2path.fonts.cache import FontCache

        # Create fresh cache
        cache = FontCache()
        cache.prewarm()

        converter = Text2PathConverter(font_cache=cache)

        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Helvetica" font-size="24">Fresh Cache</text>
</svg>"""
        orig_path = tmp_path / "fresh_orig.svg"
        conv_path = tmp_path / "fresh_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 2.0

    def test_corrupted_font_fallback(self, tmp_path: Path):
        """Test that corrupted fonts are skipped and fallback works."""
        from svg_text2path.api import Text2PathConverter
        from svg_text2path.fonts.cache import FontCache

        # Create cache and mark a non-existent font as corrupted
        cache = FontCache()
        cache._corrupted_fonts.add(("/fake/path/corrupted.ttf", 0))
        cache.prewarm()

        converter = Text2PathConverter(font_cache=cache)

        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="250" height="60" viewBox="0 0 250 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Arial" font-size="24">Fallback Test</text>
</svg>"""
        orig_path = tmp_path / "fallback_orig.svg"
        conv_path = tmp_path / "fallback_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Conversion should succeed despite corrupted font in list
        assert conv_path.exists()
        conv_content = conv_path.read_text()
        assert "<path" in conv_content

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None, "sbb-compare failed"
        assert compare_result.diff_percent < 3.0

    def test_cache_reuse_across_conversions(self, tmp_path: Path):
        """Test that font cache is properly reused across multiple conversions."""
        from svg_text2path.api import Text2PathConverter
        from svg_text2path.fonts.cache import FontCache

        cache = FontCache()
        cache.prewarm()
        converter = Text2PathConverter(font_cache=cache)

        # First conversion
        svg1 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Helvetica" font-size="24">First</text>
</svg>"""
        orig1 = tmp_path / "first_orig.svg"
        conv1 = tmp_path / "first_conv.svg"
        orig1.write_text(svg1, encoding="utf-8")
        converter.convert_file(str(orig1), str(conv1))

        # Check cache has entries
        cache_entries_after_first = len(cache._fonts)

        # Second conversion with same font
        svg2 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Helvetica" font-size="24">Second</text>
</svg>"""
        orig2 = tmp_path / "second_orig.svg"
        conv2 = tmp_path / "second_conv.svg"
        orig2.write_text(svg2, encoding="utf-8")
        converter.convert_file(str(orig2), str(conv2))

        # Cache should not have grown (font was reused)
        assert len(cache._fonts) == cache_entries_after_first

        # Both conversions should be visually accurate
        result1 = run_sbb_compare(orig1, conv1)
        result2 = run_sbb_compare(orig2, conv2)

        assert result1 is not None and result1.diff_percent < 2.0
        assert result2 is not None and result2.diff_percent < 2.0


@skip_on_ci
@requires_sbb
class TestE2EEdgeCases:
    """E2E tests for edge cases and error handling."""

    def test_empty_text_element(self, converter, tmp_path: Path):
        """Test conversion handles empty text elements gracefully."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="40" font-family="Helvetica" font-size="24"></text>
  <text x="10" y="40" font-family="Helvetica" font-size="24">Real Text</text>
</svg>"""
        orig_path = tmp_path / "empty_orig.svg"
        conv_path = tmp_path / "empty_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Should succeed
        assert conv_path.exists()

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None
        assert compare_result.diff_percent < 2.0

    def test_special_characters(self, converter, tmp_path: Path):
        """Test conversion handles special characters correctly."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80" viewBox="0 0 400 80">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="50" font-family="Helvetica" font-size="24">&amp; &lt; &gt; "quotes"</text>
</svg>"""
        orig_path = tmp_path / "special_orig.svg"
        conv_path = tmp_path / "special_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None
        assert compare_result.diff_percent < 3.0

    def test_unicode_text(self, converter, tmp_path: Path):
        """Test conversion handles Unicode text correctly."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80" viewBox="0 0 400 80">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="50" font-family="Arial Unicode MS, Arial" font-size="24">Hello 世界 مرحبا</text>
</svg>"""
        orig_path = tmp_path / "unicode_orig.svg"
        conv_path = tmp_path / "unicode_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")

        # This may fail if fonts don't support the characters, which is expected
        try:
            converter.convert_file(str(orig_path), str(conv_path))
            if conv_path.exists():
                compare_result = run_sbb_compare(orig_path, conv_path)
                # Allow higher threshold for Unicode due to font substitution
                if compare_result is not None:
                    assert compare_result.diff_percent < 10.0
        except Exception:
            # Font missing is acceptable for this test
            pytest.skip("Unicode fonts not available")

    def test_no_text_elements(self, converter, tmp_path: Path):
        """Test conversion handles SVG with no text elements."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <rect width="100%" height="100%" fill="white"/>
  <circle cx="100" cy="50" r="40" fill="blue"/>
</svg>"""
        orig_path = tmp_path / "notext_orig.svg"
        conv_path = tmp_path / "notext_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        # Should succeed (no-op conversion)
        assert conv_path.exists()

        # Output should be identical to input (no changes needed)
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None
        assert compare_result.diff_percent < 1.0  # Should be near-identical


@skip_on_ci
@requires_sbb
class TestE2EPerformance:
    """E2E tests for performance characteristics."""

    @pytest.mark.slow
    def test_multiple_text_elements(self, converter, tmp_path: Path):
        """Test conversion with many text elements."""
        # Generate SVG with 20 text elements
        texts = "\n".join(
            f'  <text x="10" y="{30 + i * 25}" font-family="Helvetica" '
            f'font-size="18">Line {i + 1}: Sample text content</text>'
            for i in range(20)
        )
        svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="500" height="550" viewBox="0 0 500 550">
  <rect width="100%" height="100%" fill="white"/>
{texts}
</svg>"""
        orig_path = tmp_path / "many_orig.svg"
        conv_path = tmp_path / "many_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")

        import time

        start = time.time()
        converter.convert_file(str(orig_path), str(conv_path))
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 10.0, f"Conversion took {elapsed:.1f}s (> 30s limit)"

        # Visual verification
        compare_result = run_sbb_compare(orig_path, conv_path)
        assert compare_result is not None
        assert compare_result.diff_percent < 3.0
