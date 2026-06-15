"""
SEC report download tool
"""

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.instances import get_downloader
from mcp_sec.services.searcher import LocalSearcher
from mcp_sec.response import success_response, skipped_response, error_response


def register_download_tool(mcp: FastMCP):
    
    @mcp.tool()
    async def download_sec_report(ticker: str, form: str, report_date: str) -> str:
        """
        Download a single SEC report from EDGAR for the specified company, form type, and report date.
        Downloads one report at a time; call this tool multiple times to download multiple reports.
        
        <strategy>
        Invoke this tool ONLY as a fallback when keyword_search, get_report_pages, or get_report_toc explicitly returns a "file not found" error.
        Do not proactively call this tool without receiving an error first.
        </strategy>

        <critical_rules>
        1. NEVER assume a file needs to be downloaded before attempting a search.
        2. Upon a successful download, you MUST immediately call parse_sec_report to convert it into a searchable format before returning to your search.
        </critical_rules>

        Args:
            ticker: Stock ticker symbol, e.g. "AAPL"
            form: Report type, e.g. "10-K", "10-Q", "20-F", "6-K", "8-K", "40-F"
            report_date: Report date (fiscal period end date) or fiscal year, e.g. "2023" or "2025-01-31"
        """
        config = load_config()
        downloader = get_downloader()
        
        # 1. Resolve CIK
        cik = await downloader.resolve_cik(ticker)
        if not cik:
            return error_response(
                error=f"CIK not found for ticker '{ticker}'",
                hint="Check the stock symbol. Use list_sec_filings to verify."
            )
            
        # 2. Look up filing URL
        res = await downloader.fetch_filing_url(cik, form, report_date)
        if not res:
            available = await downloader.list_available_filings(cik, form, limit=10)
            avail_dates = [f["report_date"] for f in available] if available else []
            return error_response(
                error=f"No {ticker} {form} filing found for date '{report_date}'",
                hint=f"Available {form} report dates: {avail_dates}. Use list_sec_filings to view all available reports."
            )
                    
        url, actual_date = res
        
        # 3. Build save path
        filename = LocalSearcher.build_filename(ticker, form, actual_date)
        save_path = config.html_dir_path / f"{filename}.htm"
        
        # 4. Download
        result = await downloader.download_file(url, save_path)
        
        if result.success:
            data = {
                "filename": f"{filename}.htm",
                "file_size_mb": round(result.file_size / 1024 / 1024, 2),
                "file_path": result.file_path,
                "report_date": actual_date,
            }
            if result.skipped:
                return skipped_response(
                    data=data,
                    hint=f"File already exists. Use report_date='{actual_date}' in subsequent tool calls."
                )
            else:
                return success_response(
                    data=data,
                    hint=f"Call parse_sec_report with report_date='{actual_date}' to parse this report."
                )
        else:
            return error_response(error=f"Download failed: {result.error}")
