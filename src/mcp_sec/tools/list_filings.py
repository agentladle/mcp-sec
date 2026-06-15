"""
List available SEC filings tool
"""

from mcp.server.fastmcp import FastMCP

from mcp_sec.instances import get_downloader
from mcp_sec.response import success_response, error_response


def register_list_filings_tool(mcp: FastMCP):

    @mcp.tool()
    async def list_sec_filings(
        ticker: str,
        form: str | None = None,
        limit: int = 5,
    ) -> str:
        """
        List available SEC filings for a company.

        <strategy>
        Invoke this tool to verify available report dates ONLY when necessary. Do not use this as a mandatory first step.
        </strategy>

        <critical_rules>
        1. If the user provides a specific year or date, SKIP this tool entirely and proceed directly to keyword_search or download_sec_report.
        2. Use this tool ONLY if the user provides no timeframe, or if an attempt to download fails due to an invalid date/missing filing.
        </critical_rules>

        <examples>
        User: "What was Apple's 2023 revenue?"
        -> SKIP list_sec_filings, go straight to keyword_search for 2023.
        
        User: "Give me Microsoft's latest 10-K details."
        -> Use list_sec_filings to find the most recent report_date, then proceed.
        </examples>

        Args:
            ticker: Stock ticker, e.g. "AAPL"
            form: Filing type filter, e.g. "10-K". Omit to list all financial report types.
            limit: Max number of filings to return, default 5, max 20
        """
        limit = min(max(1, limit), 20)

        downloader = get_downloader()

        # 1. Resolve CIK
        cik = await downloader.resolve_cik(ticker)
        if not cik:
            return error_response(
                error=f"Ticker '{ticker}' not found",
                hint="Check the stock symbol spelling."
            )

        # 2. Query available filings
        filings = await downloader.list_available_filings(cik, form=form, limit=limit)

        if not filings:
            form_hint = f" {form}" if form else ""
            return error_response(
                error=f"No{form_hint} filings found for {ticker}",
            )

        # 3. Return structured data
        return success_response(
            data={
                "ticker": ticker.upper(),
                "filings": filings,
            }
        )