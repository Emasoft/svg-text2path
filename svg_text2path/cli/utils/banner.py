"""Banner display for svg-text2path CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from svg_text2path import __version__

# ANSI logo - embedded to avoid file I/O issues in installed packages
# fmt: off
LOGO = (
    "                   _____________   ____________                     \n"
    "                  ╱   _____╱╲   ╲ ╱   ╱  _____╱                     \n"
    "          ______  ╲_____  ╲  ╲   Y   ╱   ╲  ___   ______            \n"
    "         ╱_____╱  ╱        ╲  ╲     ╱╲    ╲_╲  ╲ ╱_____╱            \n"
    "                 ╱_______  ╱   ╲___╱  ╲______  ╱                    \n"
    "                         ╲╱                  ╲╱                     \n"
    "___________              __  __________________         __  .__     \n"
    "╲__    ___╱___ ___  ____╱  │_╲_____  ╲______   ╲_____ _╱  │_│  │__  \n"
    "  │    │_╱ __ ╲╲  ╲╱  ╱╲   __╲╱  ____╱│     ___╱╲__  ╲╲   __╲  │  ╲ \n"
    "  │    │╲  ___╱ >    <  │  │ ╱       ╲│    │     ╱ __ ╲│  │ │   Y  ╲\n"
    "  │____│ ╲___  >__╱╲_ ╲ │__│ ╲_______ ╲____│    (____  ╱__│ │___│  ╱\n"
    "             ╲╱      ╲╱              ╲╱              ╲╱          ╲╱ "
)
# fmt: on

GITHUB_URL = "https://github.com/Emasoft/svg-text2path"


def print_banner(console: Console | None = None, force: bool = False) -> None:
    """Print the svg-text2path banner with version and GitHub link.

    Args:
        console: Rich console to use. If None, creates a new one.
        force: If True, print even if output is not a TTY.
    """
    if console is None:
        console = Console()

    # Skip banner if not a TTY (unless forced)
    if not force and not console.is_terminal:
        return

    # Print logo in cyan
    console.print(Text(LOGO, style="cyan"))

    # Print version and GitHub link (centered for 68-char logo)
    version_line = f"         [bold]v{__version__}[/bold]  •  [link={GITHUB_URL}]{GITHUB_URL}[/link]"  # noqa: E501
    console.print(version_line, highlight=False)
    console.print()  # Empty line after banner


def get_version_string() -> str:
    """Get formatted version string."""
    return f"svg-text2path v{__version__}"
