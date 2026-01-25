"""text2path: Convert SVG text elements to path outlines (legacy package).

DEPRECATED: This package is deprecated. Use svg_text2path instead.

This is the legacy monolithic implementation. For new projects, prefer
using the `svg_text2path` package which provides a cleaner, modular API.

Example (legacy CLI-style):
    >>> from text2path import convert_svg_text_to_paths
    >>> convert_svg_text_to_paths("input.svg", "output.svg")

Example (using FontCache):
    >>> from text2path import FontCache
    >>> cache = FontCache()
    >>> cache.prewarm()
    >>> font, data, idx = cache.get_font("Arial", weight=400)

For dependency verification:
    >>> from text2path import verify_dependencies, print_dependency_report
    >>> report = verify_dependencies()
    >>> if not report.all_required_ok:
    ...     print_dependency_report(report)
"""

from __future__ import annotations

import warnings

warnings.warn(
    "The 'text2path' package is deprecated and will be removed in v1.0. "
    "Use 'svg_text2path' instead: from svg_text2path import Text2PathConverter",
    DeprecationWarning,
    stacklevel=2,
)

# Import from main module - lazy imports to speed up module load time
from text2path.main import (  # noqa: E402
    FontCache,
    MissingFontError,
    convert_svg_text_to_paths,
    setup_logging,
    text_to_path_rust_style,
)

# Import dependency verification from svg_text2path
try:
    from svg_text2path.tools.dependencies import (  # noqa: F401
        DependencyInfo,
        DependencyReport,
        DependencyStatus,
        DependencyType,
        format_dependency_report,
        print_dependency_report,
    )
    from svg_text2path.tools.dependencies import (
        verify_all_dependencies as verify_dependencies,
    )

    _HAS_DEPENDENCY_CHECKER = True
except ImportError:
    _HAS_DEPENDENCY_CHECKER = False
    DependencyInfo = None  # type: ignore[misc, assignment]
    DependencyReport = None  # type: ignore[misc, assignment]
    DependencyStatus = None  # type: ignore[misc, assignment]
    DependencyType = None  # type: ignore[misc, assignment]
    format_dependency_report = None  # type: ignore[misc, assignment]

    def verify_dependencies():  # type: ignore[no-redef]
        """Stub: svg_text2path package not available."""
        raise ImportError(
            "Dependency verification requires svg_text2path package. "
            "Install with: pip install svg-text2path"
        )

    def print_dependency_report(*args, **kwargs):  # type: ignore[no-redef]
        """Stub: svg_text2path package not available."""
        del args, kwargs  # unused
        raise ImportError(
            "Dependency verification requires svg_text2path package. "
            "Install with: pip install svg-text2path"
        )


__version__ = "0.3.0"
__author__ = "Emasoft"
__email__ = "713559+Emasoft@users.noreply.github.com"

__all__ = [
    # Core conversion
    "convert_svg_text_to_paths",
    "text_to_path_rust_style",
    # Font handling
    "FontCache",
    "MissingFontError",
    # Logging
    "setup_logging",
    # Dependency verification
    "verify_dependencies",
    "print_dependency_report",
    # Metadata
    "__version__",
]

# Conditionally add dependency types to __all__ if available
if _HAS_DEPENDENCY_CHECKER:
    __all__.extend(
        [
            "DependencyInfo",
            "DependencyReport",
            "DependencyStatus",
            "DependencyType",
            "format_dependency_report",
        ]
    )
