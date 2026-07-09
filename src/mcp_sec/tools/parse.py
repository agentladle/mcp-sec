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
        Parse a downloaded HTML report (and HTML exhibits, if present) into a page-split JSON file.
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
            form: Report type, e.g. "10-K", "10-Q", "6-K", "8-K"
            report_date: Report date (fiscal period end date), e.g. "2025-01-31"
        """
        config = load_config()
        parser = get_parser()

        filename = LocalSearcher.build_filename(ticker, form, report_date)
        filing_dir = config.html_dir_path / filename
        flat_html = config.html_dir_path / f"{filename}.htm"
        json_path = config.json_dir_path / f"{filename}.json"

        if filing_dir.is_dir() and (filing_dir / "primary.htm").exists():
            result = parser.parse_bundle(filing_dir, json_path)
        elif flat_html.exists():
            result = parser.parse(flat_html, json_path)
        else:
            return error_response(
                error=f"HTML filing not found: {filename}/primary.htm or {filename}.htm",
                hint="Download the report first using download_sec_report.",
            )

        if result.success:
            data = {
                "filename": json_path.name,
                "total_pages": result.total_pages,
                "file_size_kb": round(result.file_size / 1024, 1),
                "exhibits_parsed": result.exhibits_parsed,
            }
            if result.skipped:
                return skipped_response(data=data)
            return success_response(
                data=data,
                hint=(
                    "You can now use keyword_search, get_report_pages, or "
                    "get_report_toc to explore this report."
                ),
            )
        return error_response(error=f"Parsing failed: {result.error}")
