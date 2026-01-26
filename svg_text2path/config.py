"""Configuration management for svg-text2path.

Supports:
- YAML config files (~/.text2path/config.yaml or ./text2path.yaml)
- Environment variables (TEXT2PATH_*)
- Programmatic configuration
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FontConfig:
    """Font resolution configuration."""

    system_only: bool = False
    """Only use system fonts, don't fetch remote fonts."""

    remote: bool = True
    """Allow fetching fonts from remote URLs."""

    custom_dirs: list[Path] = field(default_factory=list)
    """Additional directories to search for fonts."""

    replacements: dict[str, str] = field(default_factory=dict)
    """Font name replacements (e.g., Arial -> Liberation Sans)."""

    fallbacks: dict[str, list[str]] = field(default_factory=dict)
    """Fallback chains by generic family (sans-serif, serif, monospace)."""


@dataclass
class ConversionConfig:
    """Conversion settings."""

    precision: int = 6
    """Decimal precision for path coordinates."""

    preserve_styles: bool = False
    """Preserve font styling metadata on converted path elements."""

    output_suffix: str = "_text2path"
    """Suffix added to output filenames."""


@dataclass
class SecurityConfig:
    """Security and resource limit settings."""

    ignore_size_limits: bool = False
    """Bypass file size limits for processing large files.

    WARNING: Disabling size limits may expose the system to:
    - Memory exhaustion from decompression bombs (gzip, ZIP)
    - Denial of service from extremely large files

    Only enable when processing trusted files that exceed default limits.
    """

    max_file_size_mb: int = 50
    """Maximum file size in megabytes (default: 50MB)."""

    max_decompressed_size_mb: int = 100
    """Maximum decompressed size for gzip/ZIP files in megabytes (default: 100MB)."""


