"""CLI commands for svg-text2path."""

from svg_text2path.cli.commands.batch import batch
from svg_text2path.cli.commands.compare import compare
from svg_text2path.cli.commands.convert import convert
from svg_text2path.cli.commands.fonts import fonts

__all__ = ["convert", "batch", "fonts", "compare"]
