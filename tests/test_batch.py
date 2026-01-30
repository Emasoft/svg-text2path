"""Tests for batch conversion mode with YAML configuration.

Tests cover:
- YAML config loading and validation
- Batch settings parsing
- Input entry validation (folder mode vs file mode)
- Template generation
- Batch convert command execution
"""

from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from svg_text2path.cli.commands.batch import (
    BatchConfig,
    BatchConfigError,
    BatchSettings,
    FormatSelection,
    InputEntry,
    PathAccessResult,
    _check_path_accessibility,
    _is_remote_path,
    _parse_compact_entry,
    _validate_path_format,
    load_batch_config,
)
from svg_text2path.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner instance for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_svg_file(tmp_path: Path) -> Path:
    """Create a temporary SVG file with text for testing."""
    svg_content = dedent("""
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <text x="10" y="50" font-family="Arial" font-size="24">Hello</text>
        </svg>
    """).strip()
    svg_path = tmp_path / "test_input.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


@pytest.fixture
def temp_svg_folder(tmp_path: Path) -> Path:
    """Create a folder with multiple SVG files with text."""
    folder = tmp_path / "svg_folder"
    folder.mkdir()

    # SVG with text
    (folder / "has_text.svg").write_text(
        dedent("""
        <?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
          <text x="10" y="50">Sample text</text>
        </svg>
    """).strip()
    )

    # SVG without text (should be skipped)
    (folder / "no_text.svg").write_text(
        dedent("""
        <?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
          <rect x="10" y="10" width="80" height="80" fill="blue"/>
        </svg>
    """).strip()
    )

    return folder


# ---------------------------------------------------------------------------
# Tests for load_batch_config
# ---------------------------------------------------------------------------


class TestLoadBatchConfig:
    """Tests for YAML config loading and validation."""

    def test_load_minimal_config(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Minimal config with only required fields loads successfully."""
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            inputs:
              - path: {temp_svg_file}
                output: {tmp_path / "output.svg"}
        """)
        )

        config = load_batch_config(config_file)

        assert isinstance(config, BatchConfig)
        assert len(config.inputs) == 1
        assert config.inputs[0].path == temp_svg_file
        # Check defaults
        assert config.settings.precision == 6
        assert config.settings.jobs == 4
        assert config.settings.continue_on_error is True
        assert config.settings.formats.svg is True

    def test_load_full_config(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Config with all settings loads correctly."""
        config_file = tmp_path / "full.yaml"
        config_file.write_text(
            dedent(f"""
            settings:
              precision: 4
              preserve_styles: true
              system_fonts_only: true
              font_dirs:
                - /custom/fonts
              no_remote_fonts: true
              no_size_limit: true
              auto_download: true
              validate: true
              verify: true
              verify_pixel_threshold: 20
              verify_image_threshold: 3.5
              jobs: 8
              continue_on_error: false

            formats:
              svg: true
              svgz: true
              html: false

            inputs:
              - path: {temp_svg_file}
                output: {tmp_path / "output.svg"}

            log_file: custom_log.json
        """)
        )

        config = load_batch_config(config_file)

        assert config.settings.precision == 4
        assert config.settings.preserve_styles is True
        assert config.settings.system_fonts_only is True
        assert config.settings.font_dirs == ["/custom/fonts"]
        assert config.settings.no_remote_fonts is True
        assert config.settings.no_size_limit is True
        assert config.settings.auto_download is True
        assert config.settings.validate is True
        assert config.settings.verify is True
        assert config.settings.verify_pixel_threshold == 20
        assert config.settings.verify_image_threshold == 3.5
        assert config.settings.jobs == 8
        assert config.settings.continue_on_error is False
        assert config.log_file == Path("custom_log.json")
        assert config.settings.formats.svg is True
        assert config.settings.formats.svgz is True
        assert config.settings.formats.html is False

    def test_folder_mode_input(self, tmp_path: Path, temp_svg_folder: Path) -> None:
        """Folder mode input is parsed correctly."""
        config_file = tmp_path / "folder.yaml"
        output_dir = tmp_path / "output"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            inputs:
              - path: {temp_svg_folder}/
                output_dir: {output_dir}
                suffix: _converted
        """)
        )

        config = load_batch_config(config_file)

        assert len(config.inputs) == 1
        entry = config.inputs[0]
        assert entry.is_folder is True
        assert entry.output_dir == output_dir
        assert entry.suffix == "_converted"

    def test_file_mode_input(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """File mode input is parsed correctly."""
        config_file = tmp_path / "file.yaml"
        output_path = tmp_path / "output" / "result.svg"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            inputs:
              - path: {temp_svg_file}
                output: {output_path}
        """)
        )

        config = load_batch_config(config_file)

        assert len(config.inputs) == 1
        entry = config.inputs[0]
        assert entry.is_folder is False
        assert entry.output == output_path

    def test_mixed_inputs(
        self, tmp_path: Path, temp_svg_file: Path, temp_svg_folder: Path
    ) -> None:
        """Mixed folder and file mode inputs work together."""
        config_file = tmp_path / "mixed.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            inputs:
              - path: {temp_svg_folder}/
                output_dir: {tmp_path / "folder_out"}
                suffix: _batch
              - path: {temp_svg_file}
                output: {tmp_path / "file_out.svg"}
        """)
        )

        config = load_batch_config(config_file)

        assert len(config.inputs) == 2
        assert config.inputs[0].is_folder is True
        assert config.inputs[1].is_folder is False


