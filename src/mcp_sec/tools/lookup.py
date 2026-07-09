"""
Ticker → CIK mapping diagnostic tool
"""

from mcp.server.fastmcp import FastMCP

from mcp_sec.instances import get_downloader
from mcp_sec.response import success_response, error_response


def register_lookup_tool(mcp: FastMCP):

    @mcp.tool()
    async def lookup_ticker_cik(ticker: str, refresh: bool = False) -> str:
        """
        Look up the SEC CIK mapping for a ticker symbol. Diagnostic / recovery tool.

        <strategy>
        Invoke this tool ONLY when download_sec_report or list_sec_filings returns
        "CIK not found" or "Ticker not found". Do NOT use it as a routine first step.
        After a successful lookup, retry the original download / list call.
        If aliases are returned, you may retry with an alias ticker instead.
        </strategy>

        <critical_rules>
        1. This tool bypasses the session-level failed-ticker blacklist and can clear it.
        2. Prefer refresh=false first (reads local cache). Use refresh=true only when
           total_entries is 0 or the ticker is still missing after a local lookup.
        </critical_rules>

        <examples>
        User / prior tool error: "CIK not found for ticker 'BABA'"
        -> lookup_ticker_cik(ticker="BABA")
        -> if cik found, retry download_sec_report with BABA (or an alias like BABAF)
        </examples>

        Args:
            ticker: Stock ticker symbol, e.g. "BABA"
            refresh: Force re-download of company_tickers.json from SEC (default: false)
        """
        if not ticker or not ticker.strip():
            return error_response(error="Please provide a ticker symbol")

        downloader = get_downloader()
        data = await downloader.lookup_ticker(ticker.strip(), refresh=refresh)

        cik = data.get("cik")
        aliases = data.get("aliases") or []
        total = data.get("total_entries", 0)
        in_failed = data.get("in_failed_cache", False)

        if cik:
            hint_parts = []
            if in_failed:
                hint_parts.append(
                    "Ticker resolved and removed from the failed-ticker cache. "
                    "Retry download_sec_report or list_sec_filings."
                )
            else:
                hint_parts.append(
                    "Mapping looks healthy. If download still fails, check report_date."
                )
            if aliases:
                hint_parts.append(f"Same-CIK aliases available: {aliases}.")
            return success_response(data=data, hint=" ".join(hint_parts))

        # cik is None
        if total == 0:
            return error_response(
                error=f"Ticker '{data['ticker']}' not found; local ticker cache is empty",
                hint=(
                    "Configure SEC_EMAIL and retry with refresh=true to download "
                    "company_tickers.json from SEC."
                ),
            )

        hint = (
            f"Cache has {total} entries but '{data['ticker']}' is absent. "
            "Check spelling, or retry with refresh=true."
        )
        if aliases:
            hint += f" Aliases: {aliases}."
        return success_response(data=data, hint=hint)
