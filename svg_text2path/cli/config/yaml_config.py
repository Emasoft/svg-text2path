"""YAML configuration file handling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from svg_text2path.config import Config, ConversionConfig, FontConfig


def load_yaml_config(path: Path) -> Config:
    """Load configuration from YAML file.

    Args:
        path: Path to YAML config file

    Returns:
        Config object
    """
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return _dict_to_config(data)


def save_yaml_config(config: Config, path: Path) -> None:
    """Save configuration to YAML file.

    Args:
        config: Config object to save
        path: Output path
    """
    data = _config_to_dict(config)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def _dict_to_config(data: dict[str, Any]) -> Config:
    """Convert dictionary to Config object."""
    fonts_data = data.get("fonts", {})
    conversion_data = data.get("conversion", data.get("defaults", {}))

    fonts = FontConfig(
        system_only=fonts_data.get("system_only", False),
        remote=fonts_data.get("remote", True),
        custom_dirs=[Path(p) for p in fonts_data.get("custom_dirs", [])],
        replacements=fonts_data.get("replacements", {}),
        fallbacks=fonts_data.get("fallbacks", {}),
    )

    conversion = ConversionConfig(
        precision=conversion_data.get("precision", 6),
        preserve_styles=conversion_data.get("preserve_styles", False),
        output_suffix=conversion_data.get("output_suffix", "_text2path"),
    )

    return Config(fonts=fonts, conversion=conversion)


def _config_to_dict(config: Config) -> dict[str, Any]:
    """Convert Config object to dictionary."""
    return {
        "fonts": {
            "system_only": config.fonts.system_only,
            "remote": config.fonts.remote,
            "custom_dirs": [str(p) for p in config.fonts.custom_dirs],
            "replacements": config.fonts.replacements,
            "fallbacks": config.fonts.fallbacks,
        },
        "conversion": {
            "precision": config.conversion.precision,
            "preserve_styles": config.conversion.preserve_styles,
            "output_suffix": config.conversion.output_suffix,
        },
    }
