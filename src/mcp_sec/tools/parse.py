"""
SEC report parsing tool
"""

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.instances import get_parser
from mcp_sec.services.searcher import LocalSearcher
from mcp_sec.response import success_response, skipped_response, error_response


def register_parse_tool(mcp: FastMCP):
    
    @mcp.tool()
    def parse_sec_report(ticker: str, form: str, report_date: str) -> str:
        """
        Parse a downloaded HTML report into a page-split JSON file.
        Typically called immediately after download_sec_report completes.
        
        <strategy>
        Invoke this tool ONLY under two specific system states:
        1. You have just successfully downloaded a new report using download_sec_report.
        2. A retrieval tool explicitly returns an error indicating that the HTML file exists but has not been parsed into JSON yet.
        </strategy>

        <critical_rules>
        1. Never call this tool preemptively. Wait for the download to succeed or for a specific error prompt.
        </critical_rules>

        Args:
            ticker: Stock ticker symbol, e.g. "AAPL"
            form: Report type, e.g. "10-K", "10-Q"
            report_date: Report date (fiscal period end date), e.g. "2025-01-31"
        """
        config = load_config()
        parser = get_parser()
        
        # Locate file
        filename = LocalSearcher.build_filename(ticker, form, report_date)
        html_path = config.html_dir_path / f"{filename}.htm"
        json_path = config.json_dir_path / f"{filename}.json"
        
        if not html_path.exists():
            return error_response(
                error=f"HTML file not found: {html_path.name}",
                hint="Download the report first using download_sec_report."
            )
            
        # Parse
        result = parser.parse(html_path, json_path)
        
        if result.success:
            data = {
                "filename": json_path.name,
                "total_pages": result.total_pages,
                "file_size_kb": round(result.file_size / 1024, 1),
            }
            if result.skipped:
                return skipped_response(data=data)
            else:
                return success_response(
                    data=data,
                    hint="You can now use keyword_search, get_report_pages, or get_report_toc to explore this report."
                )
        else:
            return error_response(error=f"Parsing failed: {result.error}")
