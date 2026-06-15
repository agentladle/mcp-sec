"""
Data models
"""

from dataclasses import dataclass, field


@dataclass
class DownloadResult:
    success: bool
    file_path: str = ""
    file_size: int = 0
    skipped: bool = False
    error: str = ""


@dataclass
class ParseResult:
    success: bool
    file_path: str = ""
    total_pages: int = 0
    file_size: int = 0
    skipped: bool = False
    error: str = ""


@dataclass
class SearchMatch:
    page_number: int
    score: float
    snippet: str
    keyword_hits: int  # number of matched keywords


@dataclass
class SearchResult:
    document_name: str
    matches: list[SearchMatch] = field(default_factory=list)


@dataclass
class Page:
    page_number: int
    full_content: str