class TestBatchConfigValidation:
    """Tests for config validation error handling."""

    def test_empty_config_raises(self, tmp_path: Path) -> None:
        """Empty YAML file raises BatchConfigError."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        with pytest.raises(BatchConfigError, match="Empty YAML config file"):
            load_batch_config(config_file)

    def test_missing_inputs_raises(self, tmp_path: Path) -> None:
        """Config without inputs section raises BatchConfigError."""
        config_file = tmp_path / "no_inputs.yaml"
        config_file.write_text(
            dedent("""
            formats:
              svg: true
            settings:
              precision: 6
        """)
        )

        with pytest.raises(BatchConfigError, match="inputs: required field is missing"):
            load_batch_config(config_file)

    def test_empty_inputs_raises(self, tmp_path: Path) -> None:
        """Config with empty inputs list raises BatchConfigError."""
        config_file = tmp_path / "empty_inputs.yaml"
        config_file.write_text(
            dedent("""
            formats:
              svg: true
            inputs: []
        """)
        )

        with pytest.raises(
            BatchConfigError, match="at least one input entry is required"
        ):
            load_batch_config(config_file)

    def test_missing_path_raises(self, tmp_path: Path) -> None:
        """Input entry without path field raises BatchConfigError."""
        config_file = tmp_path / "no_path.yaml"
        config_file.write_text(
            dedent("""
            formats:
              svg: true
            inputs:
              - output: /some/output.svg
        """)
        )

        with pytest.raises(BatchConfigError, match="missing required 'path' field"):
            load_batch_config(config_file)

    def test_folder_mode_missing_output_dir_raises(
        self, tmp_path: Path, temp_svg_folder: Path
    ) -> None:
        """Folder mode without output_dir raises BatchConfigError."""
        config_file = tmp_path / "folder_no_out.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            inputs:
              - path: {temp_svg_folder}/
        """)
        )

        with pytest.raises(BatchConfigError, match="folder mode requires 'output_dir'"):
            load_batch_config(config_file)

    def test_file_mode_missing_output_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """File mode without output raises BatchConfigError."""
        config_file = tmp_path / "file_no_out.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            inputs:
              - path: {temp_svg_file}
        """)
        )

        with pytest.raises(BatchConfigError, match="file mode requires 'output'"):
            load_batch_config(config_file)

    def test_invalid_precision_range(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Precision outside 1-10 raises BatchConfigError."""
        config_file = tmp_path / "bad_precision.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              precision: 15
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError, match="settings.precision: must be between 1 and 10"
        ):
            load_batch_config(config_file)

    def test_invalid_pixel_threshold_range(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Pixel threshold outside 1-255 raises BatchConfigError."""
        config_file = tmp_path / "bad_threshold.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              verify_pixel_threshold: 300
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError,
            match="settings.verify_pixel_threshold: must be between 1 and 255",
        ):
            load_batch_config(config_file)

    def test_invalid_image_threshold_range(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Image threshold outside 0-100 raises BatchConfigError."""
        config_file = tmp_path / "bad_img_threshold.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              verify_image_threshold: 150.0
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError,
            match="settings.verify_image_threshold: must be between 0.0 and 100.0",
        ):
            load_batch_config(config_file)

    def test_invalid_jobs_value(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Jobs less than 1 raises BatchConfigError."""
        config_file = tmp_path / "bad_jobs.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              jobs: 0
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(BatchConfigError, match="settings.jobs: must be at least 1"):
            load_batch_config(config_file)

    def test_invalid_type_in_settings(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Wrong type for setting value raises BatchConfigError."""
        config_file = tmp_path / "bad_type.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              precision: "high"
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError, match="settings.precision: expected integer, got str"
        ):
            load_batch_config(config_file)

    def test_invalid_font_dirs_type(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Non-string in font_dirs raises BatchConfigError."""
        config_file = tmp_path / "bad_fonts.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              font_dirs:
                - /valid/path
                - 123
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError,
            match="settings.font_dirs\\[1\\]: expected string path, got int",
        ):
            load_batch_config(config_file)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Non-existent config file raises FileNotFoundError."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_batch_config(config_file)

    def test_invalid_yaml_syntax_raises(self, tmp_path: Path) -> None:
        """Invalid YAML syntax raises BatchConfigError."""
        config_file = tmp_path / "bad_yaml.yaml"
        config_file.write_text("inputs:\n  - path: [unclosed bracket")

        with pytest.raises(BatchConfigError, match="Invalid YAML syntax"):
            load_batch_config(config_file)


# ---------------------------------------------------------------------------
# Tests for CLI commands
# ---------------------------------------------------------------------------


class TestBatchTemplateCommand:
    """Tests for the batch template command."""

    def test_template_creates_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """batch template creates YAML file."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["batch", "template", "my_config.yaml"])

            assert result.exit_code == 0
            assert Path("my_config.yaml").exists()
            content = Path("my_config.yaml").read_text()
            assert "settings:" in content
            assert "inputs:" in content
            assert "precision:" in content

    def test_template_default_filename(self, runner: CliRunner, tmp_path: Path) -> None:
        """batch template uses default filename when not specified."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["batch", "template"])

            assert result.exit_code == 0
            assert Path("batch_config.yaml").exists()

    def test_template_no_overwrite_without_force(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """batch template prompts before overwriting existing file."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("existing.yaml").write_text("old content")

            # Answer 'n' to overwrite prompt
            result = runner.invoke(
                cli, ["batch", "template", "existing.yaml"], input="n\n"
            )

            assert result.exit_code == 0
            assert "Aborted" in result.output
            assert Path("existing.yaml").read_text() == "old content"

    def test_template_force_overwrites(self, runner: CliRunner, tmp_path: Path) -> None:
        """batch template --force overwrites without prompting."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("existing.yaml").write_text("old content")

            result = runner.invoke(cli, ["batch", "template", "existing.yaml", "-f"])

            assert result.exit_code == 0
            assert "old content" not in Path("existing.yaml").read_text()
            assert "settings:" in Path("existing.yaml").read_text()


class TestBatchConvertCommand:
    """Tests for the batch convert command."""

    def test_batch_convert_with_valid_config(
        self, runner: CliRunner, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """batch convert processes files with valid YAML config."""
        output_file = tmp_path / "output.svg"
        log_file = tmp_path / "batch_log.json"
        config_file = tmp_path / "config.yaml"

        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            settings:
              precision: 6
              continue_on_error: true

            inputs:
              - path: {temp_svg_file}
                output: {output_file}

            log_file: {log_file}
        """)
        )

        result = runner.invoke(cli, ["batch", "convert", str(config_file)])

        # May fail on font resolution but CLI parsing should work
        assert result.exit_code in (0, 1), f"Unexpected exit: {result.output}"
        assert "Error loading config" not in result.output

    def test_batch_convert_requires_config_file(self, runner: CliRunner) -> None:
        """batch convert fails without config file argument."""
        result = runner.invoke(cli, ["batch", "convert"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "CONFIG_FILE" in result.output

    def test_batch_convert_invalid_config_shows_error(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """batch convert shows validation errors for invalid config."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text(
            dedent("""
            settings:
              precision: 100
            inputs: []
        """)
        )

        result = runner.invoke(cli, ["batch", "convert", str(config_file)])

        assert result.exit_code != 0
        assert "Error loading config" in result.output

    def test_batch_convert_folder_mode(
        self, runner: CliRunner, tmp_path: Path, temp_svg_folder: Path
    ) -> None:
        """batch convert processes folder with SVG files."""
        output_dir = tmp_path / "converted"
        log_file = tmp_path / "batch_log.json"
        config_file = tmp_path / "folder_config.yaml"

        config_file.write_text(
            dedent(f"""
            formats:
              svg: true

            settings:
              continue_on_error: true
              jobs: 1

            inputs:
              - path: {temp_svg_folder}/
                output_dir: {output_dir}
                suffix: _out

            log_file: {log_file}
        """)
        )

        result = runner.invoke(cli, ["batch", "convert", str(config_file)])

        # May fail on font resolution but should not fail on config parsing
        assert "Error loading config" not in result.output


class TestBatchHelpCommand:
    """Tests for batch command help."""

    def test_batch_help_shows_subcommands(self, runner: CliRunner) -> None:
        """batch --help shows available subcommands."""
        result = runner.invoke(cli, ["batch", "--help"])

        assert result.exit_code == 0
        assert "convert" in result.output
        assert "compare" in result.output
        assert "regression" in result.output
        assert "template" in result.output


# ---------------------------------------------------------------------------
# Tests for BatchSettings dataclass
# ---------------------------------------------------------------------------


class TestBatchSettingsDefaults:
    """Tests for BatchSettings default values."""

    def test_default_values(self) -> None:
        """BatchSettings has correct default values."""
        settings = BatchSettings()

        assert settings.precision == 6
        assert settings.preserve_styles is False
        assert settings.system_fonts_only is False
        assert settings.font_dirs == []
        assert settings.no_remote_fonts is False
        assert settings.no_size_limit is False
        assert settings.auto_download is False
        assert settings.validate is False
        assert settings.verify is False
        assert settings.verify_pixel_threshold == 10
        assert settings.verify_image_threshold == 5.0
        assert settings.jobs == 4
        assert settings.continue_on_error is True


class TestInputEntry:
    """Tests for InputEntry dataclass."""

    def test_folder_mode_entry(self) -> None:
        """InputEntry for folder mode has correct attributes."""
        entry = InputEntry(
            path=Path("/input/folder"),
            is_folder=True,
            output_dir=Path("/output/folder"),
            suffix="_converted",
        )

        assert entry.is_folder is True
        assert entry.output_dir == Path("/output/folder")
        assert entry.suffix == "_converted"
        assert entry.output is None

    def test_file_mode_entry(self) -> None:
        """InputEntry for file mode has correct attributes."""
        entry = InputEntry(
            path=Path("/input/file.svg"),
            is_folder=False,
            output=Path("/output/result.svg"),
        )

        assert entry.is_folder is False
        assert entry.output == Path("/output/result.svg")
        assert entry.output_dir is None
        assert entry.suffix == "_text2path"  # default


# ---------------------------------------------------------------------------
# Tests for FormatSelection
# ---------------------------------------------------------------------------


class TestFormatSelection:
    """Tests for FormatSelection dataclass and validation."""

    def test_default_svg_enabled(self) -> None:
        """FormatSelection defaults to svg enabled, others disabled."""
        formats = FormatSelection()

        assert formats.svg is True  # SVG enabled by default
        assert formats.svgz is False
        assert formats.html is False
        assert formats.css is False
        assert formats.json is False
        assert formats.csv is False
        assert formats.markdown is False
        assert formats.python is False
        assert formats.javascript is False
        assert formats.rst is False
        assert formats.plaintext is False
        assert formats.epub is False

    def test_missing_formats_section_defaults_to_svg(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config without formats section defaults to svg only."""
        config_file = tmp_path / "no_formats.yaml"
        config_file.write_text(
            dedent(f"""
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        config = load_batch_config(config_file)

        # SVG should be enabled by default
        assert config.settings.formats.svg is True
        assert config.settings.formats.html is False
        assert config.settings.formats.python is False

    def test_all_formats_disabled_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config with all formats explicitly disabled raises BatchConfigError."""
        config_file = tmp_path / "all_formats_disabled.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: false
              svgz: false
              html: false
              css: false
              json: false
              csv: false
              markdown: false
              python: false
              javascript: false
              rst: false
              plaintext: false
              epub: false
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError,
            match="at least one format must be enabled",
        ):
            load_batch_config(config_file)

    def test_unknown_format_warns(self, tmp_path: Path, temp_svg_file: Path) -> None:
        """Config with unknown format raises BatchConfigError."""
        config_file = tmp_path / "unknown_format.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
              unknown_format: true
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(BatchConfigError, match="unknown format"):
            load_batch_config(config_file)

    def test_invalid_format_type_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config with non-boolean format value raises BatchConfigError."""
        config_file = tmp_path / "bad_format_type.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: "yes"
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(BatchConfigError, match="expected boolean"):
            load_batch_config(config_file)

    def test_multiple_formats_enabled(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config with multiple formats enabled loads correctly."""
        config_file = tmp_path / "multi_formats.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
              svgz: true
              html: true
              python: false
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        config = load_batch_config(config_file)

        assert config.settings.formats.svg is True
        assert config.settings.formats.svgz is True
        assert config.settings.formats.html is True
        assert config.settings.formats.python is False


# ---------------------------------------------------------------------------
# Tests for compact input format and remote paths
# ---------------------------------------------------------------------------


class TestCompactInputFormat:
    """Tests for the compact semicolon-delimited input format."""

    def test_parse_file_mode(self) -> None:
        """Parse compact file mode: input;output."""
        result = _parse_compact_entry("./input.svg;./output.svg")

        assert result["path"] == "./input.svg"
        assert result["output"] == "./output.svg"
        assert result["_is_folder"] is False

    def test_parse_folder_mode(self) -> None:
        """Parse compact folder mode: input/;output/;suffix."""
        result = _parse_compact_entry("./input/;./output/;_converted")

        assert result["path"] == "./input"
        assert result["output_dir"] == "./output"
        assert result["suffix"] == "_converted"
        assert result["_is_folder"] is True

    def test_parse_folder_mode_default_suffix(self) -> None:
        """Parse folder mode with default suffix."""
        result = _parse_compact_entry("./input/;./output/")

        assert result["path"] == "./input"
        assert result["output_dir"] == "./output"
        assert result["suffix"] == "_text2path"
        assert result["_is_folder"] is True

    def test_parse_url_encoded_spaces(self) -> None:
        """Parse paths with URL-encoded spaces (%20)."""
        result = _parse_compact_entry("./my%20files/input.svg;./my%20output/file.svg")

        assert result["path"] == "./my files/input.svg"
        assert result["output"] == "./my output/file.svg"

    def test_parse_invalid_format_raises(self) -> None:
        """Invalid format (missing output) raises ValueError."""
        with pytest.raises(ValueError, match="Invalid format"):
            _parse_compact_entry("./input.svg")

    def test_load_config_with_compact_format(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Load config with compact string format entries."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config_file = tmp_path / "compact.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            inputs:
              - {temp_svg_file};{output_dir / "out.svg"}
        """)
        )

        config = load_batch_config(config_file)

        assert len(config.inputs) == 1
        assert config.inputs[0].is_folder is False
        assert config.inputs[0].output == output_dir / "out.svg"

    def test_load_config_mixed_formats(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Load config with both compact and dict format entries."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config_file = tmp_path / "mixed.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            inputs:
              # Compact format
              - {temp_svg_file};{output_dir / "out1.svg"}
              # Dict format
              - path: {temp_svg_file}
                output: {output_dir / "out2.svg"}
        """)
        )

        config = load_batch_config(config_file)

        assert len(config.inputs) == 2
        assert config.inputs[0].output == output_dir / "out1.svg"
        assert config.inputs[1].output == output_dir / "out2.svg"

    def test_parse_escaped_semicolon_backslash(self) -> None:
        """Parse paths with backslash-escaped semicolons (\\;)."""
        result = _parse_compact_entry("./path\\;with\\;semicolons.svg;./output.svg")

        assert result["path"] == "./path;with;semicolons.svg"
        assert result["output"] == "./output.svg"

    def test_parse_escaped_semicolon_url_encoded(self) -> None:
        """Parse paths with URL-encoded semicolons (%3B)."""
        result = _parse_compact_entry("./path%3Bwith%3Bsemicolons.svg;./output.svg")

        assert result["path"] == "./path;with;semicolons.svg"
        assert result["output"] == "./output.svg"

    def test_parse_mixed_escaping(self) -> None:
        """Parse paths with mixed escaping (backslash and URL encoding)."""
        # Input with \; and output with %3B
        result = _parse_compact_entry("./in\\;put.svg;./out%3Bput.svg")

        assert result["path"] == "./in;put.svg"
        assert result["output"] == "./out;put.svg"


class TestRemotePathDetection:
    """Tests for remote path detection (SSH, URLs)."""

    def test_ssh_path_detected(self) -> None:
        """SSH paths (user@host:path) are detected as remote."""
        assert _is_remote_path("user@192.168.1.10:/home/user/file.svg") is True
        assert _is_remote_path("root@server:/var/www/image.svg") is True

    def test_https_url_detected(self) -> None:
        """HTTPS URLs are detected as remote."""
        assert _is_remote_path("https://example.com/icon.svg") is True
        assert _is_remote_path("https://cdn.site.org/assets/logo.svg") is True

    def test_http_url_detected(self) -> None:
        """HTTP URLs are detected as remote."""
        assert _is_remote_path("http://example.com/icon.svg") is True

    def test_ftp_url_detected(self) -> None:
        """FTP URLs are detected as remote."""
        assert _is_remote_path("ftp://files.example.com/icon.svg") is True

    def test_sftp_url_detected(self) -> None:
        """SFTP URLs are detected as remote."""
        assert _is_remote_path("sftp://files.example.com/icon.svg") is True

    def test_local_path_not_detected(self) -> None:
        """Local paths are not detected as remote."""
        assert _is_remote_path("./local/file.svg") is False
        assert _is_remote_path("/absolute/path/file.svg") is False
        assert _is_remote_path("~/Documents/file.svg") is False
        assert _is_remote_path("relative/path/file.svg") is False

    def test_email_in_path_not_detected(self) -> None:
        """Paths containing @ but not SSH format are not detected as remote."""
        # Email-like local path should not be detected as SSH
        assert _is_remote_path("./user@local/file.svg") is False


class TestAllowOverwrite:
    """Tests for allow_overwrite setting validation."""

    def test_same_input_output_without_allow_overwrite_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Same input/output path without allow_overwrite raises error."""
        config_file = tmp_path / "overwrite.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              allow_overwrite: false
            inputs:
              - {temp_svg_file};{temp_svg_file}
        """)
        )

        with pytest.raises(BatchConfigError, match="input and output are the same"):
            load_batch_config(config_file)

    def test_same_input_output_with_allow_overwrite_succeeds(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Same input/output path with allow_overwrite loads successfully."""
        config_file = tmp_path / "overwrite_ok.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              allow_overwrite: true
            inputs:
              - {temp_svg_file};{temp_svg_file}
        """)
        )

        config = load_batch_config(config_file)

        assert config.settings.allow_overwrite is True
        assert len(config.inputs) == 1
        assert str(config.inputs[0].path) == str(config.inputs[0].output)


