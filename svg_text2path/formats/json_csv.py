"""JSON and CSV escaped SVG input handler.

Handles SVG content escaped in JSON strings or CSV cells.
"""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import register_namespace as _register_namespace

import defusedxml.ElementTree as ET

from svg_text2path.exceptions import SVGParseError
from svg_text2path.formats.base import FormatHandler, InputFormat

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element, ElementTree


class JSONHandler(FormatHandler):
    """Handler for JSON with escaped SVG content."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.JSON_ESCAPED]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is JSON with SVG content
        """
        if not isinstance(source, str):
            return False

        content = source.strip()

        # Must start with JSON markers
        if not (content.startswith("{") or content.startswith("[")):
            return False

        # Check for SVG content (escaped or unicode-escaped)
        lower = content.lower()
        return "<svg" in lower or "\\u003csvg" in lower or "\\u003Csvg" in content

    def parse(self, source: str) -> ElementTree:
        """Parse JSON and extract SVG content.

        Searches JSON values for SVG strings and returns the first one.

        Args:
            source: JSON string

        Returns:
            ElementTree containing the SVG

        Raises:
            SVGParseError: If no SVG found or parsing fails
        """
        svg_content = self._extract_svg_from_json(source)
        if not svg_content:
            raise SVGParseError("No SVG content found in JSON")

        try:
            root = ET.fromstring(svg_content)
            return cast(ElementTree, ET.ElementTree(root))  # type: ignore[reportAttributeAccessIssue]
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG from JSON: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Parse JSON and return SVG element."""
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree to JSON with SVG.

        Args:
            tree: ElementTree to serialize
            target: Original JSON structure (optional)

        Returns:
            JSON string containing SVG
        """
        self._register_namespaces()

        # Serialize SVG
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        svg_string = buffer.getvalue()

        if target:
            # Try to update first SVG value in original JSON
            return self._update_json_svg(target, svg_string)

        # Return simple JSON wrapper
        return json.dumps({"svg": svg_string})

    def _extract_svg_from_json(self, json_str: str) -> str | None:
        """Extract first SVG string from JSON.

        Handles nested structures and escaped content.

        Args:
            json_str: JSON string

        Returns:
            SVG string or None
        """
        try:
            data = json.loads(json_str)
            return self._find_svg_in_value(data)
        except json.JSONDecodeError:
            # Try regex fallback for malformed JSON
            return self._extract_svg_regex(json_str)

    def _find_svg_in_value(self, value: Any) -> str | None:
        """Recursively search for SVG in JSON value.

        Args:
            value: JSON value (dict, list, str, etc.)

        Returns:
            First SVG string found or None
        """
        if isinstance(value, str):
            if "<svg" in value.lower():
                return value

        elif isinstance(value, dict):
            for v in value.values():
                result = self._find_svg_in_value(v)
                if result:
                    return result

        elif isinstance(value, list):
            for item in value:
                result = self._find_svg_in_value(item)
                if result:
                    return result

        return None

    def _extract_svg_regex(self, json_str: str) -> str | None:
        """Extract SVG using regex (fallback for malformed JSON).

        Args:
            json_str: JSON-like string

        Returns:
            SVG string or None
        """
        # Look for SVG in JSON string values
        pattern = re.compile(
            r'"([^"]*<svg[^"]*</svg>[^"]*)"',
            re.IGNORECASE | re.DOTALL,
        )

        match = pattern.search(json_str)
        if match:
            # Unescape JSON string
            svg_escaped = match.group(1)
            return svg_escaped.encode().decode("unicode_escape")

        return None

    def _update_json_svg(self, json_str: str, new_svg: str) -> str:
        """Update first SVG in JSON structure.

        Args:
            json_str: Original JSON
            new_svg: New SVG string

        Returns:
            Updated JSON string
        """
        try:
            data = json.loads(json_str)
            updated = self._replace_svg_in_value(data, new_svg)
            return json.dumps(updated, indent=2)
        except json.JSONDecodeError:
            # Return simple wrapper if original is invalid
            return json.dumps({"svg": new_svg})

    def _replace_svg_in_value(self, value: Any, new_svg: str) -> Any:
        """Replace first SVG in JSON value.

        Args:
            value: JSON value
            new_svg: New SVG string

        Returns:
            Updated value
        """
        if isinstance(value, str) and "<svg" in value.lower():
            return new_svg

        if isinstance(value, dict):
            result = {}
            replaced = False
            for k, v in value.items():
                if not replaced:
                    new_v = self._replace_svg_in_value(v, new_svg)
                    if new_v != v:
                        replaced = True
                    result[k] = new_v
                else:
                    result[k] = v
            return result

        if isinstance(value, list):
            list_result: list[Any] = []
            replaced = False
            for item in value:
                if not replaced:
                    new_item = self._replace_svg_in_value(item, new_svg)
                    if new_item != item:
                        replaced = True
                    list_result.append(new_item)
                else:
                    list_result.append(item)
            return list_result

        return value

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)


