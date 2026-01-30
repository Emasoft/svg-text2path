"""Tests for the deps CLI command (svg_text2path/cli/commands/deps.py).

Coverage: 8 tests covering CLI help, basic execution, filter options,
JSON output, strict mode exit codes, and missing dependency detection.
Tests use CliRunner for isolated command invocation.
"""

import json
import re
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from svg_text2path.cli.main import cli
from svg_text2path.tools.dependencies import (
    DependencyInfo,
    DependencyReport,
    DependencyStatus,
    DependencyType,
)


def extract_json_from_output(output: str) -> dict:
    """Extract JSON object from CLI output that may contain ANSI codes or banners.

    Rich's print_json outputs formatted JSON with possible styling.
    This function finds and extracts the JSON portion.
    """
    # Remove ANSI escape codes
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    clean = ansi_escape.sub("", output)
    # Find JSON object boundaries (first { to last })
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in output: {output[:200]}")
    json_str = clean[start:end]
    return json.loads(json_str)


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner instance for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_report_all_ok() -> DependencyReport:
    """Create a DependencyReport where all required dependencies are satisfied."""
    return DependencyReport(
        python_packages=[
            DependencyInfo(
                name="click",
                dep_type=DependencyType.PYTHON_PACKAGE,
                required=True,
                status=DependencyStatus.OK,
                version="8.1.7",
                feature="CLI framework",
            ),
            DependencyInfo(
                name="rich",
                dep_type=DependencyType.PYTHON_PACKAGE,
                required=True,
                status=DependencyStatus.OK,
                version="13.7.0",
                feature="Rich terminal output",
            ),
        ],
        system_tools=[
            DependencyInfo(
                name="node",
                dep_type=DependencyType.SYSTEM_TOOL,
                required=False,
                status=DependencyStatus.OK,
                version="20.10.0",
                feature="Visual comparison",
            ),
        ],
        npm_packages=[
            DependencyInfo(
                name="svg-bbox",
                dep_type=DependencyType.NPM_PACKAGE,
                required=False,
                status=DependencyStatus.OK,
                version="1.2.0",
                feature="SVG bounding box calculation",
            ),
        ],
    )


@pytest.fixture
def mock_report_missing_required() -> DependencyReport:
    """Create a DependencyReport with missing required dependencies."""
    return DependencyReport(
        python_packages=[
            DependencyInfo(
                name="click",
                dep_type=DependencyType.PYTHON_PACKAGE,
                required=True,
                status=DependencyStatus.OK,
                version="8.1.7",
            ),
            DependencyInfo(
                name="fonttools",
                dep_type=DependencyType.PYTHON_PACKAGE,
                required=True,
                status=DependencyStatus.MISSING,
                install_hint="pip install fonttools",
                feature="Font parsing",
            ),
        ],
        system_tools=[],
        npm_packages=[],
    )


@pytest.fixture
def mock_report_missing_optional() -> DependencyReport:
    """Create a DependencyReport with only optional dependencies missing."""
    return DependencyReport(
        python_packages=[
            DependencyInfo(
                name="click",
                dep_type=DependencyType.PYTHON_PACKAGE,
                required=True,
                status=DependencyStatus.OK,
                version="8.1.7",
            ),
        ],
        system_tools=[
            DependencyInfo(
                name="inkscape",
                dep_type=DependencyType.SYSTEM_TOOL,
                required=False,
                status=DependencyStatus.MISSING,
                install_hint="brew install inkscape",
                feature="Reference rendering",
            ),
        ],
        npm_packages=[],
    )


class TestDepsHelp:
    """Tests for the deps command help text."""

    def test_deps_help_shows_usage_and_options(self, runner: CliRunner) -> None:
        """deps --help displays usage information and all available options."""
        result = runner.invoke(cli, ["deps", "--help"])
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        # Check command description is shown
        assert "Check and report on all dependencies" in result.output
        # Check all options are documented
        assert "--all" in result.output
        assert "--python-only" in result.output
        assert "--system-only" in result.output
        assert "--npm-only" in result.output
        assert "--json" in result.output
        assert "--strict" in result.output


class TestDepsBasicExecution:
    """Tests for basic deps command execution."""

    def test_deps_runs_and_produces_output(self, runner: CliRunner) -> None:
        """deps command executes successfully and produces output."""
        result = runner.invoke(cli, ["deps"])
        # Command should run (exit 0) or warn about missing optional (exit 0)
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
        # Should produce some output
        assert len(result.output) > 0

    def test_deps_with_all_flag_shows_all_dependencies(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --all shows all dependencies including OK ones."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_all_ok,
        ):
            result = runner.invoke(cli, ["deps", "--all"])
            assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
            # Should show OK dependencies when --all is used
            assert "click" in result.output
            assert "rich" in result.output


