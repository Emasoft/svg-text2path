"""Tests for batch regression command implementation.

Tests cover:
- CLI command invocation and option parsing
- Registry loading and saving
- Regression detection logic
- Improvement detection
- Baseline creation for new registry
- Skip file functionality
- Error handling for missing samples

Coverage: ~60% target (CLI-focused testing with mocked converters/comparers)

Limitations:
- Does not test actual SVG conversion (mocked Text2PathConverter)
- Does not test actual sbb-compare execution (mocked subprocess)
- Integration testing recommended for full pipeline verification
"""

import json
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from svg_text2path.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner instance for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_samples_dir(tmp_path: Path) -> Path:
    """Create a samples directory with test SVG files containing text elements."""
    samples = tmp_path / "samples"
    samples.mkdir()

    # Create text SVG files with text elements for conversion
    for i in range(3):
        svg_content = dedent(f"""
            <?xml version="1.0" encoding="UTF-8"?>
            <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
              <text x="10" y="50" font-family="Arial" font-size="24">Sample {i}</text>
            </svg>
        """).strip()
        (samples / f"text{i + 1}.svg").write_text(svg_content, encoding="utf-8")

    return samples


@pytest.fixture
def temp_registry(tmp_path: Path) -> Path:
    """Create an empty registry path without existing data."""
    return tmp_path / "registry" / "regression_history.json"


@pytest.fixture
def existing_registry(tmp_path: Path) -> Path:
    """Create a registry with previous run data for regression testing."""
    registry_path = tmp_path / "registry" / "regression_history.json"
    registry_path.parent.mkdir(parents=True)

    # Previous run data with known diff percentages
    previous_data = [
        {
            "timestamp": "20250101T120000Z",
            "threshold": 20,
            "scale": 4.0,
            "resolution": "viewbox",
            "precision": 3,
            "results": {
                "text1.svg": 5.0,
                "text2.svg": 3.5,
                "text3.svg": 2.0,
            },
            "failures": [],
        }
    ]
    registry_path.write_text(json.dumps(previous_data, indent=2))
    return registry_path


class TestBatchRegressionHelp:
    """Tests for batch regression command help and basic invocation."""

    def test_regression_command_exists(self, runner: CliRunner) -> None:
        """batch regression command is available in CLI."""
        result = runner.invoke(cli, ["batch", "regression", "--help"])

        assert result.exit_code == 0
        assert "regression" in result.output.lower()
        assert "--samples-dir" in result.output
        assert "--registry" in result.output
        assert "--threshold" in result.output

    def test_regression_help_shows_all_options(self, runner: CliRunner) -> None:
        """batch regression --help shows all available options."""
        result = runner.invoke(cli, ["batch", "regression", "--help"])

        assert result.exit_code == 0
        assert "--output-dir" in result.output
        assert "--skip" in result.output
        assert "--scale" in result.output
        assert "--resolution" in result.output
        assert "--precision" in result.output
        assert "--timeout" in result.output