class CSVHandler(FormatHandler):
    """Handler for CSV with SVG content in cells."""

    @property
    def supported_formats(self) -> list[InputFormat]:
        """Return list of formats this handler supports."""
        return [InputFormat.CSV_ESCAPED]

    def can_handle(self, source: Any) -> bool:
        """Check if this handler can process the given source.

        Args:
            source: Input source

        Returns:
            True if source is CSV with SVG content
        """
        if not isinstance(source, str):
            return False

        # Check for SVG in content
        if "<svg" not in source.lower():
            return False

        # Basic CSV check - has commas or tabs as delimiters
        lines = source.strip().split("\n")
        if len(lines) < 1:
            return False

        # Check if first line looks like CSV
        first_line = lines[0]
        return "," in first_line or "\t" in first_line

    def parse(self, source: str) -> ElementTree:
        """Parse CSV and extract first SVG content.

        Args:
            source: CSV string

        Returns:
            ElementTree containing the SVG

        Raises:
            SVGParseError: If no SVG found
        """
        svg_content = self._extract_svg_from_csv(source)
        if not svg_content:
            raise SVGParseError("No SVG content found in CSV")

        try:
            root = ET.fromstring(svg_content)
            return cast(ElementTree, ET.ElementTree(root))  # type: ignore[reportAttributeAccessIssue]
        except ET.ParseError as e:
            raise SVGParseError(f"Failed to parse SVG from CSV: {e}") from e

    def parse_element(self, source: str) -> Element:
        """Parse CSV and return SVG element."""
        tree = self.parse(source)
        root = tree.getroot()
        if root is None:
            raise SVGParseError("Parsed SVG has no root element")
        return root

    def serialize(self, tree: ElementTree, target: str | None = None) -> str:
        """Serialize ElementTree to CSV with SVG.

        Args:
            tree: ElementTree to serialize
            target: Original CSV structure (optional)

        Returns:
            CSV string containing SVG
        """
        self._register_namespaces()

        # Serialize SVG
        buffer = StringIO()
        tree.write(buffer, encoding="unicode")
        svg_string = buffer.getvalue()

        if target:
            return self._update_csv_svg(target, svg_string)

        # Return simple CSV with SVG
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["svg"])
        writer.writerow([svg_string])
        return output.getvalue()

    def _extract_svg_from_csv(self, csv_str: str) -> str | None:
        """Extract first SVG from CSV cells.

        Args:
            csv_str: CSV string

        Returns:
            SVG string or None
        """
        try:
            reader = csv.reader(StringIO(csv_str))
            for row in reader:
                for cell in row:
                    if "<svg" in cell.lower():
                        return cell
        except csv.Error:
            pass

        return None

    def _update_csv_svg(self, csv_str: str, new_svg: str) -> str:
        """Update first SVG in CSV.

        Args:
            csv_str: Original CSV
            new_svg: New SVG string

        Returns:
            Updated CSV string
        """
        rows: list[list[str]] = []
        replaced = False

        try:
            reader = csv.reader(StringIO(csv_str))
            for row in reader:
                new_row = []
                for cell in row:
                    if not replaced and "<svg" in cell.lower():
                        new_row.append(new_svg)
                        replaced = True
                    else:
                        new_row.append(cell)
                rows.append(new_row)
        except csv.Error:
            return csv_str

        output = StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()

    def _register_namespaces(self) -> None:
        """Register common SVG namespaces."""
        namespaces = {
            "": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        for prefix, uri in namespaces.items():
            _register_namespace(prefix, uri)
