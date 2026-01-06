"""CLI configuration handling."""

from svg_text2path.cli.config.defaults import DEFAULT_CONFIG, get_default_config_path
from svg_text2path.cli.config.yaml_config import load_yaml_config, save_yaml_config

__all__ = [
    "load_yaml_config",
    "save_yaml_config",
    "DEFAULT_CONFIG",
    "get_default_config_path",
]
