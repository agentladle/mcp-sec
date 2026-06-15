"""
Table of contents query tool
"""

import json as json_lib

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.services.searcher import LocalSearcher
from mcp_sec.response import success_response, error_response


def register_toc_tool(mcp: FastMCP):
    
    @mcp.tool()
    def get_report_toc(ticker: str, form: str, report_date: str) -> str:
        """
        Retrieve the Table of Contents of a report.
        Also returns structured section metadata (Item numbers and page locations) if available.
        
        <strategy>
        Directly invoke this tool to understand the structural layout of the report. Do not pre-check if the file exists; if missing, an error will prompt you to download and parse.
        Use this tool when you need an overview or want to read a specific chapter in its entirety by finding its starting page and passing it to get_report_pages.
        </strategy>

        <critical_rules>
        1. If you only need to locate specific numbers or singular facts, do NOT use this tool. Use keyword_search instead.
        2. Reading TOC to find a chapter and then reading pages is much slower than direct keyword search. Use it only for broad contextual understanding.
        </critical_rules>
        
        Args:
            ticker: Stock ticker symbol
            form: Report type
            report_date: Report date (fiscal period end date)
        """
        config = load_config()
        json_path = LocalSearcher.find_json_file(config.json_dir_path, ticker, form, report_date)
        
        if not json_path:
            return error_response(
                error=f"Parsed file not found: {ticker}_{form}_{report_date}.json",
                hint="Ensure the report has been downloaded and parsed first."
            )

        toc_pages = LocalSearcher.find_toc(json_path)

        # Also load sections metadata if available
        sections = []
        try:
            data = json_lib.loads(json_path.read_text(encoding="utf-8"))
            sections = data.get("sections", [])
        except Exception:
            pass

        if not toc_pages and not sections:
            return error_response(
                error="Could not find a Table of Contents within the first 15 pages",
                hint="Try using keyword_search to locate specific sections."
            )
            
        page_data = [
            {
                "page_number": p.page_number,
                "content": p.full_content,
            }
            for p in toc_pages
        ]

        return success_response(
            data={
                "document": json_path.stem,
                "toc_pages": page_data,
                "sections": sections,
            }
        )
