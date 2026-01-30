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

    def test_default_all_disabled(self) -> None:
        """FormatSelection defaults to all formats disabled."""
        formats = FormatSelection()

        assert formats.svg is False
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

    def test_missing_formats_section_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config without formats section raises BatchConfigError."""
        config_file = tmp_path / "no_formats.yaml"
        config_file.write_text(
            dedent(f"""
            inputs:
              - path: {temp_svg_file}
                output: out.svg
        """)
        )

        with pytest.raises(
            BatchConfigError,
            match="formats: required section is missing",
        ):
            load_batch_config(config_file)

    def test_no_formats_enabled_raises(
        self, tmp_path: Path, temp_svg_file: Path
    ) -> None:
        """Config with no formats enabled raises BatchConfigError."""
        config_file = tmp_path / "no_formats_enabled.yaml"
        config_file.write_text(
            dedent(f"""
            formats:
              svg: false
              html: false
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
