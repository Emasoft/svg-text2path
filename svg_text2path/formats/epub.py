"""ePub ebook input handler for SVG content.

Extracts and converts SVG elements from ePub ebook files.
ePub files are ZIP archives containing XHTML files with embedded SVG.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import Element, ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace
from xml.etree.ElementTree import tostring as et_tostring

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat
from svg_text2path.svg.parser import SVG_NS, XLINK_NS

if TYPE_CHECKING:
    pass  # ElementTree imported above for cast()

# Security limits for zip bomb and file size protection
MAX_EPUB_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100MB max uncompressed
MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024  # 50MB max per file


# Namespaces used in XHTML/ePub content (SVG_NS, XLINK_NS imported from parser)
XHTML_NS = "http://www.w3.org/1999/xhtml"


class EpubHandler(FormatHandler):
    """Handler for ePub ebook files containing SVG content.

    This handler processes ePub files (which are ZIP archives) to extract and convert
    SVG elements embedded in XHTML documents. The typical workflow is:

    1. Parse: Read ePub ZIP → Find XHTML/HTML files → Extract SVG elements
    2. Convert: Use text2path converter on extracted SVG content
    3. Serialize: Write back to new ePub ZIP with replaced SVG content

    The handler maintains mappings of SVG locations within the ePub structure to
    enable proper serialization back to the original document locations.

    Attributes:
        _svg_map: Mapping of (file_path, svg_index) tuples to original SVG
            content strings. Used to track SVG locations for serialization.
        _original_epub_path: Path to the source ePub file, needed for serialization.
        _svg_elements: List of (file_path, svg_index, Element) tuples containing all
            extracted SVG elements in discovery order.
    """

    def __init__(self) -> None:
        """Initialize handler with empty SVG mapping.

        Creates empty internal structures for tracking SVG elements discovered
        during parsing. No arguments required.

        Attributes initialized:
            _svg_map: Empty dictionary for SVG content mapping
            _original_epub_path: None (set during parse)
            _svg_elements: Empty list for SVG element storage
        """
        super().__init__()  # Initialize base class config
        # Mapping: (file_in_epub, svg_index) -> svg_content_string
        self._svg_map: dict[tuple[str, int], str] = {}
        # Store original ePub for serialization
        self._original_epub_path: Path | None = None
        # Store all SVG elements found during parse
        self._svg_elements: list[tuple[str, int, Element]] = []

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports.

        Returns:
            list[InputFormat]: Single-element list containing InputFormat.EPUB
        """
        return [InputFormat.EPUB]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Validates whether the source is an ePub file by checking:
        - File extension is .epub (case-insensitive)
        - File exists on filesystem
        - Source is not XML/SVG markup (starts with '<')

        Args:
            source (Any): Input source to validate. Can be:
                - Path object pointing to .epub file
                - str containing file path to .epub file
                - Any other type (will return False)

        Returns:
            bool: True if source is a valid, existing ePub file path.
                False if source is not an ePub file or doesn't exist.
        """
        if isinstance(source, Path):
            return source.suffix.lower() == ".epub" and source.exists()

        if isinstance(source, str):
            # Check if it looks like a path to an ePub
            if source.startswith("<"):
                return False
            path = Path(source)
            if path.exists() and path.suffix.lower() == ".epub":
                return True

        return False

    def parse(self, source: str | Path) -> ElementTree:
        """Parse ePub file and extract SVG content.

        Opens the ePub as a ZIP archive, finds all XHTML/HTML files,
        extracts SVG elements from each, and returns the first SVG
        as an ElementTree. Stores mapping of all SVGs for serialization.

        The parsing workflow:
        1. Open ePub ZIP archive
        2. Find all content files (.xhtml, .html, .htm, .xml, .svg)
        3. Extract SVG elements from each XHTML file
        4. Store all SVG elements with location mappings
        5. Return first SVG as ElementTree with proper xmlns namespace

        Args:
            source (str | Path): File path to ePub file. Can be string path
                or Path object.

        Returns:
            ElementTree: ElementTree containing the first SVG element found.
                The SVG root will have xmlns="http://www.w3.org/2000/svg" if
                not already present.

        Raises:
            FileNotFoundError: If the ePub file doesn't exist at the given path.
            SVGParseError: If parsing fails (invalid ZIP, no SVG found, or
                XHTML parsing error).
        """
        path = Path(source) if isinstance(source, str) else source

        if not path.exists():
            raise FileNotFoundError(f"ePub file not found: {path}")

        self._original_epub_path = path
        self._svg_map.clear()
        self._svg_elements.clear()

        try:
            with zipfile.ZipFile(path, "r") as epub:
                # Check total uncompressed size (zip bomb protection)
                # Respect config.security.ignore_size_limits if set
                should_check_size = True
                max_decompressed = MAX_EPUB_UNCOMPRESSED_SIZE
                if self.config and self.config.security:
                    if self.config.security.ignore_size_limits:
                        should_check_size = False
                    elif self.config.security.max_decompressed_size_mb:
                        max_decompressed = (
                            self.config.security.max_decompressed_size_mb * 1024 * 1024
                        )

                if should_check_size:
                    total_uncompressed = sum(info.file_size for info in epub.infolist())
                    if total_uncompressed > max_decompressed:
                        msg = (
                            f"ePub too large when uncompressed: "
                            f"{total_uncompressed} bytes (max: {max_decompressed})"
                        )
                        raise SVGParseError(msg)

                # Find all XHTML/HTML content files
                content_files = self._find_content_files(epub)

                # Extract SVGs from each content file
                for content_path in content_files:
                    self._extract_svgs_from_xhtml(epub, content_path)

            if not self._svg_elements:
                raise SVGParseError(
                    "No SVG elements found in ePub",
                    source=str(path),
                )

            # Return first SVG as ElementTree
            _first_file, _first_idx, first_svg = self._svg_elements[0]

            # Create a proper SVG root with namespaces if needed
            if not first_svg.get("xmlns"):
                first_svg.set("xmlns", SVG_NS)

            return cast(ElementTree, ElementTree(first_svg))

        except zipfile.BadZipFile as e:
            raise SVGParseError(f"Invalid ePub/ZIP file: {e}") from e
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse XHTML content: {e}") from e
        except Exception as e:
            if isinstance(e, (SVGParseError, FileNotFoundError)):
                raise
            raise SVGParseError(f"Error reading ePub file: {e}") from e

    def serialize(self, tree: ElementTree, target: str | Path) -> Path:
        """Write ElementTree back to ePub file with replaced SVG content.

        Creates a new ePub archive, replacing SVG content in XHTML files
        while preserving all other ePub structure (mimetype, META-INF, etc.).

        The serialization workflow:
        1. Register XML namespaces (svg, xlink, xhtml) to avoid ns0: prefixes
        2. Convert ElementTree to SVG string
        3. Create new ZIP archive with original ePub structure
        4. Write mimetype first (uncompressed, as per ePub spec)
        5. Copy all files, replacing SVG in XHTML documents
        6. Preserve compression settings from original ePub

        Args:
            tree (ElementTree): ElementTree with converted SVG content (typically
                from text2path conversion). Should contain the replacement SVG.
            target (str | Path): Output ePub file path. Can be string or Path.

        Returns:
            Path: Absolute path to the written ePub file.

        Raises:
            SVGParseError: If serialization fails (no parsed ePub, invalid ZIP
                operation, or XHTML replacement error).
        """
        target_path = Path(target) if isinstance(target, str) else target

        if self._original_epub_path is None:
            raise SVGParseError("Cannot serialize: no ePub was parsed")

        # Register namespaces
        self._register_namespaces()

        # Get the new SVG content from the tree
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Tree has no root element")
        new_svg_content = et_tostring(root, encoding="unicode")

        try:
            with (
                zipfile.ZipFile(self._original_epub_path, "r") as src_epub,
                zipfile.ZipFile(target_path, "w") as dst_epub,
            ):
                # mimetype must be first and uncompressed
                if "mimetype" in src_epub.namelist():
                    mimetype_info = src_epub.getinfo("mimetype")
                    mimetype_info.compress_type = zipfile.ZIP_STORED
                    dst_epub.writestr(mimetype_info, src_epub.read("mimetype"))

                # Copy all other files, replacing SVGs in XHTML
                for item in src_epub.infolist():
                    if item.filename == "mimetype":
                        continue  # Already written

                    content = src_epub.read(item.filename)

                    # Check if this file contains SVGs we need to replace
                    if self._is_content_file(item.filename):
                        content = self._replace_svg_in_xhtml(
                            content,
                            item.filename,
                            new_svg_content,
                        )

                    dst_epub.writestr(item, content)

            return target_path

        except Exception as e:
            raise SVGParseError(f"Failed to serialize ePub: {e}") from e

    def get_svg_count(self) -> int:
        """Return number of SVG elements found in last parsed ePub.

        Returns:
            int: Total count of SVG elements discovered during the last parse()
                call. Returns 0 if no ePub has been parsed yet.
        """
        return len(self._svg_elements)

    def get_svg_by_index(self, index: int) -> ElementTree | None:
        """Get a specific SVG element by index.

        Retrieves an SVG element from the internal storage by its discovery
        order index. Useful for processing multiple SVGs from a single ePub.

        Args:
            index (int): Zero-based index of the SVG element to retrieve.
                Must be in range [0, get_svg_count()).

        Returns:
            ElementTree | None: ElementTree containing the SVG element at the
                given index, or None if index is out of range.
        """
        if 0 <= index < len(self._svg_elements):
            _, _, svg_elem = self._svg_elements[index]
            return cast(ElementTree, ElementTree(svg_elem))
        return None

    def _validate_zip_entry(self, name: str) -> None:
        """Validate ZIP entry path for security.

        Checks for path traversal attacks and other unsafe path patterns
        that could allow reading/writing files outside the intended directory.

        Args:
            name (str): The filename/path from the ZIP archive entry.

        Raises:
            SVGParseError: If the path contains unsafe patterns like:
                - Absolute paths starting with /
                - Parent directory traversal (..)
                - Windows-style paths starting with \\
        """
        if name.startswith("/") or ".." in name or name.startswith("\\"):
            raise SVGParseError(f"Unsafe path in ePub archive: {name}")

    def _find_content_files(self, epub: zipfile.ZipFile) -> list[str]:
        """Find all XHTML/HTML content files in the ePub.

        Scans the ePub ZIP archive for files that may contain SVG content:
        - XHTML/HTML documents (.xhtml, .html, .htm, .xml)
        - Standalone SVG files (.svg)

        Args:
            epub (zipfile.ZipFile): Open ZipFile object for the ePub archive.

        Returns:
            list[str]: List of file paths within the ZIP archive that may
                contain SVG content. Paths are relative to the ZIP root
                (e.g., "OEBPS/content.xhtml").
        """
        content_files: list[str] = []
        content_extensions = {".xhtml", ".html", ".htm", ".xml"}

        for name in epub.namelist():
            path = Path(name)
            if path.suffix.lower() in content_extensions:
                content_files.append(name)

        # Also check OPF manifest for SVG files directly in the ePub
        for name in epub.namelist():
            if name.endswith(".svg"):
                content_files.append(name)

        return content_files

    def _is_content_file(self, filename: str) -> bool:
        """Check if a file is an XHTML/HTML content file.

        Used during serialization to determine which files need SVG replacement.
        SVG files are excluded as they don't need replacement (they are the SVG).

        Args:
            filename (str): Path to file within ePub ZIP archive.

        Returns:
            bool: True if file is an XHTML/HTML document that may contain embedded
                SVG elements (.xhtml, .html, .htm, .xml). False otherwise.
        """
        path = Path(filename)
        return path.suffix.lower() in {".xhtml", ".html", ".htm", ".xml"}

    def _extract_svgs_from_xhtml(
        self,
        epub: zipfile.ZipFile,
        content_path: str,
    ) -> None:
        """Extract SVG elements from an XHTML file.

        Reads an XHTML/HTML file from the ePub archive, parses it, and extracts
        all SVG elements. Handles both:
        - Standalone .svg files (reads entire file as SVG)
        - SVG embedded in XHTML (searches for <svg> elements with various namespaces)

        SVG elements are searched with multiple namespace variants to handle
        different XHTML authoring approaches:
        - Namespaced: {http://www.w3.org/2000/svg}svg
        - Non-namespaced: svg
        - XHTML namespace: {http://www.w3.org/1999/xhtml}svg

        Silently skips files that cannot be parsed as XML.

        Args:
            epub (zipfile.ZipFile): Open ZipFile object for the ePub archive.
            content_path (str): Path to XHTML/HTML/SVG file within the ZIP archive.

        Returns:
            None: Updates internal _svg_map and _svg_elements with discovered SVGs.
        """
        try:
            # Validate path for security (path traversal protection)
            self._validate_zip_entry(content_path)

            # Check individual file size before reading
            # Respect config.security.ignore_size_limits if set
            should_check_file_size = True
            max_file_size = MAX_SINGLE_FILE_SIZE
            if self.config and self.config.security:
                if self.config.security.ignore_size_limits:
                    should_check_file_size = False
                elif self.config.security.max_file_size_mb:
                    max_file_size = self.config.security.max_file_size_mb * 1024 * 1024

            if should_check_file_size:
                info = epub.getinfo(content_path)
                if info.file_size > max_file_size:
                    msg = (
                        f"File too large in ePub: {content_path} "
                        f"({info.file_size} bytes, max: {max_file_size})"
                    )
                    raise SVGParseError(msg)

            content = epub.read(content_path).decode("utf-8")

            # Handle direct SVG files
            if content_path.endswith(".svg"):
                tree = cast(ElementTree, ET.parse(io.StringIO(content)))
                root = tree.getroot()
                if root is None:
                    raise SVGParseError(f"SVG file has no root element: {content_path}")
                svg_idx = len(self._svg_elements)
                self._svg_map[(content_path, svg_idx)] = content
                self._svg_elements.append((content_path, svg_idx, root))
                return

            # Parse XHTML
            tree = cast(ElementTree, ET.parse(io.StringIO(content)))
            root = tree.getroot()
            if root is None:
                raise SVGParseError(f"XHTML file has no root element: {content_path}")

            # Find all SVG elements (both namespaced and non-namespaced)
            svg_elements: list[Element] = []

            # Search for {http://www.w3.org/2000/svg}svg
            svg_elements.extend(root.findall(f".//{{{SVG_NS}}}svg"))

            # Search for svg without namespace (in case of non-namespaced XHTML)
            svg_elements.extend(root.findall(".//svg"))

            # Also search within XHTML namespace
            svg_elements.extend(root.findall(f".//{{{XHTML_NS}}}svg"))

            # Deduplicate while preserving order
            seen: set[int] = set()
            unique_svgs: list[Element] = []
            for svg in svg_elements:
                svg_id = id(svg)
                if svg_id not in seen:
                    seen.add(svg_id)
                    unique_svgs.append(svg)

            # Store each SVG
            for idx, svg in enumerate(unique_svgs):
                svg_content = et_tostring(svg, encoding="unicode")
                self._svg_map[(content_path, idx)] = svg_content
                self._svg_elements.append((content_path, idx, svg))

        except ET.ParseError:
            # Some content files may not be valid XML, skip them
            pass
        except Exception:
            # Skip files that can't be processed
            pass

    def _replace_svg_in_xhtml(
        self,
        content: bytes,
        filename: str,
        new_svg_content: str,
    ) -> bytes:
        """Replace first SVG in XHTML content with new content.

        Uses regex to find and replace SVG elements while preserving the
        surrounding XHTML structure. Only replaces the first SVG occurrence
        to match the parse() behavior (which returns the first SVG).

        If the file has no SVG mapping (no SVG was found during parse), or
        if replacement fails, returns original content unchanged.

        Args:
            content (bytes): Original XHTML content as UTF-8 encoded bytes.
            filename (str): Name of the file being processed (path within ePub ZIP).
            new_svg_content (str): New SVG content string to insert in place of
                the first SVG element.

        Returns:
            bytes: Updated XHTML content with first SVG replaced, or original
                content if no replacement needed/possible. Always UTF-8 encoded.
        """
        # Only replace if we have a mapping for this file
        if not any(f == filename for f, _ in self._svg_map):
            return content

        try:
            content_str = content.decode("utf-8")

            # Simple SVG replacement using regex
            # This preserves surrounding XHTML structure
            svg_pattern = re.compile(
                r"<svg[^>]*>.*?</svg>",
                re.DOTALL | re.IGNORECASE,
            )

            # Replace first SVG occurrence
            new_content = svg_pattern.sub(new_svg_content, content_str, count=1)

            return new_content.encode("utf-8")

        except Exception:
            # If replacement fails, return original content
            return content

    def _register_namespaces(self) -> None:
        """Register common namespaces to avoid ns0: prefixes.

        Registers XML namespaces globally before serialization to ensure clean
        output without auto-generated prefixes like "ns0:", "ns1:", etc.

        Registered namespaces:
        - "" (default): http://www.w3.org/2000/svg
        - "svg": http://www.w3.org/2000/svg
        - "xlink": http://www.w3.org/1999/xlink
        - "xhtml": http://www.w3.org/1999/xhtml

        Returns:
            None: Modifies global ElementTree namespace registry.
        """
        namespaces = {
            "": SVG_NS,
            "svg": SVG_NS,
            "xlink": XLINK_NS,
            "xhtml": XHTML_NS,
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