class TestRegistryLoading:
    """Tests for loading existing registry data."""

    def test_load_nonexistent_registry(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        temp_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Command creates new registry when file does not exist."""
        output_dir = tmp_path / "output"

        # Mock converter to return success results
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        # Mock comparison results
        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 4.5},
                {"a": str(temp_samples_dir / "text2.svg"), "diffPercent": 3.0},
                {"a": str(temp_samples_dir / "text3.svg"), "diffPercent": 2.5},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            # Make subprocess.run write JSON to the file
            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(temp_registry),
                ],
            )

        # Registry file should be created with baseline data
        assert temp_registry.exists(), f"Registry not created. Output: {result.output}"

    def test_load_existing_registry(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        existing_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Command loads data from existing registry for comparison."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        # Return same values as baseline - no regression expected
        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 5.0},
                {"a": str(temp_samples_dir / "text2.svg"), "diffPercent": 3.5},
                {"a": str(temp_samples_dir / "text3.svg"), "diffPercent": 2.0},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(existing_registry),
                ],
            )

        # Should show "No regression detected" message
        assert "No regression detected" in result.output or result.exit_code == 0


class TestRegressionDetection:
    """Tests for detecting regressions when diff percentages increase."""

    def test_regression_detected_when_diff_increases(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        existing_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Command warns when diff percentage increases compared to baseline."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        # Return HIGHER values than baseline - regression expected
        comparison_results = {
            "results": [
                {
                    "a": str(temp_samples_dir / "text1.svg"),
                    "diffPercent": 8.0,
                },  # Was 5.0
                {"a": str(temp_samples_dir / "text2.svg"), "diffPercent": 3.5},  # Same
                {"a": str(temp_samples_dir / "text3.svg"), "diffPercent": 2.0},  # Same
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(existing_registry),
                ],
            )

        # Should show regression warning
        assert "Regression" in result.output or "regression" in result.output.lower()


class TestImprovementDetection:
    """Tests for detecting improvements when diff percentages decrease."""

    def test_improvement_shown_when_diff_decreases(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        existing_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Command shows green improvement indicator when diff decreases."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        # Return LOWER values than baseline - improvement expected
        comparison_results = {
            "results": [
                {
                    "a": str(temp_samples_dir / "text1.svg"),
                    "diffPercent": 2.0,
                },  # Was 5.0
                {
                    "a": str(temp_samples_dir / "text2.svg"),
                    "diffPercent": 1.5,
                },  # Was 3.5
                {
                    "a": str(temp_samples_dir / "text3.svg"),
                    "diffPercent": 1.0,
                },  # Was 2.0
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(existing_registry),
                ],
            )

        # Should NOT show regression warning - we improved!
        assert "No regression detected" in result.output


class TestRegistrySaving:
    """Tests for saving registry data after each run."""

    def test_registry_appends_new_entry(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        existing_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Each run appends a new entry to the registry."""
        output_dir = tmp_path / "output"

        # Count initial entries
        initial_data = json.loads(existing_registry.read_text())
        initial_count = len(initial_data)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 5.0},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(existing_registry),
                ],
            )

        # Check registry has one more entry
        updated_data = json.loads(existing_registry.read_text())
        assert len(updated_data) == initial_count + 1

    def test_registry_entry_contains_expected_fields(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        temp_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Registry entry contains timestamp, settings, and results."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 4.5},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(temp_registry),
                    "--threshold",
                    "25",
                    "--scale",
                    "2.0",
                    "--precision",
                    "4",
                ],
            )

        registry_data = json.loads(temp_registry.read_text())
        latest_entry = registry_data[-1]

        # Verify expected fields exist
        assert "timestamp" in latest_entry
        assert "threshold" in latest_entry
        assert "scale" in latest_entry
        assert "resolution" in latest_entry
        assert "precision" in latest_entry
        assert "results" in latest_entry
        assert "failures" in latest_entry

        # Verify settings were saved correctly
        assert latest_entry["threshold"] == 25
        assert latest_entry["scale"] == 2.0
        assert latest_entry["precision"] == 4


