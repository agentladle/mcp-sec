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
        """
        return self._parse_sources(
            sources=[("primary", html_path.name, html_path)],
            json_path=json_path,
            document_name=html_path.name,
        )

    def parse_bundle(self, filing_dir: Path, json_path: Path) -> ParseResult:
        """
        Parse primary.htm + downloaded HTML exhibits in a filing directory,
        merging them into one page-split JSON with section metadata.
        """
        primary = filing_dir / "primary.htm"
        if not primary.exists():
            # Backward compat: flat .htm next to dir name
            flat = filing_dir.parent / f"{filing_dir.name}.htm"
            if flat.exists():
                return self.parse(flat, json_path)
            return ParseResult(
                success=False,
                error=f"primary.htm not found in {filing_dir}",
            )

        sources: list[tuple[str, str, Path]] = [("primary", "Form primary", primary)]
        exhibits_parsed = 0

        manifest_path = filing_dir / "manifest.json"
        exhibit_files: list[tuple[str, Path]] = []
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for ex in manifest.get("exhibits_downloaded", []):
                    name = ex.get("name") or ""
                    path = filing_dir / Path(name).name
                    if path.exists():
                        exhibit_files.append((name, path))
            except Exception as e:
                logger.warning(f"Failed to read manifest.json: {e}")

        # Fallback: any html/txt in dir except primary/manifest
        if not exhibit_files:
            for path in sorted(filing_dir.iterdir()):
                if path.name.lower() in {"primary.htm", "manifest.json"}:
                    continue
                if path.suffix.lower() in {".htm", ".html", ".txt"}:
                    exhibit_files.append((path.name, path))

        for name, path in exhibit_files:
            sources.append((Path(name).stem, name, path))
            exhibits_parsed += 1

        result = self._parse_sources(
            sources=sources,
            json_path=json_path,
            document_name=filing_dir.name,
        )
        if result.success:
            result.exhibits_parsed = exhibits_parsed
        return result

    def _parse_sources(
        self,
        sources: list[tuple[str, str, Path]],
        json_path: Path,
        document_name: str,
    ) -> ParseResult:
        """
        Parse one or more HTML sources and merge into a single JSON document.
        sources: list of (section_id, section_title, path)
        """
        # Idempotent check: if JSON exists and source mtimes are older, skip
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                json_mtime = json_path.stat().st_mtime
                sources_newer = any(
                    p.exists() and p.stat().st_mtime > json_mtime for _, _, p in sources
                )
                if not sources_newer:
                    page_count = len(data.get("pages", []))
                    return ParseResult(
                        success=True,
                        file_path=str(json_path),
                        total_pages=page_count,
                        file_size=json_path.stat().st_size,
                        skipped=True,
                        exhibits_parsed=max(0, len(sources) - 1),
                    )
            except Exception:
                pass

        for _, _, path in sources:
            if not path.exists():
                return ParseResult(
                    success=False,
                    error=f"HTML file does not exist: {path}",
                )

        try:
            all_pages: list[tuple[int, str]] = []
            section_meta: list[dict] = []
            page_offset = 0

            for section_id, section_title, path in sources:
                html_content = path.read_text(encoding="utf-8", errors="replace")
                # Plain .txt exhibits: wrap lightly so parser still works
                if path.suffix.lower() == ".txt" and "<html" not in html_content.lower():
                    html_content = f"<html><body><pre>{html_content}</pre></body></html>"

                mixed_content = self._html_to_mixed_markdown(html_content)
                pages = self._split_into_pages(mixed_content)
                pages = self._deduplicate_pages(pages)

                if not pages or (len(pages) == 1 and not pages[0][1].strip()):
                    continue

                start_page = page_offset + 1
                renumbered = []
                for i, (_, content) in enumerate(pages):
                    renumbered.append((page_offset + i + 1, content))
                end_page = renumbered[-1][0]
                page_offset = end_page

                section_meta.append({
                    "id": section_id,
                    "title": section_title,
                    "page_start": start_page,
                    "page_end": end_page,
                    "source_file": path.name,
                })

                # Keep Item/Part extraction within this section's pages
                for item_sec in self._extract_sections(renumbered):
                    item_sec["section_id"] = section_id
                    section_meta.append(item_sec)

                all_pages.extend(renumbered)

            if not all_pages:
                return ParseResult(success=False, error="No parseable content found")

            doc = {
                "document_name": document_name,
                "sections": section_meta,
                "pages": [
                    {"page_number": page_num, "full_content": content}
                    for page_num, content in all_pages
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
                total_pages=len(all_pages),
                file_size=json_path.stat().st_size,
                exhibits_parsed=max(0, len(sources) - 1),
            )

        except Exception as e:
            logger.error(f"Parsing failed for {document_name}: {e}")
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
