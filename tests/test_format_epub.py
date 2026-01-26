"""Unit tests for svg_text2path.formats.epub EpubHandler.

Coverage: 8 tests covering EpubHandler detection, parsing, serialization,
and multi-SVG extraction from ePub files.

Tests use real ZIP archive creation with minimal ePub structure (mimetype,
container.xml, content.opf, and XHTML with embedded SVG).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from svg_text2path.formats.base import InputFormat
from svg_text2path.formats.epub import EpubHandler

# Minimal valid SVG for testing
SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<rect x="10" y="10" width="80" height="80" fill="blue"/></svg>'
)

SAMPLE_SVG_2 = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">'
    '<circle cx="25" cy="25" r="20" fill="red"/></svg>'
)


def create_minimal_epub(path: Path, xhtml_content: str) -> None:
    """Create a minimal valid ePub file with the given XHTML content.

    Creates ePub structure:
    - mimetype (uncompressed, first entry)
    - META-INF/container.xml
    - OEBPS/content.opf
    - OEBPS/chapter.xhtml (with provided content)
    """
    mimetype = b"application/epub+zip"

    container_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = b"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">test-epub</dc:identifier>
    <dc:title>Test ePub</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>"""

    with zipfile.ZipFile(path, "w") as epub:
        # mimetype MUST be first and uncompressed per ePub spec
        epub.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OEBPS/content.opf", content_opf)
        epub.writestr("OEBPS/chapter.xhtml", xhtml_content.encode("utf-8"))


def create_multi_svg_epub(path: Path, svg1: str, svg2: str) -> None:
    """Create ePub with multiple SVGs in XHTML content."""
    xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Multi-SVG Test</title></head>
<body>
<h1>First SVG</h1>
{svg1}
<h1>Second SVG</h1>
{svg2}
</body>
</html>"""
    create_minimal_epub(path, xhtml)


class TestEpubHandler:
    """Test EpubHandler: detect, parse, and serialize ePub files with SVG."""

    def test_can_handle_epub_file(self, tmp_path: Path) -> None:
        """EpubHandler returns True for .epub file that exists."""
        # Create minimal ePub with SVG content
        xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>{SAMPLE_SVG}</body>
</html>"""
        epub_file = tmp_path / "test.epub"
        create_minimal_epub(epub_file, xhtml)

        handler = EpubHandler()

        # Path object
        assert handler.can_handle(epub_file) is True

        # String path
        assert handler.can_handle(str(epub_file)) is True

    def test_can_handle_non_epub(self, tmp_path: Path) -> None:
        """EpubHandler returns False for non-epub files and inputs."""
        handler = EpubHandler()

        # Wrong extension
        svg_file = tmp_path / "test.svg"
        svg_file.write_text(SAMPLE_SVG)
        assert handler.can_handle(svg_file) is False

        # Non-existent epub
        assert handler.can_handle(tmp_path / "nonexistent.epub") is False

        # XML string content (not a file path)
        assert handler.can_handle(SAMPLE_SVG) is False

        # Plain string
        assert handler.can_handle("not an epub") is False

        # None and other types
        assert handler.can_handle(None) is False
        assert handler.can_handle(12345) is False

    def test_parse_extracts_svg_from_xhtml(self, tmp_path: Path) -> None:
        """EpubHandler.parse extracts SVG element from XHTML content in ePub."""
        xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>SVG Test</title></head>
<body>
<p>Some text before</p>
{SAMPLE_SVG}
<p>Some text after</p>
</body>
</html>"""
        epub_file = tmp_path / "test_extract.epub"
        create_minimal_epub(epub_file, xhtml)

        handler = EpubHandler()
        tree = handler.parse(epub_file)

        root = tree.getroot()
        assert root is not None
        # Root should be svg element
        assert root.tag.endswith("svg") or root.tag == "{http://www.w3.org/2000/svg}svg"
        # Verify attributes preserved
        assert root.get("width") == "100"
        assert root.get("height") == "100"
        # Verify child element exists
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")
        if rect is None:
            rect = root.find(".//rect")
        assert rect is not None

    def test_parse_returns_element_tree(self, tmp_path: Path) -> None:
        """EpubHandler.parse returns valid ElementTree object."""
        from xml.etree.ElementTree import ElementTree

        xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>{SAMPLE_SVG}</body>
</html>"""
        epub_file = tmp_path / "test_tree.epub"
        create_minimal_epub(epub_file, xhtml)

        handler = EpubHandler()
        result = handler.parse(epub_file)

        # Verify returns ElementTree
        assert isinstance(result, ElementTree)

        # Verify root is accessible
        root = result.getroot()
        assert root is not None
        assert root.tag.endswith("svg") or "svg" in root.tag

    def test_get_all_svgs_returns_all(self, tmp_path: Path) -> None:
        """EpubHandler extracts multiple SVGs from XHTML content."""
        epub_file = tmp_path / "multi_svg.epub"
        create_multi_svg_epub(epub_file, SAMPLE_SVG, SAMPLE_SVG_2)

        handler = EpubHandler()
        handler.parse(epub_file)

        # Check count
        svg_count = handler.get_svg_count()
        assert svg_count == 2, f"Expected 2 SVGs, got {svg_count}"

        # Get first SVG
        svg1 = handler.get_svg_by_index(0)
        assert svg1 is not None
        root1 = svg1.getroot()
        assert root1.get("width") == "100"

        # Get second SVG
        svg2 = handler.get_svg_by_index(1)
        assert svg2 is not None
        root2 = svg2.getroot()
        assert root2.get("width") == "50"

        # Out of range returns None
        assert handler.get_svg_by_index(5) is None
        assert handler.get_svg_by_index(-1) is None

    def test_serialize_creates_valid_epub(self, tmp_path: Path) -> None:
        """EpubHandler.serialize creates valid ePub with mimetype first."""
        xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>{SAMPLE_SVG}</body>
</html>"""
        epub_file = tmp_path / "input.epub"
        create_minimal_epub(epub_file, xhtml)

        handler = EpubHandler()
        tree = handler.parse(epub_file)

        # Modify the SVG (simulate text2path conversion)
        root = tree.getroot()
        root.set("data-converted", "true")

        # Serialize to new ePub
        output_file = tmp_path / "output.epub"
        result_path = handler.serialize(tree, output_file)

        # Verify output path
        assert result_path == output_file
        assert output_file.exists()

        # Verify output is valid ZIP
        with zipfile.ZipFile(output_file, "r") as epub:
            namelist = epub.namelist()

            # mimetype MUST be first per ePub spec
            assert namelist[0] == "mimetype"

            # Verify mimetype is uncompressed
            info = epub.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED

            # Verify mimetype content
            assert epub.read("mimetype") == b"application/epub+zip"

            # Verify other required files exist
            assert "META-INF/container.xml" in namelist
            assert "OEBPS/content.opf" in namelist
            assert "OEBPS/chapter.xhtml" in namelist

    def test_supported_formats_includes_epub(self) -> None:
        """EpubHandler.supported_formats includes InputFormat.EPUB."""
        handler = EpubHandler()
        supported = handler.supported_formats

        assert isinstance(supported, list)
        assert len(supported) >= 1
        assert InputFormat.EPUB in supported

    def test_parse_nonexistent_raises(self, tmp_path: Path) -> None:
        """EpubHandler.parse raises FileNotFoundError for missing file."""
        handler = EpubHandler()
        nonexistent = tmp_path / "does_not_exist.epub"

        with pytest.raises(FileNotFoundError) as exc_info:
            handler.parse(nonexistent)

        assert "not found" in str(exc_info.value).lower()
