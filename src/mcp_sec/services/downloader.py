"""
SEC EDGAR download service
- ticker → CIK mapping (SEC company_tickers.json, auto-download + cache + refresh)
- Query download URL for a specific report
- Download HTML files (idempotent)
"""

import json
import time
import asyncio
import logging
from pathlib import Path

import httpx

from mcp_sec.config import AppConfig
from mcp_sec.models import DownloadResult

logger = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"


class SECDownloader:

    TICKERS_CACHE_TTL = 7 * 24 * 3600       # Local file auto-refresh after 7 days
    TICKERS_DOWNLOAD_COOLDOWN = 300          # 5 min cooldown after download attempt

    def __init__(self, config: AppConfig):
        self.config = config
        self._tickers_cache: dict | None = None  # ticker -> CIK mapping cache
        self._client: httpx.AsyncClient | None = None
        self._last_download_attempt: float = 0
        self._failed_tickers: set[str] = set()

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self.config.sec.user_agent,
            "Accept": "application/json",
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=30,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client connection pool."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _is_cache_expired(self) -> bool:
        """Check if local company_tickers.json is older than TTL."""
        cache_path = self.config.company_tickers_path
        if not cache_path.exists():
            return True
        age = time.time() - cache_path.stat().st_mtime
        return age > self.TICKERS_CACHE_TTL

    def _can_download(self) -> bool:
        """Check if cooldown period has elapsed since last download attempt."""
        return time.time() - self._last_download_attempt > self.TICKERS_DOWNLOAD_COOLDOWN

    # ── ticker → CIK ──────────────────────────────────────────

    def _load_tickers_from_cache(self) -> dict:
        """Load ticker → CIK mapping from local cache file."""
        cache_path = self.config.company_tickers_path
        if not cache_path.exists():
            return {}

        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            # SEC format: {"0": {"cik_str": "320193", "ticker": "AAPL", ...}, ...}
            mapping = {}
            for entry in raw.values():
                ticker = entry.get("ticker", "").upper()
                cik = int(entry.get("cik_str", 0))
                if ticker and cik:
                    mapping[ticker] = cik
            return mapping
        except Exception as e:
            logger.warning(f"Failed to load company_tickers.json cache: {e}")
            return {}

    async def _download_company_tickers(self) -> dict:
        """Download the latest company_tickers.json from SEC and cache it."""
        logger.info("Downloading company_tickers.json from SEC ...")
        self._last_download_attempt = time.time()
        try:
            resp = await self._get_client().get(COMPANY_TICKERS_URL, timeout=30)
            resp.raise_for_status()
            raw = resp.json()

            # Save to local cache
            cache_path = self.config.company_tickers_path
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Cached company_tickers.json ({len(raw)} records)")

            # Build mapping
            mapping = {}
            for entry in raw.values():
                ticker = entry.get("ticker", "").upper()
                cik = int(entry.get("cik_str", 0))
                if ticker and cik:
                    mapping[ticker] = cik
            return mapping

        except Exception as e:
            logger.error(f"Failed to download company_tickers.json: {e}")
            return {}

    async def resolve_cik(self, ticker: str) -> int | None:
        """
        Resolve a ticker to its CIK.
        Lookup order: failed cache → in-memory cache → local file → re-download (with cooldown)
        """
        ticker = ticker.upper()

        # Quick reject for tickers already known to be missing in this session
        if ticker in self._failed_tickers:
            return None

        # 1. In-memory cache
        if self._tickers_cache and ticker in self._tickers_cache:
            return self._tickers_cache[ticker]

        # 2. Load from local file
        if self._tickers_cache is None:
            self._tickers_cache = self._load_tickers_from_cache()
            if ticker in self._tickers_cache:
                return self._tickers_cache[ticker]

        # 3. Check if refresh is needed (cache expired or ticker not found)
        needs_refresh = self._is_cache_expired() or ticker not in self._tickers_cache

        if needs_refresh and self._can_download():
            fresh_cache = await self._download_company_tickers()
            if fresh_cache:
                self._tickers_cache = fresh_cache

        result = self._tickers_cache.get(ticker) if self._tickers_cache else None
        if result is None:
            self._failed_tickers.add(ticker)
        return result

    # ── Query report URL ──────────────────────────────────────────

    async def fetch_filing_url(self, cik: int, form: str, report_date: str) -> tuple[str, str] | None:
        """
        Query the SEC submissions API for the download URL of a specific report.
        Returns (url, actual_report_date) or None.
        If report_date does not match exactly, returns None and logs available dates.
        """
        padded_cik = str(cik).zfill(10)
        url = SUBMISSIONS_URL_TEMPLATE.format(cik=padded_cik)

        try:
            resp = await self._get_client().get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Failed to query SEC submissions: {e}")
            return None

        filings = data.get("filings", {}).get("recent", {})
        if not filings:
            return None

        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        report_dates = filings.get("reportDate", [])
        accessions = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])

        if not report_dates:
            report_dates = dates

        is_year_only = len(report_date) == 4 and report_date.isdigit()

        # Match form + report_date (support year-only match against reportDate)
        for i, (f, rd) in enumerate(zip(forms, report_dates)):
            rd_str = str(rd) if rd else ""

            if is_year_only:
                match = (f == form) and rd_str.startswith(report_date)
            else:
                match = (f == form) and rd_str == report_date

            if match:
                fd_str = str(dates[i]) if dates[i] else ""
                accession_no_dashes = accessions[i].replace("-", "")
                file_url = ARCHIVES_URL_TEMPLATE.format(
                    cik=cik,
                    accession=accession_no_dashes,
                    primary_doc=primary_docs[i],
                )
                actual_date = rd_str if rd_str else fd_str
                return file_url, actual_date

        return None

    async def list_available_filings(
        self, cik: int, form: str | None = None, limit: int = 5
    ) -> list[dict]:
        """List available SEC filings.

        Args:
            cik: Company CIK
            form: Filing type filter, e.g. "10-K". None returns all types.
            limit: Max number of results

        Returns:
            [{"form": "10-K", "report_date": "2025-01-31"}, ...]
        """
        padded_cik = str(cik).zfill(10)
        url = SUBMISSIONS_URL_TEMPLATE.format(cik=padded_cik)

        try:
            resp = await self._get_client().get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        report_dates = filings.get("reportDate", [])

        # Common financial report types
        financial_forms = {"10-K", "10-Q", "20-F", "6-K", "8-K", "40-F"}

        available = []
        for i, (f, fd) in enumerate(zip(forms, dates)):
            # If form is specified, exact match; otherwise return only financial report types
            if form and f != form:
                continue
            if not form and f not in financial_forms:
                continue

            rd = report_dates[i] if i < len(report_dates) else None
            available.append({
                "form": f,
                "report_date": rd or "",
            })
            if len(available) >= limit:
                break
        return available

    # ── Download file ──────────────────────────────────────────────

    async def download_file(self, url: str, save_path: Path) -> DownloadResult:
        """
        Download an HTML file. Idempotent: skips if file already exists and is valid.
        Validates file content by checking for HTML markers in the file header.
        """
        # Idempotent check with HTML format validation
        if save_path.exists():
            size = save_path.stat().st_size
            if size > self.config.download.min_file_size:
                try:
                    head = save_path.read_bytes()[:1024].lower()
                    if b"<html" in head or b"<!doctype" in head:
                        return DownloadResult(
                            success=True,
                            file_path=str(save_path),
                            file_size=size,
                            skipped=True,
                        )
                except Exception:
                    pass  # Read failed, proceed to re-download

        try:
            # SEC rate limit
            await asyncio.sleep(self.config.download.delay_between_requests)

            resp = await self._get_client().get(url, headers={
                "User-Agent": self.config.sec.user_agent,
            }, timeout=120)
            resp.raise_for_status()

            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(resp.content)

            return DownloadResult(
                success=True,
                file_path=str(save_path),
                file_size=len(resp.content),
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
            )
