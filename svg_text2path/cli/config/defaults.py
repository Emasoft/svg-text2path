"""Default configuration values."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Default configuration dictionary
DEFAULT_CONFIG: dict[str, Any] = {
    "fonts": {
        "system_only": False,
        "remote": True,
        "custom_dirs": [],
        "replacements": {
            "Arial": "Liberation Sans",
            "Helvetica": "Liberation Sans",
            "Times New Roman": "Liberation Serif",
            "Courier New": "Liberation Mono",
        },
        "fallbacks": {
            "sans-serif": ["Liberation Sans", "DejaVu Sans", "Noto Sans"],
            "serif": ["Liberation Serif", "DejaVu Serif", "Noto Serif"],
            "monospace": ["Liberation Mono", "DejaVu Sans Mono", "Noto Sans Mono"],
        },
    },
    "conversion": {
        "precision": 6,
        "preserve_styles": False,
        "output_suffix": "_text2path",
    },
}


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Returns:
        Path to default config file (~/.text2path/config.yaml)
    """
    return Path.home() / ".text2path" / "config.yaml"


def get_project_config_path() -> Path | None:
    """Get project-local config file if it exists.

    Returns:
        Path to project config or None
    """
    local_path = Path("text2path.yaml")
    if local_path.exists():
        return local_path

    local_path = Path(".text2path.yaml")
    if local_path.exists():
        return local_path

    return None