@dataclass
class Config:
    """Main configuration class for svg-text2path."""

    fonts: FontConfig = field(default_factory=FontConfig)
    conversion: ConversionConfig = field(default_factory=ConversionConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    log_level: str = "WARNING"
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".text2path" / "cache"
    )
    tools_dir: Path = field(
        default_factory=lambda: Path.home() / ".text2path" / "tools"
    )

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "Config":
        """Load configuration from file and environment.

        Priority (highest to lowest):
        1. Environment variables (TEXT2PATH_*)
        2. Specified config file
        3. ./text2path.yaml (local)
        4. ~/.text2path/config.yaml (global)
        5. Built-in defaults

        Args:
            config_path: Optional explicit path to config file.

        Returns:
            Merged configuration object.
        """
        config = cls()

        # Load from config files (lowest priority first)
        global_config = Path.home() / ".text2path" / "config.yaml"
        local_config = Path.cwd() / "text2path.yaml"

        for path in [global_config, local_config]:
            if path.exists():
                config._merge_yaml(path)

        if config_path:
            path = Path(config_path)
            if path.exists():
                config._merge_yaml(path)

        # Override with environment variables
        config._apply_env_vars()

        return config

    def _merge_yaml(self, path: Path) -> None:
        """Merge YAML config file into current config."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            return

        # Fonts
        if "fonts" in data:
            fonts = data["fonts"]
            if "system_only" in fonts:
                self.fonts.system_only = fonts["system_only"]
            if "remote" in fonts:
                self.fonts.remote = fonts["remote"]
            if "custom_dirs" in fonts:
                self.fonts.custom_dirs = [
                    Path(p).expanduser() for p in fonts["custom_dirs"]
                ]
            if "replacements" in fonts:
                self.fonts.replacements.update(fonts["replacements"])
            if "fallbacks" in fonts:
                self.fonts.fallbacks.update(fonts["fallbacks"])

        # Conversion
        if "defaults" in data:
            defaults = data["defaults"]
            if "precision" in defaults:
                self.conversion.precision = defaults["precision"]
            if "preserve_styles" in defaults:
                self.conversion.preserve_styles = defaults["preserve_styles"]
            if "output_suffix" in defaults:
                self.conversion.output_suffix = defaults["output_suffix"]

        # Security
        if "security" in data:
            security = data["security"]
            if "ignore_size_limits" in security:
                self.security.ignore_size_limits = security["ignore_size_limits"]
            if "max_file_size_mb" in security:
                self.security.max_file_size_mb = security["max_file_size_mb"]
            if "max_decompressed_size_mb" in security:
                self.security.max_decompressed_size_mb = security[
                    "max_decompressed_size_mb"
                ]

        # General
        if "log_level" in data:
            self.log_level = data["log_level"]
        if "cache_dir" in data:
            self.cache_dir = Path(data["cache_dir"]).expanduser()
        if "tools_dir" in data:
            self.tools_dir = Path(data["tools_dir"]).expanduser()

    def _apply_env_vars(self) -> None:
        """Apply environment variable overrides."""
        env_mappings: dict[str, tuple[Any, str]] = {
            "TEXT2PATH_PRECISION": (self.conversion, "precision"),
            "TEXT2PATH_PRESERVE_STYLES": (self.conversion, "preserve_styles"),
            "TEXT2PATH_OUTPUT_SUFFIX": (self.conversion, "output_suffix"),
            "TEXT2PATH_SYSTEM_FONTS_ONLY": (self.fonts, "system_only"),
            "TEXT2PATH_REMOTE_FONTS": (self.fonts, "remote"),
            "TEXT2PATH_IGNORE_SIZE_LIMITS": (self.security, "ignore_size_limits"),
            "TEXT2PATH_MAX_FILE_SIZE_MB": (self.security, "max_file_size_mb"),
            "TEXT2PATH_MAX_DECOMPRESSED_SIZE_MB": (
                self.security,
                "max_decompressed_size_mb",
            ),
            "TEXT2PATH_LOG_LEVEL": (self, "log_level"),
            "TEXT2PATH_CACHE_DIR": (self, "cache_dir"),
            "TEXT2PATH_TOOLS_DIR": (self, "tools_dir"),
        }

        for env_var, (obj, attr) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                current = getattr(obj, attr)
                if isinstance(current, bool):
                    setattr(obj, attr, value.lower() in ("1", "true", "yes"))
                elif isinstance(current, int):
                    setattr(obj, attr, int(value))
                elif isinstance(current, Path):
                    setattr(obj, attr, Path(value).expanduser())
                else:
                    setattr(obj, attr, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "fonts": {
                "system_only": self.fonts.system_only,
                "remote": self.fonts.remote,
                "custom_dirs": [str(p) for p in self.fonts.custom_dirs],
                "replacements": self.fonts.replacements,
                "fallbacks": self.fonts.fallbacks,
            },
            "defaults": {
                "precision": self.conversion.precision,
                "preserve_styles": self.conversion.preserve_styles,
                "output_suffix": self.conversion.output_suffix,
            },
            "security": {
                "ignore_size_limits": self.security.ignore_size_limits,
                "max_file_size_mb": self.security.max_file_size_mb,
                "max_decompressed_size_mb": self.security.max_decompressed_size_mb,
            },
            "log_level": self.log_level,
            "cache_dir": str(self.cache_dir),
            "tools_dir": str(self.tools_dir),
        }


# Default font replacements (proprietary -> libre equivalents)
DEFAULT_FONT_REPLACEMENTS: dict[str, str] = {
    "Arial": "Liberation Sans",
    "Helvetica": "Liberation Sans",
    "Helvetica Neue": "Liberation Sans",
    "Times New Roman": "Liberation Serif",
    "Times": "Liberation Serif",
    "Courier New": "Liberation Mono",
    "Courier": "Liberation Mono",
    "Georgia": "DejaVu Serif",
    "Verdana": "DejaVu Sans",
    "Tahoma": "DejaVu Sans",
    "Trebuchet MS": "DejaVu Sans",
    "Impact": "Liberation Sans",
    "Comic Sans MS": "DejaVu Sans",
}

# Default fallback chains
DEFAULT_FALLBACKS: dict[str, list[str]] = {
    "sans-serif": ["Liberation Sans", "DejaVu Sans", "Noto Sans", "FreeSans"],
    "serif": ["Liberation Serif", "DejaVu Serif", "Noto Serif", "FreeSerif"],
    "monospace": ["Liberation Mono", "DejaVu Sans Mono", "Noto Sans Mono", "FreeMono"],
    "cursive": ["DejaVu Sans", "Noto Sans", "Liberation Sans"],
    "fantasy": ["DejaVu Sans", "Liberation Sans", "Noto Sans"],
}
