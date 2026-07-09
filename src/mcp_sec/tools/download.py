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
    async def download_sec_report(
        ticker: str,
        form: str,
        report_date: str,
        include_exhibits: bool | None = None,
    ) -> str:
        """
        Download a SEC report from EDGAR for the specified company, form type, and report date.
        For 6-K/8-K, also downloads HTML exhibits by default (PDF exhibits are skipped, not parsed).

        <strategy>
        Invoke this tool ONLY as a fallback when keyword_search, get_report_pages, or get_report_toc explicitly returns a "file not found" error.
        Do not proactively call this tool without receiving an error first.
        </strategy>

        <critical_rules>
        1. NEVER assume a file needs to be downloaded before attempting a search.
        2. Upon a successful download, you MUST immediately call parse_sec_report to convert it into a searchable format before returning to your search.
        3. If exhibits_skipped contains pdf_not_supported, PDF exhibit text is unavailable in this version.
        </critical_rules>

        Args:
            ticker: Stock ticker symbol, e.g. "AAPL"
            form: Report type, e.g. "10-K", "10-Q", "20-F", "6-K", "8-K", "40-F"
            report_date: Report date (fiscal period end date) or fiscal year, e.g. "2023" or "2025-01-31"
            include_exhibits: Whether to download HTML exhibits. Default: true for 6-K/8-K, false otherwise. PDF exhibits are never parsed.
        """
        config = load_config()
        downloader = get_downloader()

        # 1. Resolve CIK
        cik = await downloader.resolve_cik(ticker)
        if not cik:
            return error_response(
                error=f"CIK not found for ticker '{ticker}'",
                hint=(
                    "Check the stock symbol. Use lookup_ticker_cik to diagnose "
                    "ticker→CIK mapping, or list_sec_filings to verify."
                ),
            )

        # 2. Download primary + optional HTML exhibits as a bundle
        filename = LocalSearcher.build_filename(ticker, form, report_date)
        # report_date may be year-only; actual_date comes from bundle result
        # Use a temporary dir name from input; rename not needed — actual_date used below
        # First resolve meta to get actual_date for stable folder naming
        meta = await downloader.fetch_filing_meta(cik, form, report_date)
        if not meta:
            available = await downloader.list_available_filings(cik, form, limit=10)
            avail_dates = [f["report_date"] for f in available] if available else []
            return error_response(
                error=f"No {ticker} {form} filing found for date '{report_date}'",
                hint=(
                    f"Available {form} report dates: {avail_dates}. "
                    "Use list_sec_filings to view all available reports."
                ),
            )

        actual_date = meta["report_date"]
        filename = LocalSearcher.build_filename(ticker, form, actual_date)
        filing_dir = config.html_dir_path / filename

        result = await downloader.download_filing_bundle(
            cik=cik,
            form=form,
            report_date=actual_date,
            filing_dir=filing_dir,
            include_exhibits=include_exhibits,
        )

        if not result.success:
            return error_response(error=f"Download failed: {result.error}")

        data = {
            "filename": filename,
            "filing_dir": result.filing_dir,
            "file_size_mb": round(result.total_bytes / 1024 / 1024, 2),
            "report_date": result.report_date,
            "exhibits_downloaded": [
                e.get("name") for e in result.exhibits_downloaded
            ],
            "exhibits_skipped": result.exhibits_skipped,
            "exhibits_downloaded_count": len(result.exhibits_downloaded),
            "exhibits_skipped_count": len(result.exhibits_skipped),
        }

        hint = (
            f"Call parse_sec_report with report_date='{result.report_date}' "
            "to parse this report (including HTML exhibits)."
        )
        if result.exhibits_skipped:
            pdf_skipped = [
                e for e in result.exhibits_skipped
                if e.get("reason") == "pdf_not_supported"
            ]
            if pdf_skipped:
                hint += (
                    f" Note: {len(pdf_skipped)} PDF exhibit(s) were skipped "
                    "(pdf_not_supported)."
                )

        if result.skipped:
            return skipped_response(
                data=data,
                hint=(
                    f"Filing bundle already exists. Use report_date='{result.report_date}' "
                    "in subsequent tool calls."
                ),
            )
        return success_response(data=data, hint=hint)
