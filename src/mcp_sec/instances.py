"""
Singleton instances for services.
Shared across all tool calls to preserve in-memory caches.
"""

from mcp_sec.config import load_config
from mcp_sec.services.downloader import SECDownloader
from mcp_sec.services.parser import ReportParser

_downloader: SECDownloader | None = None
_parser: ReportParser | None = None


def get_downloader() -> SECDownloader:
    """Get or create the singleton SECDownloader instance."""
    global _downloader
    if _downloader is None:
        _downloader = SECDownloader(load_config())
    return _downloader


def get_parser() -> ReportParser:
    """Get or create the singleton ReportParser instance."""
    global _parser
    if _parser is None:
        _parser = ReportParser()
    return _parser