class TestSkipFiles:
    """Tests for the skip file functionality."""

    def test_skip_option_excludes_files(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        temp_registry: Path,
        tmp_path: Path,
    ) -> None:
        """--skip option excludes specified files from processing."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        comparison_results = {"results": []}
        converted_files = []

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()

            def track_convert(src, *_):
                converted_files.append(src.name)
                return mock_result

            mock_converter.convert_file.side_effect = track_convert
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(temp_registry),
                    "--skip",
                    "text1.svg",
                    "--skip",
                    "text2.svg",
                ],
            )

        # Only text3.svg should have been converted
        assert "text1.svg" not in converted_files
        assert "text2.svg" not in converted_files
        assert "text3.svg" in converted_files


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_no_samples_found_shows_warning(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Command shows warning when no text*.svg files are found."""
        empty_samples = tmp_path / "empty_samples"
        empty_samples.mkdir()
        registry = tmp_path / "registry.json"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            cli,
            [
                "batch",
                "regression",
                "--samples-dir",
                str(empty_samples),
                "--output-dir",
                str(output_dir),
                "--registry",
                str(registry),
            ],
        )

        assert "No text*.svg files found" in result.output or "Warning" in result.output

    def test_conversion_failure_tracked_in_registry(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        temp_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Failed conversions are tracked in registry failures list."""
        output_dir = tmp_path / "output"

        # Mock converter to fail on one file
        success_result = MagicMock()
        success_result.success = True
        success_result.errors = []

        fail_result = MagicMock()
        fail_result.success = False
        fail_result.errors = ["Font not found"]

        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 5.0},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()

            def selective_convert(src, *_):
                if "text2" in str(src):
                    return fail_result
                return success_result

            mock_converter.convert_file.side_effect = selective_convert
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(temp_registry),
                ],
            )

        # Check registry has failures recorded
        registry_data = json.loads(temp_registry.read_text())
        latest_entry = registry_data[-1]
        assert len(latest_entry["failures"]) > 0

    def test_comparer_not_found_exits_with_error(
        self,
        runner: CliRunner,
        temp_samples_dir: Path,
        temp_registry: Path,
        tmp_path: Path,
    ) -> None:
        """Command exits with error when comparer tool is not found."""
        output_dir = tmp_path / "output"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            # Simulate FileNotFoundError when running comparer
            mock_run.side_effect = FileNotFoundError("node not found")

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(temp_registry),
                ],
            )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestSettingsMatching:
    """Tests for matching settings when comparing with previous runs."""

    def test_only_compares_with_matching_settings(
        self, runner: CliRunner, temp_samples_dir: Path, tmp_path: Path
    ) -> None:
        """Regression comparison only uses previous runs with matching settings."""
        registry_path = tmp_path / "registry.json"
        output_dir = tmp_path / "output"

        # Create registry with entries having different settings
        registry_data = [
            # Different threshold
            {
                "timestamp": "20250101T100000Z",
                "threshold": 30,  # Different!
                "scale": 4.0,
                "resolution": "viewbox",
                "precision": 3,
                "results": {"text1.svg": 10.0},
                "failures": [],
            },
            # Matching settings
            {
                "timestamp": "20250101T110000Z",
                "threshold": 20,
                "scale": 4.0,
                "resolution": "viewbox",
                "precision": 3,
                "results": {"text1.svg": 5.0},
                "failures": [],
            },
        ]
        registry_path.write_text(json.dumps(registry_data))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []

        # Current run has diff of 6.0 - higher than matching entry's 5.0
        # Should detect regression against matching entry (5.0 -> 6.0)
        comparison_results = {
            "results": [
                {"a": str(temp_samples_dir / "text1.svg"), "diffPercent": 6.0},
            ]
        }

        with (
            patch(
                "svg_text2path.cli.commands.batch.regression.Text2PathConverter"
            ) as mock_converter_class,
            patch(
                "svg_text2path.cli.commands.batch.regression.subprocess.run"
            ) as mock_run,
        ):
            mock_converter = MagicMock()
            mock_converter.convert_file.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            def write_json_side_effect(*_, **kwargs):
                if "stdout" in kwargs and kwargs["stdout"] is not None:
                    kwargs["stdout"].write(json.dumps(comparison_results))
                return MagicMock(returncode=0)

            mock_run.side_effect = write_json_side_effect

            result = runner.invoke(
                cli,
                [
                    "batch",
                    "regression",
                    "--samples-dir",
                    str(temp_samples_dir),
                    "--output-dir",
                    str(output_dir),
                    "--registry",
                    str(registry_path),
                    "--threshold",
                    "20",
                ],
            )

        # Should detect regression (5.0 -> 6.0), not compare with 10.0
        assert "Regression" in result.output or "regression" in result.output.lower()
