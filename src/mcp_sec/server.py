"""
SEC MCP Server main entry point
"""

import sys
import logging

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.instances import get_downloader
from mcp_sec.tools.download import register_download_tool
from mcp_sec.tools.parse import register_parse_tool
from mcp_sec.tools.search import register_search_tool
from mcp_sec.tools.page import register_page_tool
from mcp_sec.tools.toc import register_toc_tool
from mcp_sec.tools.list_filings import register_list_filings_tool
from mcp_sec.tools.lookup import register_lookup_tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr  # MCP stdio mode requires log output to stderr
)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP(
    "AgentLadle MCP SEC",
    dependencies=["httpx", "edgartools", "beautifulsoup4", "pyyaml"],
    instructions=(
        "You are equipped with a complete suite of SEC data retrieval and search tools. Make decisions based on the user's goal and system feedback.\n"
        "Assume the requested data file already exists locally. Directly invoke the retrieval tools (keyword_search, get_report_pages, get_report_toc) to extract information.\n"
        "Only when the system explicitly returns a 'file not found' error should you fall back to execute the download (download_sec_report) and parse (parse_sec_report) operations.\n"
        "If the user specifies a particular year or date in their prompt, skip listing available filings (list_sec_filings) and proceed directly to searching or downloading.\n"
        "If download_sec_report or list_sec_filings returns 'CIK not found' / 'Ticker not found', call lookup_ticker_cik to diagnose the mapping, then retry (optionally with an alias ticker)."
    )
)

# Register all tools
register_download_tool(mcp)
register_parse_tool(mcp)
register_search_tool(mcp)
register_page_tool(mcp)
register_toc_tool(mcp)
register_list_filings_tool(mcp)
register_lookup_tool(mcp)

def main():
    """Application entry point"""
    # Pre-load config to ensure data directories exist
    config = load_config()

    # Warn if no email configured (using default fake User-Agent)
    if not config.sec.email:
        sys.stderr.write(
            "\n"
            "  ⚠️  WARNING: No email configured for SEC User-Agent.\n"
            "  ⚠️  The SEC requires a real email in the User-Agent header.\n"
            "  ⚠️  Using the default may result in your IP being blocked.\n"
            "  ⚠️  Missing email can also cause intermittent ticker→CIK lookup failures.\n"
            "  ⚠️  Set SEC_EMAIL env var or edit ~/.agentladle/mcp-sec/config.yaml to add your email.\n"
            "\n"
        )
        sys.stderr.flush()

    # Eagerly load ticker→CIK mapping so the first user request does not pay
    # the cold-start cost (and so a failed first load does not blacklist tickers).
    try:
        count = get_downloader().preload_tickers()
        if count:
            logger.info("Preloaded %d ticker→CIK mappings from local cache", count)
        else:
            logger.warning(
                "Ticker cache empty at startup; first resolve_cik may trigger a SEC download"
            )
    except Exception as e:
        logger.warning("Failed to preload ticker cache at startup: %s", e)

    # Start MCP Server (default stdio)
    mcp.run()

if __name__ == "__main__":
    main()
