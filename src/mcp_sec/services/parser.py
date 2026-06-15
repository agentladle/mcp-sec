"""
HTML → JSON report parsing service.
Uses edgartools to parse SEC HTML reports into page-split JSON.
Self-contained implementation with no dependency on external project code.
"""

import json
import re
import logging
from pathlib import Path

from bs4 import BeautifulSoup

from edgar.documents import parse_html
from edgar.documents.table_nodes import TableNode
from edgar.documents.nodes import (
    TextNode,
    HeadingNode,
    ParagraphNode,
    ListNode,
    ListItemNode,
)
from edgar.files.page_breaks import mark_page_breaks as mark_html_page_breaks

from mcp_sec.models import ParseResult

logger = logging.getLogger(__name__)

# Page break placeholder (plain text to avoid HTML comment parsing ambiguity)
PAGE_BREAK_PLACEHOLDER = "@@EDGAR_PAGE_BREAK@@"


class ReportParser:
    def parse(self, html_path: Path, json_path: Path) -> ParseResult:
        """
        Parse a single HTML report file into page-split JSON.
        Idempotent: skips if JSON already exists.

        Parsing flow:
        1. edgartools mark_page_breaks() to mark page breaks
        2. Replace page break markers with placeholders
        3. edgartools parse_html() to parse the document node tree
        4. Traverse nodes: tables kept as HTML, text to Markdown, lists to Markdown
        5. Split by placeholders into page list
        6. Deduplicate consecutive duplicate pages (preserve original page numbers)
        7. Output JSON
        """
        # Idempotent check
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                page_count = len(data.get("pages", []))
                return ParseResult(
                    success=True,
                    file_path=str(json_path),
                    total_pages=page_count,
                    file_size=json_path.stat().st_size,
                    skipped=True,
                )
            except Exception:
                pass  # JSON is corrupt, re-parse

        if not html_path.exists():
            return ParseResult(
                success=False,
                error=f"HTML file does not exist: {html_path}",
            )

        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
            mixed_content = self._html_to_mixed_markdown(html_content)
            pages = self._split_into_pages(mixed_content)
            pages = self._deduplicate_pages(pages)

            sections = self._extract_sections(pages)

            doc = {
                "document_name": html_path.name,
                "sections": sections,
                "pages": [
                    {"page_number": page_num, "full_content": content}
                    for page_num, content in pages
                ],
            }

            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            return ParseResult(
                success=True,
                file_path=str(json_path),
                total_pages=len(pages),
                file_size=json_path.stat().st_size,
            )

        except Exception as e:
            logger.error(f"Parsing failed {html_path.name}: {e}")
            return ParseResult(success=False, error=str(e))

    def _html_to_mixed_markdown(self, html: str) -> str:
        """
        Convert HTML to mixed-format Markdown:
        Uses edgartools' mark_page_breaks + parse_html

        - Tables kept in HTML format (<table>...</table>)
        - Headings converted to Markdown headings (#, ##, ###)
        - Paragraphs and text converted to plain text
        - Lists converted to Markdown lists
        - Page breaks marked with placeholders
        """
        # 1. Use edgartools to mark page breaks (professional SEC document page break detection)
        soup = BeautifulSoup(html, "html.parser")
        html_marked = mark_html_page_breaks(str(soup))

        # 2. Replace page break markers with plain-text placeholders to preserve them as text nodes after parse_html
        soup2 = BeautifulSoup(html_marked, "html.parser")
        for el in soup2.find_all(True):
            is_page = False
            for key, _ in el.attrs.items():
                if "_is_page_break" in str(key).lower():
                    is_page = True
                    break
            if is_page:
                # Wrap placeholder in a <p> tag so parse_html() preserves it as a ParagraphNode.
                # Bare text nodes at <body> level are silently dropped by edgartools' parser.
                p_tag = soup2.new_tag("p")
                p_tag.string = PAGE_BREAK_PLACEHOLDER
                el.replace_with(p_tag)

        # 3. Use edgartools to parse the document node tree
        document = parse_html(str(soup2))

        # 4. Traverse nodes and convert to mixed Markdown
        parts = []
        for node in document.root.walk():
            # Skip container nodes (those with non-text children); only process leaf nodes
            if hasattr(node, "children") and len(node.children) > 0:
                has_non_text_children = any(
                    not isinstance(child, TextNode) for child in node.children
                )
                if has_non_text_children:
                    continue

            if isinstance(node, TableNode):
                # Table: keep HTML format
                table_html = node.html()
                parts.append(table_html)
            elif isinstance(node, HeadingNode):
                # Only process leaf heading nodes
                if not hasattr(node, "children") or len(node.children) == 0:
                    level = min(node.level, 6)
                    text_content = node.text()
                    if text_content.strip():
                        markdown_heading = "#" * level + " " + text_content.strip()
                        parts.append(markdown_heading)
            elif isinstance(node, (TextNode, ParagraphNode)):
                # Only process leaf nodes
                if not hasattr(node, "children") or len(node.children) == 0:
                    text_content = node.text()
                    if not text_content.strip():
                        continue
                    # Page break placeholder: output directly as separator
                    if PAGE_BREAK_PLACEHOLDER in text_content:
                        parts.append(PAGE_BREAK_PLACEHOLDER)
                    else:
                        parts.append(text_content.strip())
            elif isinstance(node, ListNode):
                # List node: convert to Markdown list format
                list_items = []
                for child in node.children:
                    if isinstance(child, ListItemNode):
                        item_text = child.text().strip()
                        if item_text:
                            if hasattr(node, "ordered") and node.ordered:
                                index = list(node.children).index(child) + 1
                                list_items.append(f"{index}. {item_text}")
                            else:
                                list_items.append(f"- {item_text}")
                if list_items:
                    parts.extend(list_items)

        return "\n\n".join(parts)

    def _split_into_pages(self, content: str) -> list[tuple[int, str]]:
        """Split content by page break placeholders into page list, preserving original page numbers."""
        pages_raw = content.split(PAGE_BREAK_PLACEHOLDER)

        # Keep all pages (including empty ones) to maintain page number alignment
        result = []
        for i, page in enumerate(pages_raw):
            page = page.strip()
            result.append((i + 1, page))

        # If no page breaks found, treat the entire content as a single page
        if not result:
            result = [(1, content.strip())]

        return result

    def _deduplicate_pages(self, pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """Remove consecutive duplicate pages and filter near-empty pages, preserving original page numbers."""
        if not pages:
            return pages

        result = []
        prev_content = None
        for page_num, content in pages:
            # Skip near-empty pages (fewer than 10 non-whitespace characters)
            stripped = content.strip()
            if len(stripped) < 10:
                continue
            # Skip consecutive duplicate pages
            if content == prev_content:
                continue
            result.append((page_num, content))
            prev_content = content

        return result if result else [(1, "")]

    def _extract_sections(self, pages: list[tuple[int, str]]) -> list[dict]:
        """Extract SEC section metadata (Item numbers and Part headers) from parsed pages."""
        sections = []
        # Match patterns like "Item 1.", "Item 1A.", "Item 7.", "Part I", "Part II" etc.
        item_pattern = re.compile(
            r'(?:^|\n)\s*#*\s*((?:Item\s+\d+[A-C]?\.?|Part\s+[IV]+))\s*\.?\s+(.+?)(?:\n|$)',
            re.IGNORECASE | re.MULTILINE
        )
        seen = set()
        for page_num, content in pages:
            for match in item_pattern.finditer(content):
                item = match.group(1).strip().rstrip('.')
                title = match.group(2).strip()
                # Deduplicate: same item+title only recorded once (first occurrence)
                key = (item.lower(), title.lower())
                if key not in seen:
                    seen.add(key)
                    sections.append({
                        "item": item,
                        "title": title,
                        "page": page_num,
                    })
        return sections
