"""
Page query tool
"""

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.services.searcher import LocalSearcher
from mcp_sec.response import success_response, error_response


def register_page_tool(mcp: FastMCP):
    
    @mcp.tool()
    def get_report_pages(
        ticker: str, 
        form: str, 
        report_date: str,
        start_page: int, 
        page_count: int = 3
    ) -> str:
        """
        Retrieve full page content for a range of pages from a report.
        
        <strategy>
        Directly invoke this tool to retrieve large, continuous blocks of text. Do not pre-check if the file exists; if it is missing, the system will return an error, prompting you to download and parse.
        This tool is designed for reading entire chapters. It is typically called after keyword_search or get_report_toc has provided the starting page (start_page). If looking for specific data points, use keyword_search instead.
        </strategy>

        <critical_rules>
        1. Do not use this tool blindly without knowing the target page. Find the start_page via keyword_search or get_report_toc first.
        2. Keep page_count reasonable (default 3, max 5) to avoid context overflow.
        </critical_rules>
        
        Args:
            ticker: Stock ticker symbol
            form: Report type
            report_date: Report date (fiscal period end date)
            start_page: Starting page number (1-based)
            page_count: Number of consecutive pages to return, default 3, max 5
        """
        # Parameter limit check (page_count max 5)
        page_count = min(max(1, page_count), 5)

        config = load_config()
        json_path = LocalSearcher.find_json_file(config.json_dir_path, ticker, form, report_date)
        
        if not json_path:
            return error_response(
                error=f"Parsed file not found: {ticker}_{form}_{report_date}.json",
                hint="Ensure the report has been downloaded and parsed first."
            )
            
        total_pages = LocalSearcher.get_total_pages(json_path)
        if start_page < 1 or start_page > total_pages:
            return error_response(
                error=f"Page number {start_page} out of range",
                hint=f"This report has {total_pages} pages (1-{total_pages})."
            )
            
        pages = LocalSearcher.read_pages(json_path, start_page, page_count)
        
        if not pages:
            return error_response(error="No content found for the specified pages")
            
        page_data = [
            {
                "page_number": p.page_number,
                "content": p.full_content,
            }
            for p in pages
        ]
            
        return success_response(
            data={
                "document": json_path.stem,
                "total_pages": total_pages,
                "page_range": f"{pages[0].page_number}-{pages[-1].page_number}",
                "pages": page_data,
            }
        )
