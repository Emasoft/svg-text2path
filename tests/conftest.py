"""Pytest configuration and shared fixtures for svg-text2path tests."""

from collections.abc import Generator
from pathlib import Path

import pytest

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def samples_dir() -> Path:
    """Return the samples directory containing test SVGs."""
    return SAMPLES_DIR


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def temp_svg(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary SVG file for testing."""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
</svg>"""
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    yield svg_path


@pytest.fixture
def simple_svg_content() -> str:
    """Return a simple SVG string with text element."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Test</text>
</svg>"""


@pytest.fixture
def tspan_svg_content() -> str:
    """Return SVG with tspan elements."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" viewBox="0 0 300 100">
  <text x="10" y="50" font-family="Arial" font-size="24">
    <tspan>Hello</tspan>
    <tspan x="10" dy="30">World</tspan>
  </text>
</svg>"""


@pytest.fixture
def rtl_svg_content() -> str:
    """Return SVG with RTL (Arabic) text."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" '
        'viewBox="0 0 300 100">\n'
        '  <text x="290" y="50" font-family="Noto Sans Arabic" font-size="24" '
        'direction="rtl">مرحبا</text>\n'
        "</svg>"
    )


@pytest.fixture
def textpath_svg_content() -> str:
    """Return SVG with textPath element."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="300" height="200" viewBox="0 0 300 200">\n'
        "  <defs>\n"
        '    <path id="curve" d="M 50,150 Q 150,50 250,150"/>\n'
        "  </defs>\n"
        '  <text font-family="Arial" font-size="18">\n'
        '    <textPath xlink:href="#curve">Text on a curved path</textPath>\n'
        "  </text>\n"
        "</svg>"
    )


@pytest.fixture
def transform_svg_content() -> str:
    """Return SVG with transform attribute on text."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" '
        'viewBox="0 0 200 200">\n'
        '  <text x="50" y="50" font-family="Arial" font-size="24" '
        'transform="rotate(45, 50, 50)">Rotated</text>\n'
        "</svg>"
    )


@pytest.fixture
def no_text_svg_content() -> str:
    """Return SVG without any text elements."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
  <circle cx="50" cy="50" r="30" fill="red"/>
</svg>"""


@pytest.fixture
def malformed_svg_content() -> str:
    """Return malformed SVG for error testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="50">Unclosed text
</svg>"""


# Skip markers for slow or external-dependent tests
slow = pytest.mark.slow


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "visual: marks visual comparison tests (require Inkscape + sbb-compare)",
    )


requires_fonts = pytest.mark.skipif(
    not Path("/System/Library/Fonts").exists()
    and not Path("/usr/share/fonts").exists(),
    reason="System fonts not available",
)
requires_network = pytest.mark.skipif(True, reason="Network tests disabled by default")