class TestDepsFilterOptions:
    """Tests for deps command filter options."""

    def test_deps_python_only_checks_only_python_packages(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --python-only only checks Python packages."""
        # Create a report that simulates python-only check (empty system/npm)
        python_only_report = DependencyReport(
            python_packages=mock_report_all_ok.python_packages,
            system_tools=[],
            npm_packages=[],
        )
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=python_only_report,
        ):
            result = runner.invoke(cli, ["deps", "--python-only", "--json"])
            assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
            data = extract_json_from_output(result.output)
            # Python packages should be populated
            assert "python_packages" in data
            assert len(data["python_packages"]) > 0
            # System tools and npm should be empty (not checked)
            assert data["system_tools"] == []
            assert data["npm_packages"] == []

    def test_deps_system_only_checks_only_system_tools(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --system-only only checks system tools."""
        # Create a report that simulates system-only check (empty python/npm)
        system_only_report = DependencyReport(
            python_packages=[],
            system_tools=mock_report_all_ok.system_tools,
            npm_packages=[],
        )
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=system_only_report,
        ):
            result = runner.invoke(cli, ["deps", "--system-only", "--json"])
            assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
            data = extract_json_from_output(result.output)
            # System tools should be populated
            assert "system_tools" in data
            assert len(data["system_tools"]) > 0
            # Python and npm should be empty (not checked)
            assert data["python_packages"] == []
            assert data["npm_packages"] == []

    def test_deps_npm_only_checks_only_npm_packages(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --npm-only only checks npm packages."""
        # Create a report that simulates npm-only check (empty python/system)
        npm_only_report = DependencyReport(
            python_packages=[],
            system_tools=[],
            npm_packages=mock_report_all_ok.npm_packages,
        )
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=npm_only_report,
        ):
            result = runner.invoke(cli, ["deps", "--npm-only", "--json"])
            assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
            data = extract_json_from_output(result.output)
            # npm packages should be populated
            assert "npm_packages" in data
            assert len(data["npm_packages"]) > 0
            # Python and system should be empty (not checked)
            assert data["python_packages"] == []
            assert data["system_tools"] == []


class TestDepsJsonOutput:
    """Tests for deps command JSON output format."""

    def test_deps_json_output_is_valid_json(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --json outputs valid JSON."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_all_ok,
        ):
            result = runner.invoke(cli, ["deps", "--json"])
            assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
            # Should parse as valid JSON without exception (handles rich formatting)
            data = extract_json_from_output(result.output)
            assert isinstance(data, dict)

    def test_deps_json_output_contains_expected_keys(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --json output contains all expected top-level keys."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_all_ok,
        ):
            result = runner.invoke(cli, ["deps", "--json"])
            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            # Check all expected keys present
            assert "all_required_ok" in data
            assert "all_ok" in data
            assert "python_packages" in data
            assert "system_tools" in data
            assert "npm_packages" in data
            # Check package structure has expected fields
            assert len(data["python_packages"]) > 0
            pkg = data["python_packages"][0]
            assert "name" in pkg
            assert "status" in pkg
            assert "required" in pkg
            assert "version" in pkg


class TestDepsStrictMode:
    """Tests for deps command --strict mode exit codes."""

    def test_deps_strict_exits_zero_when_all_required_ok(
        self, runner: CliRunner, mock_report_all_ok: DependencyReport
    ) -> None:
        """deps --strict exits 0 when all required dependencies are satisfied."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_all_ok,
        ):
            result = runner.invoke(cli, ["deps", "--strict"])
            assert result.exit_code == 0

    def test_deps_strict_exits_one_when_required_missing(
        self, runner: CliRunner, mock_report_missing_required: DependencyReport
    ) -> None:
        """deps --strict exits 1 when required dependencies are missing."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_missing_required,
        ):
            result = runner.invoke(cli, ["deps", "--strict"])
            assert result.exit_code == 1

    def test_deps_strict_exits_two_when_only_optional_missing(
        self, runner: CliRunner, mock_report_missing_optional: DependencyReport
    ) -> None:
        """deps --strict exits 2 when only optional dependencies are missing."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_missing_optional,
        ):
            result = runner.invoke(cli, ["deps", "--strict"])
            assert result.exit_code == 2


class TestDepsMissingDependencyDetection:
    """Tests for deps command output when dependencies are missing."""

    def test_deps_shows_missing_required_error_message(
        self, runner: CliRunner, mock_report_missing_required: DependencyReport
    ) -> None:
        """deps shows error message when required dependencies are missing."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_missing_required,
        ):
            result = runner.invoke(cli, ["deps"])
            # Should indicate missing required dependencies
            assert "Missing" in result.output or "missing" in result.output.lower()
            assert "required" in result.output.lower()

    def test_deps_shows_install_hints_for_missing(
        self, runner: CliRunner, mock_report_missing_required: DependencyReport
    ) -> None:
        """deps shows installation hints for missing dependencies."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_missing_required,
        ):
            result = runner.invoke(cli, ["deps"])
            # Should show install hint for fonttools
            assert "pip install fonttools" in result.output

    def test_deps_shows_optional_missing_warning(
        self, runner: CliRunner, mock_report_missing_optional: DependencyReport
    ) -> None:
        """deps shows warning when optional dependencies are missing."""
        with patch(
            "svg_text2path.cli.commands.deps.verify_all_dependencies",
            return_value=mock_report_missing_optional,
        ):
            result = runner.invoke(cli, ["deps"])
            # Should indicate optional missing (not error, warning)
            assert "optional" in result.output.lower()
