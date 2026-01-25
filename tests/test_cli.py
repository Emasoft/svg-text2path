"""Tests for svg_text2path CLI commands using Click's testing utilities.

Coverage: 5 tests covering CLI help, convert command, batch command, fonts command.
Tests use CliRunner for isolated command invocation without side effects.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from svg_text2path.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner instance for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_svg_file(tmp_path: Path) -> Path:
    """Create a temporary SVG file with text for CLI testing."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
</svg>"""
    svg_path = tmp_path / "input.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


class TestCLIMain:
    """Tests for the main CLI group command."""

    def test_cli_shows_help_text(self, runner: CliRunner) -> None:
        """CLI --help shows usage information and available commands."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}: {result.output}"
        )
        # Check help contains expected command group description
        assert "Convert SVG text elements" in result.output
        # Check subcommands are listed
        assert "convert" in result.output
        assert "batch" in result.output
        assert "fonts" in result.output

    def test_cli_version_option(self, runner: CliRunner) -> None:
        """CLI --version displays the package version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "text2path" in result.output.lower()


class TestConvertCommand:
    """Tests for the convert subcommand."""

    def test_convert_accepts_input_file_argument(
        self, runner: CliRunner, temp_svg_file: Path
    ) -> None:
        """Convert command accepts an input file path as argument."""
        result = runner.invoke(cli, ["convert", str(temp_svg_file)])
        # Command should run without argument errors (may fail on font
        # resolution but that's OK). We're testing CLI argument parsing.
        assert result.exit_code in (0, 1), (
            f"Unexpected exit code {result.exit_code}: {result.output}"
        )
        # Should not show "Missing argument" error
        assert "Missing argument" not in result.output

    def test_convert_with_output_option(
        self, runner: CliRunner, temp_svg_file: Path, tmp_path: Path
    ) -> None:
        """Convert command --output option specifies output file path."""
        output_file = tmp_path / "output.svg"
        result = runner.invoke(
            cli, ["convert", str(temp_svg_file), "--output", str(output_file)]
        )
        # Check that the --output option is parsed correctly (no argument errors)
        assert "Error: Invalid value for '--output'" not in result.output
        assert "Missing argument" not in result.output
        # Exit code 0 or 1 (may fail on font issues, but CLI parsing should work)
        assert result.exit_code in (0, 1), f"Unexpected exit code: {result.output}"

    def test_convert_missing_input_file_shows_error(self, runner: CliRunner) -> None:
        """Convert command without input file shows missing argument error."""
        result = runner.invoke(cli, ["convert"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output


class TestBatchCommand:
    """Tests for the batch subcommand (now a command group with subcommands)."""

    def test_batch_help_shows_subcommands(self, runner: CliRunner) -> None:
        """Batch command --help shows available batch subcommands."""
        result = runner.invoke(cli, ["batch", "--help"])
        assert result.exit_code == 0
        # Check batch subcommands are listed
        assert "convert" in result.output
        assert "compare" in result.output
        assert "regression" in result.output

    def test_batch_convert_with_output_dir_option(
        self, runner: CliRunner, temp_svg_file: Path, tmp_path: Path
    ) -> None:
        """Batch convert --output-dir option specifies output directory."""
        output_dir = tmp_path / "batch_output"
        result = runner.invoke(
            cli,
            ["batch", "convert", str(temp_svg_file), "--output-dir", str(output_dir)],
        )
        # Check that --output-dir is parsed (no argument errors)
        assert "Error: Invalid value for '--output-dir'" not in result.output
        # Exit code may be 0 or 1 depending on font availability
        assert result.exit_code in (0, 1), f"Unexpected exit: {result.output}"

    def test_batch_convert_requires_output_dir(
        self, runner: CliRunner, temp_svg_file: Path
    ) -> None:
        """Batch convert fails without required --output-dir option."""
        result = runner.invoke(cli, ["batch", "convert", str(temp_svg_file)])
        assert result.exit_code != 0
        # Should indicate missing required option
        assert "Missing option" in result.output or "--output-dir" in result.output


class TestFontsCommand:
    """Tests for the fonts subcommand."""

    def test_fonts_help_shows_subcommands(self, runner: CliRunner) -> None:
        """Fonts command --help shows available font management subcommands."""
        result = runner.invoke(cli, ["fonts", "--help"])
        assert result.exit_code == 0
        # Check font subcommands are listed
        assert "list" in result.output
        assert "cache" in result.output
        assert "find" in result.output

    def test_fonts_list_command_executes(self, runner: CliRunner) -> None:
        """Fonts list command runs and produces output."""
        result = runner.invoke(cli, ["fonts", "list"])
        # Command should execute (may take time to load fonts)
        # Exit 0 on success or 1 if font system issues
        assert result.exit_code in (0, 1), f"Unexpected exit: {result.output}"
        # Should show some output (table or error)
        assert len(result.output) > 0
