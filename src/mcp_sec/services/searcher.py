"""
Local JSON file search service
- Keyword full-text search + TF relevance scoring
- Page range reading
- Table of contents page lookup
"""

import json
import re
import logging
from pathlib import Path

from mcp_sec.models import SearchMatch, Page

logger = logging.getLogger(__name__)


class LocalSearcher:

    # ── File location ──────────────────────────────────────────────

    @staticmethod
    def build_filename(ticker: str, form: str, report_date: str) -> str:
        """Build standard filename (without extension)."""
        return f"{ticker.upper()}_{form}_{report_date}"

    @staticmethod
    def find_json_file(json_dir: Path, ticker: str, form: str, report_date: str) -> Path | None:
        """Locate the JSON file for a given report."""
        filename = LocalSearcher.build_filename(ticker, form, report_date)
        json_path = json_dir / f"{filename}.json"
        if json_path.exists():
            return json_path
        return None

    @staticmethod
    def find_html_file(html_dir: Path, ticker: str, form: str, report_date: str) -> Path | None:
        """Locate the HTML file (or bundle primary) for a given report."""
        filename = LocalSearcher.build_filename(ticker, form, report_date)
        # New bundle layout
        primary = html_dir / filename / "primary.htm"
        if primary.exists():
            return primary
        # Legacy flat file
        html_path = html_dir / f"{filename}.htm"
        if html_path.exists():
            return html_path
        return None

    @staticmethod
    def find_filing_dir(html_dir: Path, ticker: str, form: str, report_date: str) -> Path | None:
        """Locate the filing bundle directory if present."""
        filename = LocalSearcher.build_filename(ticker, form, report_date)
        filing_dir = html_dir / filename
        if filing_dir.is_dir() and (filing_dir / "primary.htm").exists():
            return filing_dir
        return None

    # ── JSON file reading ─────────────────────────────────────────

    @staticmethod
    def load_pages(json_path: Path) -> list[Page]:
        """Load all pages from a JSON file."""
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            pages = []
            for p in data.get("pages", []):
                pages.append(Page(
                    page_number=p["page_number"],
                    full_content=p["full_content"],
                ))
            return pages
        except Exception as e:
            logger.error(f"Failed to load JSON {json_path}: {e}")
            return []

    # ── Page reading ──────────────────────────────────────────────

    @staticmethod
    def read_pages(json_path: Path, start_page: int, page_count: int = 3) -> list[Page]:
        """Read content for a given page range."""
        all_pages = LocalSearcher.load_pages(json_path)
        result = []
        for page in all_pages:
            if start_page <= page.page_number < start_page + page_count:
                result.append(page)
        return result

    @staticmethod
    def get_total_pages(json_path: Path) -> int:
        """Get total number of pages in the report."""
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return len(data.get("pages", []))
        except Exception:
            return 0

    # ── Table of contents lookup ──────────────────────────────────────────────

    @staticmethod
    def find_toc(json_path: Path) -> list[Page]:
        """
        Search for table of contents pages within the first 15 pages.
        Returns pages containing TOC content (may span two pages).
        Supports multiple TOC title variants: "Table of Contents", "INDEX" (with Item/Part context).
        """
        all_pages = LocalSearcher.load_pages(json_path)
        toc_pages = []

        for page in all_pages[:15]:
            content_lower = page.full_content.lower()
            is_toc = False

            # Enhanced detection: Check for Table of Contents header or specific Index context
            if "table of contents" in content_lower:
                is_toc = True
            elif "index" in content_lower and re.search(r'\b(item|part)\b', content_lower):
                is_toc = True

            if is_toc:
                toc_pages.append(page)
                # Check if next page is a TOC continuation
                next_page_num = page.page_number + 1
                for p2 in all_pages:
                    if p2.page_number == next_page_num:
                        p2_lower = p2.full_content.lower()
                        # If next page has multiple "item " references, likely a TOC continuation
                        item_count = p2_lower.count("item ")
                        if item_count >= 3 and "table of contents" not in p2_lower:
                            toc_pages.append(p2)
                        break
                break  # Only take the first TOC occurrence

        return toc_pages

    # ── Keyword search + TF scoring ─────────────────────────────────

    @staticmethod
    def search(
        json_path: Path,
        keywords: list[str],
        match_mode: str = "ANY",
        max_results: int = 5,
    ) -> list[SearchMatch]:
        """
        Search keywords across pages in a JSON file, return results sorted by TF score descending.

        Scoring algorithm:
          score = Σ (count_i / total_words × position_boost_i)
          - count_i: number of occurrences of keyword i
          - total_words: total word count of the page
          - position_boost_i: 1.2 if first occurrence is in the top 20%, else 1.0
          - ALL mode bonus: ×2.0 when all keywords are matched
        """
        all_pages = LocalSearcher.load_pages(json_path)
        results: list[SearchMatch] = []

        for page in all_pages:
            content_lower = page.full_content.lower()
            total_words = max(len(page.full_content.split()), 1)

            hit_count = 0
            score = 0.0

            for kw in keywords:
                kw_lower = kw.lower()
                kw_pattern = re.compile(r'(?<!\w)' + re.escape(kw_lower) + r'(?!\w)', re.IGNORECASE)
                kw_matches = kw_pattern.findall(content_lower)
                count = len(kw_matches)
                if count == 0:
                    continue

                hit_count += 1

                # TF: term frequency / total words
                tf = count / total_words

                # Position weighting: boost if first occurrence is in the top 20%
                first_pos = content_lower.find(kw_lower)
                position_boost = 1.2 if first_pos < len(content_lower) * 0.2 else 1.0

                score += tf * position_boost

            # Match mode check
            if match_mode.upper() == "ALL" and hit_count < len(keywords):
                continue
            if hit_count == 0:
                continue

            # ALL mode bonus when all keywords matched
            if match_mode.upper() == "ALL" and hit_count == len(keywords):
                score *= 2.0

            # Generate context snippet
            snippet = LocalSearcher._extract_snippet(page.full_content, keywords)

            results.append(SearchMatch(
                page_number=page.page_number,
                score=round(score, 6),
                snippet=snippet,
                keyword_hits=hit_count,
            ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:max_results]

    @staticmethod
    def _extract_snippet(content: str, keywords: list[str], context_len: int = 150) -> str:
        """
        Extract a context snippet containing the keyword(s).
        Centered on the first keyword match, taking context_len characters before and after.
        Highlights matched words with **keyword**.
        """
        content_lower = content.lower()
        best_pos = -1

        # Find position of the first keyword match
        for kw in keywords:
            pos = content_lower.find(kw.lower())
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos

        if best_pos < 0:
            return content[:context_len * 2] + "..."

        start = max(0, best_pos - context_len)
        end = min(len(content), best_pos + context_len)
        snippet = content[start:end]

        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        # Highlight keywords (preserving original case from the document)
        for kw in keywords:
            pattern = re.compile(r'(?<!\w)(' + re.escape(kw) + r')(?!\w)', re.IGNORECASE)
            snippet = pattern.sub(r'**\1**', snippet)

        # Clean up extra whitespace
        snippet = re.sub(r"\s+", " ", snippet).strip()

        return snippet
