"""Tests for the compare CLI command.

Coverage: 12 tests covering compare command options, error handling, and exit codes.
Tests use Click's CliRunner for isolated command invocation.

Coverage targets:
- compare() main function entry point
- --pixel-perfect flag handling with ImageComparator
- --generate-diff and --grayscale-diff image output
- --threshold validation and exit code logic
- Error handling for missing files and dependencies
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from svg_text2path.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner instance for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def reference_svg(tmp_path: Path) -> Path:
    """Create a reference SVG file for comparison testing."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
</svg>"""
    svg_path = tmp_path / "reference.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def converted_svg(tmp_path: Path) -> Path:
    """Create a converted SVG file (paths instead of text) for comparison."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <path d="M10 50 L50 50 L50 30 L10 30 Z" fill="black"/>
</svg>"""
    svg_path = tmp_path / "converted.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def inkscape_svg(tmp_path: Path) -> Path:
    """Create an Inkscape reference SVG for 3-way comparison."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <path d="M10 50 L50 50 L50 30 L10 30 Z" fill="black"/>
</svg>"""
    svg_path = tmp_path / "inkscape_ref.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


class TestCompareCommandHelp:
    """Tests for compare command help and basic invocation."""

    def test_compare_help_shows_options(self, runner: CliRunner) -> None:
        """Compare command --help shows all available options."""
        result = runner.invoke(cli, ["compare", "--help"])
        assert result.exit_code == 0

        # Check main arguments are documented
        assert "REFERENCE" in result.output
        assert "CONVERTED" in result.output

        # Check key options are listed
        assert "--threshold" in result.output
        assert "--pixel-perfect" in result.output
        assert "--generate-diff" in result.output
        assert "--grayscale-diff" in result.output
        assert "--output-dir" in result.output
        assert "--inkscape-svg" in result.output
        assert "--no-html" in result.output


class TestCompareCommandArguments:
    """Tests for compare command argument handling."""

    def test_compare_missing_reference_file_shows_error(
        self, runner: CliRunner
    ) -> None:
        """Compare command without arguments shows missing argument error."""
        result = runner.invoke(cli, ["compare"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_compare_missing_converted_file_shows_error(
        self, runner: CliRunner, reference_svg: Path
    ) -> None:
        """Compare command with only reference file shows missing argument."""
        result = runner.invoke(cli, ["compare", str(reference_svg)])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_compare_nonexistent_reference_shows_error(
        self, runner: CliRunner, converted_svg: Path, tmp_path: Path
    ) -> None:
        """Compare command with non-existent reference file shows error."""
        fake_ref = tmp_path / "nonexistent.svg"
        result = runner.invoke(cli, ["compare", str(fake_ref), str(converted_svg)])
        assert result.exit_code != 0
        # Click shows path validation error
        assert "does not exist" in result.output or "Invalid value" in result.output

    def test_compare_nonexistent_converted_shows_error(
        self, runner: CliRunner, reference_svg: Path, tmp_path: Path
    ) -> None:
        """Compare command with non-existent converted file shows error."""
        fake_conv = tmp_path / "nonexistent.svg"
        result = runner.invoke(cli, ["compare", str(reference_svg), str(fake_conv)])
        assert result.exit_code != 0
        assert "does not exist" in result.output or "Invalid value" in result.output


class TestComparePixelPerfectMode:
    """Tests for --pixel-perfect comparison mode."""

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_pixel_perfect_uses_image_comparator(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """--pixel-perfect flag uses ImageComparator instead of svg-bbox."""
        # Mock dependencies as available
        mock_deps.return_value = (True, [])

        # Mock render_svg_to_png to create dummy PNG files
        def create_dummy_png(_svg_path: Path, png_path: Path) -> bool:
            # Create a small valid PNG
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png

        # Mock comparison result
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 0, "diff_percentage": 0.0},
        )

        result = runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--output-dir",
                str(tmp_path / "diffs"),
            ],
        )

        # Should call ImageComparator
        assert mock_comparator.compare_images_pixel_perfect.called
        # Should show pixel-perfect mode in output
        assert "Pixel-perfect" in result.output or result.exit_code == 0

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_pixel_tolerance_option(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """--pixel-tolerance option sets color difference tolerance."""
        mock_deps.return_value = (True, [])

        def create_dummy_png(_svg_path: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 100, "diff_percentage": 0.5},
        )

        _result = runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--pixel-tolerance",
                "0.05",
                "--output-dir",
                str(tmp_path / "diffs"),
            ],
        )

        # Verify tolerance was passed to comparator
        call_args = mock_comparator.compare_images_pixel_perfect.call_args
        assert call_args is not None
        assert call_args.kwargs.get("pixel_tolerance") == 0.05


class TestCompareThreshold:
    """Tests for --threshold option and exit code behavior."""

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_diff_below_threshold_exits_zero(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """Diff percentage below threshold results in exit code 0 (PASS)."""
        mock_deps.return_value = (True, [])

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        # Return 0.3% diff, below 0.5% threshold
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 60, "diff_percentage": 0.3},
        )

        result = runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--threshold",
                "0.5",
                "--output-dir",
                str(tmp_path / "diffs"),
            ],
        )

        assert result.exit_code == 0
        assert "PASS" in result.output

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_diff_above_threshold_exits_one(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """Diff percentage above threshold results in exit code 1 (FAIL)."""
        mock_deps.return_value = (True, [])

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        # Return 1.5% diff, above 0.5% threshold
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 300, "diff_percentage": 1.5},
        )

        result = runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--threshold",
                "0.5",
                "--output-dir",
                str(tmp_path / "diffs"),
            ],
        )

        assert result.exit_code == 1
        assert "FAIL" in result.output


class TestCompareDiffImageGeneration:
    """Tests for --generate-diff and --grayscale-diff options."""

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    @patch("svg_text2path.cli.commands.compare.generate_diff_image")
    def test_generate_diff_creates_diff_image(
        self,
        mock_gen_diff: MagicMock,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """--generate-diff option creates red-overlay diff image."""
        mock_deps.return_value = (True, [])
        output_dir = tmp_path / "diffs"

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 0, "diff_percentage": 0.0},
        )

        runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--generate-diff",
                "--output-dir",
                str(output_dir),
            ],
        )

        # generate_diff_image should be called
        assert mock_gen_diff.called

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    @patch("svg_text2path.cli.commands.compare.generate_grayscale_diff_map")
    def test_grayscale_diff_creates_grayscale_map(
        self,
        mock_grayscale: MagicMock,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """--grayscale-diff option creates grayscale magnitude diff map."""
        mock_deps.return_value = (True, [])
        output_dir = tmp_path / "diffs"

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 0, "diff_percentage": 0.0},
        )

        runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--grayscale-diff",
                "--output-dir",
                str(output_dir),
            ],
        )

        # generate_grayscale_diff_map should be called
        assert mock_grayscale.called


class TestCompareDependencyChecks:
    """Tests for dependency checking behavior."""

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    def test_missing_node_shows_error(
        self,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
    ) -> None:
        """Missing node dependency shows helpful error message."""
        mock_deps.return_value = (False, ["node"])

        result = runner.invoke(cli, ["compare", str(reference_svg), str(converted_svg)])

        assert result.exit_code == 1
        assert "node" in result.output.lower()

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    def test_missing_npx_shows_error(
        self,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
    ) -> None:
        """Missing npx dependency shows helpful error message."""
        mock_deps.return_value = (False, ["npx"])

        result = runner.invoke(cli, ["compare", str(reference_svg), str(converted_svg)])

        assert result.exit_code == 1
        assert "npx" in result.output.lower() or "npm" in result.output.lower()


class TestCompareOutputOptions:
    """Tests for output-related options."""

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_output_dir_creates_directory(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """--output-dir option creates output directory if needed."""
        mock_deps.return_value = (True, [])
        output_dir = tmp_path / "new_diffs"

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 0, "diff_percentage": 0.0},
        )

        runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--output-dir",
                str(output_dir),
            ],
        )

        # Output directory should be created
        assert output_dir.exists()

    @patch("svg_text2path.cli.commands.compare.check_visual_comparison_deps")
    @patch("svg_text2path.cli.commands.compare.SVGRenderer")
    @patch("svg_text2path.cli.commands.compare.ImageComparator")
    def test_comparison_reports_file_paths(
        self,
        mock_comparator: MagicMock,
        mock_renderer: MagicMock,
        mock_deps: MagicMock,
        runner: CliRunner,
        reference_svg: Path,
        converted_svg: Path,
        tmp_path: Path,
    ) -> None:
        """Comparison output includes reference and converted file paths."""
        mock_deps.return_value = (True, [])

        def create_dummy_png(_: Path, png_path: Path) -> bool:
            from PIL import Image

            img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
            img.save(png_path, "PNG")
            return True

        mock_renderer.render_svg_to_png.side_effect = create_dummy_png
        mock_comparator.compare_images_pixel_perfect.return_value = (
            True,
            {"total_pixels": 20000, "diff_pixels": 0, "diff_percentage": 0.0},
        )

        result = runner.invoke(
            cli,
            [
                "compare",
                str(reference_svg),
                str(converted_svg),
                "--pixel-perfect",
                "--output-dir",
                str(tmp_path / "diffs"),
            ],
        )

        # Output should mention the file names
        assert "reference" in result.output.lower()
        assert "converted" in result.output.lower()
