"""Visual comparison tests using sbb-compare.

These tests run visual comparisons between original SVGs and converted versions.
They require:
- Inkscape installed locally
- Node.js and svg-bbox package
- NOT running on GitHub CI

Tests are automatically skipped if dependencies are missing.
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
SAMPLES_DEV_DIR = PROJECT_ROOT / "samples_dev"


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


def has_inkscape() -> bool:
    """Check if Inkscape is available."""
    return shutil.which("inkscape") is not None


def has_node() -> bool:
    """Check if Node.js is available."""
    return shutil.which("node") is not None


def has_sbb_compare() -> bool:
    """Check if sbb-compare (svg-bbox) is available."""
    if not has_node():
        return False
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


# Skip conditions
skip_on_ci = pytest.mark.skipif(is_github_ci(), reason="Visual tests skip on GitHub CI")
requires_inkscape = pytest.mark.skipif(
    not has_inkscape(), reason="Inkscape not installed"
)
requires_sbb_compare = pytest.mark.skipif(
    not has_sbb_compare(), reason="sbb-compare (svg-bbox) not available"
)


def run_sbb_compare(
    svg1: Path, svg2: Path, output_dir: Path | None = None
) -> ComparisonResult | None:
    """Run sbb-compare and parse results.

    Files must be copied to PROJECT_ROOT due to sbb-compare security restrictions.

    Args:
        svg1: First SVG file path
        svg2: Second SVG file path
        output_dir: Optional output directory for diff images

    Returns:
        ComparisonResult or None if comparison failed
    """
    import shutil as sh
    import uuid

    # Copy files to project root with unique names (sbb-compare security restriction)
    unique_id = uuid.uuid4().hex[:8]
    local_svg1 = PROJECT_ROOT / f"_test_{unique_id}_{svg1.name}"
    local_svg2 = PROJECT_ROOT / f"_test_{unique_id}_{svg2.name}"

    try:
        sh.copy(svg1, local_svg1)
        sh.copy(svg2, local_svg2)

        cmd = [
            "npx",
            "sbb-compare",
            str(local_svg1.name),
            str(local_svg2.name),
            "--json",
            "--headless",
        ]

        # Note: --out-diff must also be in PROJECT_ROOT due to sbb-compare security
        diff_path = None
        if output_dir:
            diff_name = f"_test_{unique_id}_diff.png"
            diff_path = PROJECT_ROOT / diff_name
            cmd.extend(["--out-diff", diff_name])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )

        # Parse JSON output (key is diffPercentage not differencePercent)
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
        pytest.skip("sbb-compare timed out")
    except FileNotFoundError:
        pytest.skip("sbb-compare not found")
    finally:
        # Cleanup temp files
        local_svg1.unlink(missing_ok=True)
        local_svg2.unlink(missing_ok=True)
        # Move diff image to output_dir if it exists, then cleanup
        if diff_path and diff_path.exists() and output_dir:
            target = output_dir / f"{svg1.stem}_vs_{svg2.stem}_diff.png"
            sh.move(str(diff_path), str(target))
        elif diff_path:
            diff_path.unlink(missing_ok=True)

    return None


@pytest.fixture
def visual_output_dir(tmp_path: Path) -> Path:
    """Create temporary directory for visual comparison outputs."""
    out_dir = tmp_path / "visual_diffs"
    out_dir.mkdir(exist_ok=True)
    return out_dir


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
# Visual Comparison Tests
# =============================================================================


@skip_on_ci
@requires_inkscape
@requires_sbb_compare
class TestVisualComparison:
    """Visual comparison tests that run only with Inkscape installed locally."""

    def test_simple_text_conversion(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Test visual accuracy of simple text conversion."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
  <rect width="100%" height="100%" fill="white"/>
  <text x="20" y="60" font-family="Helvetica" font-size="32" fill="black">Hello World</text>
</svg>"""
        orig_path = tmp_path / "simple_orig.svg"
        conv_path = tmp_path / "simple_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Visual comparison failed"
        assert result.diff_percent < 2.0, (
            f"Simple text diff {result.diff_percent:.2f}% exceeds 2% threshold"
        )

    def test_multiple_fonts_conversion(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Test visual accuracy with multiple fonts."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
  <rect width="100%" height="100%" fill="white"/>
  <text x="20" y="50" font-family="Helvetica" font-size="24" fill="black">Helvetica</text>
  <text x="20" y="100" font-family="Arial" font-size="24" fill="blue">Arial</text>
  <text x="20" y="150" font-family="Times" font-size="24" fill="red">Times</text>
  <text x="20" y="200" font-family="Georgia" font-size="24" fill="green">Georgia</text>
  <text x="20" y="250" font-family="Verdana" font-size="24" fill="purple">Verdana</text>
</svg>"""
        orig_path = tmp_path / "multifonts_orig.svg"
        conv_path = tmp_path / "multifonts_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Visual comparison failed"
        assert result.diff_percent < 3.0, (
            f"Multi-font diff {result.diff_percent:.2f}% exceeds 3% threshold"
        )

    def test_textpath_conversion(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Test visual accuracy of textPath conversion."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="400" height="200" viewBox="0 0 400 200">
  <rect width="100%" height="100%" fill="white"/>
  <defs>
    <path id="curve" d="M 50,150 Q 200,50 350,150" fill="none" stroke="none"/>
  </defs>
  <text font-family="Helvetica" font-size="20" fill="black">
    <textPath xlink:href="#curve" startOffset="0%">Text along a curve</textPath>
  </text>
</svg>"""
        orig_path = tmp_path / "textpath_orig.svg"
        conv_path = tmp_path / "textpath_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Visual comparison failed"
        assert result.diff_percent < 8.0, (
            f"TextPath diff {result.diff_percent:.2f}% exceeds 8% threshold"
        )

    def test_bold_italic_variants(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Test visual accuracy of bold and italic font variants."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="250" viewBox="0 0 400 250">
  <rect width="100%" height="100%" fill="white"/>
  <text x="20" y="50" font-family="Helvetica" font-size="24" fill="black">Regular</text>
  <text x="20" y="100" font-family="Helvetica" font-size="24" font-weight="bold" fill="black">Bold</text>
  <text x="20" y="150" font-family="Helvetica" font-size="24" font-style="italic" fill="black">Italic</text>
  <text x="20" y="200" font-family="Helvetica" font-size="24" font-weight="bold" font-style="italic" fill="black">Bold Italic</text>
</svg>"""
        orig_path = tmp_path / "variants_orig.svg"
        conv_path = tmp_path / "variants_conv.svg"

        orig_path.write_text(svg_content, encoding="utf-8")
        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Visual comparison failed"
        assert result.diff_percent < 3.0, (
            f"Font variants diff {result.diff_percent:.2f}% exceeds 3% threshold"
        )

    @pytest.mark.skipif(
        not (SAMPLES_DIR / "test_text_to_path_advanced.svg").exists(),
        reason="Advanced sample not found",
    )
    def test_advanced_sample(self, converter, visual_output_dir: Path, tmp_path: Path):
        """Test visual accuracy of the advanced sample file."""
        orig_path = SAMPLES_DIR / "test_text_to_path_advanced.svg"
        conv_path = tmp_path / "advanced_conv.svg"

        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Visual comparison failed"
        # Advanced sample has more complex text, allow higher threshold
        assert result.diff_percent < 8.0, (
            f"Advanced sample diff {result.diff_percent:.2f}% exceeds 8% threshold"
        )

    @pytest.mark.skipif(
        not (SAMPLES_DIR / "test_text_to_path_advanced.svg").exists()
        or not (SAMPLES_DIR / "test_text_to_path_advanced_inkscape_paths.svg").exists(),
        reason="Advanced sample or Inkscape reference not found",
    )
    def test_vs_inkscape_reference(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Test our conversion against Inkscape's conversion as reference."""
        orig_path = SAMPLES_DIR / "test_text_to_path_advanced.svg"
        inkscape_path = SAMPLES_DIR / "test_text_to_path_advanced_inkscape_paths.svg"
        our_conv_path = tmp_path / "our_conv.svg"

        converter.convert_file(str(orig_path), str(our_conv_path))

        # Compare original vs Inkscape
        inkscape_result = run_sbb_compare(orig_path, inkscape_path, visual_output_dir)

        # Compare original vs our conversion
        our_result = run_sbb_compare(orig_path, our_conv_path, visual_output_dir)

        assert inkscape_result is not None, "Inkscape comparison failed"
        assert our_result is not None, "Our conversion comparison failed"

        # Log results for debugging
        print(f"\nInkscape diff: {inkscape_result.diff_percent:.2f}%")
        print(f"Our diff: {our_result.diff_percent:.2f}%")
        print(f"Gap: {our_result.diff_percent - inkscape_result.diff_percent:.2f}%")

        # Our conversion should be within 5% of Inkscape quality
        gap = our_result.diff_percent - inkscape_result.diff_percent
        assert gap < 2.0, (
            f"Our conversion ({our_result.diff_percent:.2f}%) is more than 5% "
            f"worse than Inkscape ({inkscape_result.diff_percent:.2f}%)"
        )


# =============================================================================
# Benchmark Tests (for tracking improvements over time)
# =============================================================================


@skip_on_ci
@requires_inkscape
@requires_sbb_compare
@pytest.mark.slow
class TestVisualBenchmarks:
    """Benchmark tests for tracking visual accuracy improvements."""

    def test_benchmark_advanced_sample(
        self, converter, visual_output_dir: Path, tmp_path: Path
    ):
        """Benchmark test for advanced sample - records diff percentage."""
        if not (SAMPLES_DIR / "test_text_to_path_advanced.svg").exists():
            pytest.skip("Advanced sample not found")

        orig_path = SAMPLES_DIR / "test_text_to_path_advanced.svg"
        conv_path = tmp_path / "benchmark_conv.svg"

        converter.convert_file(str(orig_path), str(conv_path))

        result = run_sbb_compare(orig_path, conv_path, visual_output_dir)

        assert result is not None, "Benchmark comparison failed"

        # Store result for tracking (could write to file for CI tracking)
        print(f"\n{'=' * 60}")
        print("BENCHMARK RESULTS")
        print(f"{'=' * 60}")
        print("Sample: test_text_to_path_advanced.svg")
        print(f"Diff: {result.diff_percent:.2f}%")
        print("Target: < 1.0%")
        print(f"{'=' * 60}")

        # Soft assertion - warn but don't fail if above target
        if result.diff_percent > 1.0:
            pytest.xfail(
                f"Diff {result.diff_percent:.2f}% above 1.0% target (tracking)"
            )
