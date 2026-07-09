"""
SEC EDGAR download service
- ticker → CIK mapping (SEC company_tickers.json, auto-download + cache + refresh)
- Query download URL for a specific report
- Download HTML files / filing bundles with HTML exhibits (idempotent)
"""

import json
import re
import time
import asyncio
import logging
from pathlib import Path
from urllib.parse import unquote

import httpx

from mcp_sec.config import AppConfig
from mcp_sec.models import DownloadResult, BundleDownloadResult

logger = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
INDEX_JSON_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"

# Forms where exhibits usually carry the real content
EXHIBIT_DEFAULT_FORMS = {"6-K", "8-K", "6-K/A", "8-K/A"}
HTML_EXTS = {".htm", ".html", ".txt"}
SKIP_EXTS = {".xml", ".xsd", ".zip", ".jpg", ".jpeg", ".png", ".gif", ".json", ".css", ".js"}
PDF_EXTS = {".pdf"}


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

    async def lookup_ticker(self, ticker: str, refresh: bool = False) -> dict:
        """
        Diagnostic ticker → CIK lookup that BYPASSES the session-level _failed_tickers
        blacklist. Always reads from local cache (and optionally forces a SEC refresh).

        Returns a dict with:
          - ticker: queried ticker (uppercased)
          - cik: resolved CIK (int) or None
          - aliases: list of other tickers sharing the same CIK
          - cache_source: "memory" | "file" | "refreshed" | "empty"
          - in_failed_cache: bool — whether the ticker was in _failed_tickers before this call
          - total_entries: number of entries in the loaded mapping
        """
        ticker = ticker.upper()
        was_failed = ticker in self._failed_tickers

        # Ensure in-memory cache is populated (do NOT short-circuit on _failed_tickers)
        if self._tickers_cache is None:
            self._tickers_cache = self._load_tickers_from_cache()

        cache_source = "memory" if self._tickers_cache else "empty"

        # Optional forced refresh from SEC
        if refresh and self._can_download():
            fresh = await self._download_company_tickers()
            if fresh:
                self._tickers_cache = fresh
                cache_source = "refreshed"
            # If refresh failed but we already have a cache, keep reporting prior source
        elif not self._tickers_cache or ticker not in self._tickers_cache:
            # Reload from file (cache may have been empty or stale on first load)
            file_cache = self._load_tickers_from_cache()
            if file_cache:
                self._tickers_cache = file_cache
                cache_source = "file"

        mapping = self._tickers_cache or {}
        cik = mapping.get(ticker)

        # Find aliases: other tickers mapping to the same CIK
        aliases: list[str] = []
        if cik:
            aliases = sorted(t for t, c in mapping.items() if c == cik and t != ticker)
            # Self-heal: clear blacklist entry so subsequent resolve_cik calls succeed
            self._failed_tickers.discard(ticker)

        return {
            "ticker": ticker,
            "cik": cik,
            "aliases": aliases,
            "cache_source": cache_source,
            "in_failed_cache": was_failed,
            "total_entries": len(mapping),
        }

    def preload_tickers(self) -> int:
        """
        Eagerly load company_tickers.json into memory at startup.
        Returns the number of entries loaded (0 if file missing / empty).
        Does NOT blacklist any ticker on failure.
        """
        if self._tickers_cache is None:
            self._tickers_cache = self._load_tickers_from_cache()
        return len(self._tickers_cache) if self._tickers_cache else 0

    async def resolve_cik(self, ticker: str) -> int | None:
        """
        Resolve a ticker to its CIK.
        Lookup order: failed cache → in-memory cache → local file → re-download (with cooldown)

        Negative-cache rule: only blacklist a ticker when the mapping cache is
        successfully populated AND the ticker is confirmed absent.  An empty /
        failed cache load must NOT cause a blacklist entry (avoids permanent
        session-level false negatives).
        """
        ticker = ticker.upper()

        # Quick reject for tickers already known to be missing in this session
        if ticker in self._failed_tickers:
            return None

        # 1. In-memory cache
        if self._tickers_cache and ticker in self._tickers_cache:
            return self._tickers_cache[ticker]

        # 2. Load from local file when cache is missing or empty
        if not self._tickers_cache:
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
        # Only blacklist when the cache is populated (confirmed miss).
        # An empty cache means load/refresh failed — do NOT blacklist.
        if result is None and self._tickers_cache:
            self._failed_tickers.add(ticker)
        return result

    # ── Query report URL / filing meta ────────────────────────────

    async def fetch_filing_meta(
        self, cik: int, form: str, report_date: str
    ) -> dict | None:
        """
        Resolve a filing match from the SEC submissions API.
        Returns dict with: url, report_date, filing_date, accession, primary_doc, form
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

        for i, (f, rd) in enumerate(zip(forms, report_dates)):
            rd_str = str(rd) if rd else ""

            if is_year_only:
                match = (f == form) and rd_str.startswith(report_date)
            else:
                match = (f == form) and rd_str == report_date

            if match:
                fd_str = str(dates[i]) if dates[i] else ""
                accession = accessions[i]
                accession_no_dashes = accession.replace("-", "")
                primary_doc = primary_docs[i]
                file_url = ARCHIVES_URL_TEMPLATE.format(
                    cik=cik,
                    accession=accession_no_dashes,
                    primary_doc=primary_doc,
                )
                actual_date = rd_str if rd_str else fd_str
                return {
                    "url": file_url,
                    "report_date": actual_date,
                    "filing_date": fd_str,
                    "accession": accession,
                    "accession_nodash": accession_no_dashes,
                    "primary_doc": primary_doc,
                    "form": f,
                    "cik": cik,
                }

        return None

    async def fetch_filing_url(self, cik: int, form: str, report_date: str) -> tuple[str, str] | None:
        """
        Query the SEC submissions API for the download URL of a specific report.
        Returns (url, actual_report_date) or None.
        """
        meta = await self.fetch_filing_meta(cik, form, report_date)
        if not meta:
            return None
        return meta["url"], meta["report_date"]

    async def fetch_exhibit_list(self, cik: int, accession_nodash: str, primary_doc: str) -> list[dict]:
        """
        List non-primary files in a filing directory via index.json.
        Returns list of {name, type, size}.
        """
        index_url = INDEX_JSON_URL_TEMPLATE.format(cik=cik, accession=accession_nodash)
        try:
            resp = await self._get_client().get(index_url, timeout=30)
            resp.raise_for_status()
            items = resp.json().get("directory", {}).get("item", [])
        except Exception as e:
            logger.warning(f"Failed to fetch filing index.json: {e}")
            return []

        primary_lower = (primary_doc or "").lower()
        exhibits: list[dict] = []
        for it in items:
            name = it.get("name") or ""
            if not name:
                continue
            low = name.lower()
            if low == primary_lower or "index" in low:
                continue
            exhibits.append({
                "name": name,
                "type": it.get("type") or "",
                "size": it.get("size") or "0",
            })
        return exhibits

    @staticmethod
    def _extract_exhibit_links_from_html(html: str, primary_doc: str) -> list[str]:
        """Fallback: pull relative exhibit hrefs from the primary HTML."""
        primary_lower = (primary_doc or "").lower()
        names: list[str] = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
            href = unquote(match.group(1).strip())
            if not href or href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # strip query/fragment and directories
            href = href.split("?")[0].split("#")[0]
            name = Path(href).name
            low = name.lower()
            if not low or low == primary_lower or "index" in low:
                continue
            if low not in {n.lower() for n in names}:
                names.append(name)
        return names

    @staticmethod
    def _classify_exhibit(name: str) -> tuple[str, str]:
        """
        Classify an exhibit file.
        Returns (action, reason) where action is 'download' | 'skip'.
        """
        low = name.lower()
        suffix = Path(low).suffix

        # Full EDGAR submission package (duplicates primary + all exhibits)
        # e.g. 0001104659-26-081265.txt
        if re.fullmatch(r"\d{10}-\d{2}-\d{6}\.txt", low):
            return "skip", "full_submission_txt"

        if suffix in PDF_EXTS:
            return "skip", "pdf_not_supported"
        if suffix in SKIP_EXTS:
            return "skip", f"unsupported_ext:{suffix}"
        if suffix in {".htm", ".html"}:
            return "download", "html"
        # Only keep .txt when it looks like an exhibit, not the accession package
        if suffix == ".txt":
            if "ex" in low:
                return "download", "txt_exhibit"
            return "skip", "non_exhibit_txt"
        if not suffix:
            return "skip", "unknown_ext"
        return "skip", f"unsupported_ext:{suffix}"

    @staticmethod
    def should_include_exhibits(form: str, include_exhibits: bool | None) -> bool:
        if include_exhibits is not None:
            return include_exhibits
        return form.upper() in EXHIBIT_DEFAULT_FORMS

    async def download_filing_bundle(
        self,
        cik: int,
        form: str,
        report_date: str,
        filing_dir: Path,
        include_exhibits: bool | None = None,
    ) -> BundleDownloadResult:
        """
        Download primary HTML plus HTML exhibits into filing_dir.
        Writes manifest.json. PDF exhibits are recorded as skipped (not downloaded).
        """
        meta = await self.fetch_filing_meta(cik, form, report_date)
        if not meta:
            return BundleDownloadResult(
                success=False,
                error=f"No {form} filing found for date '{report_date}'",
            )

        actual_date = meta["report_date"]
        accession_nodash = meta["accession_nodash"]
        primary_doc = meta["primary_doc"]
        want_exhibits = self.should_include_exhibits(meta["form"], include_exhibits)

        filing_dir.mkdir(parents=True, exist_ok=True)
        primary_path = filing_dir / "primary.htm"
        manifest_path = filing_dir / "manifest.json"

        # Idempotent: if manifest + primary already valid, reuse
        if manifest_path.exists() and primary_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("accession") == meta["accession"] and primary_path.stat().st_size > 0:
                    return BundleDownloadResult(
                        success=True,
                        filing_dir=str(filing_dir),
                        report_date=actual_date,
                        primary_path=str(primary_path),
                        exhibits_downloaded=existing.get("exhibits_downloaded", []),
                        exhibits_skipped=existing.get("exhibits_skipped", []),
                        total_bytes=sum(
                            (filing_dir / Path(e["name"]).name).stat().st_size
                            for e in existing.get("exhibits_downloaded", [])
                            if (filing_dir / Path(e["name"]).name).exists()
                        ) + primary_path.stat().st_size,
                        skipped=True,
                    )
            except Exception:
                pass

        # 1) Download primary
        primary_result = await self.download_file(meta["url"], primary_path, min_size=0)
        if not primary_result.success:
            return BundleDownloadResult(
                success=False,
                error=f"Primary download failed: {primary_result.error}",
            )

        exhibits_downloaded: list[dict] = []
        exhibits_skipped: list[dict] = []
        total_bytes = primary_result.file_size

        if want_exhibits:
            # 2) Discover exhibits
            index_items = await self.fetch_exhibit_list(cik, accession_nodash, primary_doc)
            discovered_names = [it["name"] for it in index_items]

            # Fallback: parse primary HTML links if index empty
            if not discovered_names:
                try:
                    html = primary_path.read_text(encoding="utf-8", errors="replace")
                    discovered_names = self._extract_exhibit_links_from_html(html, primary_doc)
                except Exception as e:
                    logger.warning(f"Failed to extract exhibit links from primary: {e}")

            # Prefer EX-99* / *_ex* first, then other html
            def _sort_key(n: str) -> tuple:
                low = n.lower()
                is_ex99 = 0 if ("ex99" in low or "ex-99" in low) else 1
                is_ex = 0 if ("ex" in low) else 2
                return (is_ex99, is_ex, low)

            for name in sorted(set(discovered_names), key=_sort_key):
                action, reason = self._classify_exhibit(name)
                if action == "skip":
                    exhibits_skipped.append({"name": name, "reason": reason})
                    continue

                local_name = Path(name).name
                save_path = filing_dir / local_name
                file_url = ARCHIVES_URL_TEMPLATE.format(
                    cik=cik,
                    accession=accession_nodash,
                    primary_doc=name,
                )
                result = await self.download_file(file_url, save_path, min_size=0)
                if result.success:
                    exhibits_downloaded.append({
                        "name": local_name,
                        "source_name": name,
                        "reason": reason,
                        "bytes": result.file_size,
                    })
                    total_bytes += result.file_size
                else:
                    exhibits_skipped.append({
                        "name": name,
                        "reason": f"download_failed:{result.error}",
                    })

        manifest = {
            "ticker_form_date_hint": filing_dir.name,
            "cik": cik,
            "form": meta["form"],
            "report_date": actual_date,
            "filing_date": meta["filing_date"],
            "accession": meta["accession"],
            "primary_doc": primary_doc,
            "primary": "primary.htm",
            "include_exhibits": want_exhibits,
            "exhibits_downloaded": exhibits_downloaded,
            "exhibits_skipped": exhibits_skipped,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Also keep a flat alias for backward compatibility with older tools
        flat_alias = filing_dir.parent / f"{filing_dir.name}.htm"
        try:
            if not flat_alias.exists():
                flat_alias.write_bytes(primary_path.read_bytes())
        except Exception as e:
            logger.warning(f"Failed to write flat primary alias: {e}")

        return BundleDownloadResult(
            success=True,
            filing_dir=str(filing_dir),
            report_date=actual_date,
            primary_path=str(primary_path),
            exhibits_downloaded=exhibits_downloaded,
            exhibits_skipped=exhibits_skipped,
            total_bytes=total_bytes,
            skipped=False,
        )

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

    async def download_file(
        self, url: str, save_path: Path, min_size: int | None = None
    ) -> DownloadResult:
        """
        Download a file. Idempotent: skips if file already exists and is valid.
        For HTML, validates by checking for HTML markers in the file header.
        min_size overrides config.download.min_file_size (use 0 for short 6-K/exhibits).
        """
        size_threshold = (
            self.config.download.min_file_size if min_size is None else min_size
        )

        # Idempotent check
        if save_path.exists():
            size = save_path.stat().st_size
            if size > size_threshold:
                try:
                    head = save_path.read_bytes()[:1024].lower()
                    # Accept HTML or plain text exhibits
                    if (
                        b"<html" in head
                        or b"<!doctype" in head
                        or b"<document>" in head
                        or save_path.suffix.lower() == ".txt"
                    ):
                        return DownloadResult(
                            success=True,
                            file_path=str(save_path),
                            file_size=size,
                            skipped=True,
                        )
                    # Non-empty existing file with unknown markers: still skip re-download
                    if size > 0 and min_size == 0:
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