class TestPathValidation:
    """Tests for path format validation."""

    def test_valid_local_paths(self) -> None:
        """Valid local paths return no errors."""
        assert _validate_path_format("./local/file.svg") == []
        assert _validate_path_format("/absolute/path/file.svg") == []
        assert _validate_path_format("~/Documents/file.svg") == []
        assert _validate_path_format("relative/path/file.svg") == []

    def test_valid_ssh_paths(self) -> None:
        """Valid SSH paths return no errors."""
        assert _validate_path_format("user@host:/path/to/file.svg") == []
        assert _validate_path_format("root@192.168.1.10:/var/www/file.svg") == []
        assert _validate_path_format("admin@server.example.com:/home/file.svg") == []

    def test_valid_urls(self) -> None:
        """Valid URLs return no errors."""
        assert _validate_path_format("https://example.com/icon.svg") == []
        assert _validate_path_format("http://cdn.site.org/assets/logo.svg") == []
        assert _validate_path_format("ftp://files.example.com/file.svg") == []
        assert _validate_path_format("sftp://secure.example.com/file.svg") == []

    def test_empty_path_error(self) -> None:
        """Empty path returns error."""
        errors = _validate_path_format("")
        assert len(errors) == 1
        assert "empty" in errors[0]

    def test_whitespace_only_path_error(self) -> None:
        """Whitespace-only path returns error."""
        errors = _validate_path_format("   ")
        assert len(errors) == 1
        assert "empty" in errors[0]

    def test_url_missing_host_error(self) -> None:
        """URL without host returns error."""
        errors = _validate_path_format("https:///path/file.svg")
        assert len(errors) == 1
        assert "missing host" in errors[0]

    def test_ssh_invalid_user_error(self) -> None:
        """SSH path with invalid user returns error."""
        errors = _validate_path_format("123user@host:/path")
        assert len(errors) >= 1
        assert any("user" in e.lower() for e in errors)

    def test_ssh_empty_host_error(self) -> None:
        """SSH path with empty host returns error."""
        errors = _validate_path_format("user@:/path")
        assert len(errors) >= 1
        assert any("host" in e.lower() for e in errors)

    def test_ssh_empty_path_error(self) -> None:
        """SSH path with empty remote path returns error."""
        errors = _validate_path_format("user@host:")
        assert len(errors) >= 1
        assert any("path" in e.lower() for e in errors)

    def test_null_byte_error(self) -> None:
        """Path with null byte returns error."""
        errors = _validate_path_format("path\x00with\x00nulls.svg")
        assert len(errors) == 1
        assert "null" in errors[0]

    def test_windows_drive_letter(self) -> None:
        """Windows drive letter path is valid."""
        assert _validate_path_format("C:/Users/file.svg") == []
        assert _validate_path_format("D:\\Documents\\file.svg") == []

    def test_windows_invalid_drive_letter(self) -> None:
        """Invalid Windows drive letter returns error."""
        errors = _validate_path_format("1:/invalid/path")
        assert len(errors) >= 1
        assert any("drive" in e.lower() for e in errors)

    def test_config_with_invalid_path_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config with invalid path format raises BatchConfigError."""
        config_file = tmp_path / "invalid_path.yaml"
        config_file.write_text(
            dedent("""
            formats:
              svg: true
            inputs:
              - user@:/missing_host.svg;./output.svg
        """)
        )

        with pytest.raises(BatchConfigError, match="host"):
            load_batch_config(config_file)


class TestPathAccessibility:
    """Tests for path accessibility checking."""

    def test_local_path_accessible(self, temp_svg_file: Path) -> None:
        """Existing local file is accessible."""
        result = _check_path_accessibility(str(temp_svg_file))
        assert result.accessible is True
        assert result.error_type is None

    def test_local_dir_accessible(self, tmp_path: Path) -> None:
        """Existing local directory is accessible."""
        result = _check_path_accessibility(str(tmp_path))
        assert result.accessible is True

    def test_nonexistent_path_not_accessible(self, tmp_path: Path) -> None:
        """Non-existent path with missing parent is not accessible."""
        nonexistent = tmp_path / "does_not_exist" / "deeply" / "nested" / "file.svg"
        result = _check_path_accessibility(str(nonexistent))
        assert result.accessible is False
        assert result.error_type == "not_found"

    def test_write_check_writable_dir(self, tmp_path: Path) -> None:
        """Writable directory passes write check."""
        result = _check_path_accessibility(str(tmp_path), check_write=True)
        assert result.accessible is True

    def test_path_access_result_dataclass(self) -> None:
        """PathAccessResult dataclass has correct fields."""
        result = PathAccessResult(
            accessible=False,
            error_type="network",
            error_message="Connection failed",
            suggestion="Check network",
        )
        assert result.accessible is False
        assert result.error_type == "network"
        assert result.error_message == "Connection failed"
        assert result.suggestion == "Check network"

    def test_url_format_accessible(self) -> None:
        """Well-formed URL with resolvable host is considered accessible."""
        # Note: This test may fail if DNS is not working
        # We're testing the format validation, not actual connectivity
        result = _check_path_accessibility("https://example.com/file.svg")
        # example.com should be resolvable
        assert result.accessible is True or result.error_type == "network"

    def test_invalid_ssh_host_not_accessible(self) -> None:
        """SSH path with unresolvable host is not accessible."""
        result = _check_path_accessibility("user@nonexistent-host-xyz123.invalid:/path")
        assert result.accessible is False
        assert result.error_type == "network"


class TestPreflightCheckSetting:
    """Tests for preflight_check setting."""

    def test_preflight_check_default_true(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Preflight check is enabled by default."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            inputs:
              - {temp_svg_file};{tmp_path / "out.svg"}
        """)
        )

        config = load_batch_config(config_file)
        assert config.settings.preflight_check is True

    def test_preflight_check_can_be_disabled(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Preflight check can be disabled in settings."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: true
            settings:
              preflight_check: false
            inputs:
              - {temp_svg_file};{tmp_path / "out.svg"}
        """)
        )

        config = load_batch_config(config_file)
        assert config.settings.preflight_check is False


class TestPreflightErrorsInLogReport:
    """Tests for preflight errors being saved to JSON log report."""

    def test_preflight_error_structure(self) -> None:
        """Verify PathAccessResult can be serialized for log report."""
        error = PathAccessResult(
            accessible=False,
            error_type="auth",
            error_message="SSH key rejected",
            suggestion="Check your SSH key configuration",
        )

        # Simulate the log report structure
        log_entry = {
            "path": "/some/path.svg",
            "error_type": error.error_type,
            "error_message": error.error_message,
            "suggestion": error.suggestion,
        }

        assert log_entry["path"] == "/some/path.svg"
        assert log_entry["error_type"] == "auth"
        assert log_entry["error_message"] == "SSH key rejected"
        assert log_entry["suggestion"] == "Check your SSH key configuration"

    def test_preflight_errors_list_serializable(self) -> None:
        """List of preflight errors can be JSON serialized."""
        errors: list[tuple[str, PathAccessResult]] = [
            (
                "/input1.svg",
                PathAccessResult(
                    accessible=False,
                    error_type="permission",
                    error_message="Permission denied",
                    suggestion="Check file permissions",
                ),
            ),
            (
                "/input2.svg",
                PathAccessResult(
                    accessible=False,
                    error_type="network",
                    error_message="Host unreachable",
                    suggestion="Check network connection",
                ),
            ),
        ]

        # Simulate the log report conversion
        preflight_errors_json = [
            {
                "path": path,
                "error_type": result.error_type,
                "error_message": result.error_message,
                "suggestion": result.suggestion,
            }
            for path, result in errors
        ]

        import json

        # Should be JSON serializable without errors
        json_str = json.dumps(preflight_errors_json)
        parsed = json.loads(json_str)

        assert len(parsed) == 2
        assert parsed[0]["path"] == "/input1.svg"
        assert parsed[0]["error_type"] == "permission"
        assert parsed[1]["path"] == "/input2.svg"
        assert parsed[1]["error_type"] == "network"
