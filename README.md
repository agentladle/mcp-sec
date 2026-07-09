# AgentLadle MCP SEC

**English** | [中文](README_zh.md) | 📺 [Watch Demo](https://www.youtube.com/watch?v=qZteRG7WvIQ)

> 🇨🇳 **China A-Share Market** — Cloud-hosted MCP for Shanghai & Shenzhen listed companies. [Read more](Chinese-A-share-MCP-README.md) | [Get API Key](https://agentladle.com/register)

A [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that provides tools for **discovering, downloading, parsing, and searching** U.S. SEC financial reports.

It enables AI assistants (Claude, Cursor, etc.) to access SEC EDGAR data through 6 structured tools — from discovering available filings to keyword-searching within their pages.

## Features

- **6 MCP tools** for SEC financial data: state-driven retrieval (search directly, fallback to download/parse only when needed)
- **Professional SEC document parsing** using [edgartools](https://github.com/dgunning/edgar-tools) — accurate page-break detection and structured node-tree extraction for iXBRL filings
- **Local keyword search** with TF + position-boost scoring, zero external dependencies
- **Idempotent** — already-downloaded/parsed files are automatically skipped
- **Zero-config install** — one line to add to your MCP client, no clone or manual setup needed
- **Pure Python**, cross-platform (Windows / macOS / Linux)

## Prerequisites

- **Python 3.10+** — [Download Python](https://www.python.org/downloads/)
- **uv** — [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

> **Note:** After installing uv, restart your terminal and MCP client (e.g. Cherry Studio) to ensure the `uv` command is recognized.

## Quick Start

Add to your MCP client configuration (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "uvx",
      "args": ["agentladle-mcp-sec"],
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

That's it. `uvx` will automatically download the package and its dependencies from PyPI — no clone, no manual install, no path configuration.

> ⚠️ **SEC Email Requirement:** Replace `your@email.com` with your real email. The SEC requires a valid email in the User-Agent header. Using a fake email may result in your IP being blocked.

### Alternative: pip install

If you prefer managing the environment yourself:

```bash
pip install agentladle-mcp-sec
```

Then configure:

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "agentladle-mcp-sec",
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

### Alternative: Run from source (local development)

Clone the repository and run directly:

```bash
git clone https://github.com/agentladle/mcp-sec.git
```

Then configure your MCP client:

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-sec", "agentladle-mcp-sec"],
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

Replace `/path/to/mcp-sec` with the actual path to the cloned repository.

## Data Flow

```
SEC EDGAR API                     Local Files (~/.agentladle/mcp-sec/data/)
──────────────                    ──────────────────────────────
company_tickers.json   ──→       company_tickers.json         (ticker→CIK mapping)
                                     │
SEC Submissions API    ──→        html/*.htm                  (Tool 2: download)
                                     │
edgartools parsing     ──→        json/*.json                 (Tool 3: parse, page-split)
                                     │
Local TF search        ──→        search results              (Tool 4: keyword search)
Page range read        ──→        page content                (Tool 5: read pages)
TOC lookup             ──→        table of contents           (Tool 6: get TOC)
```

## Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `list_sec_filings` | Discover available SEC filings for a company |
| 2 | `download_sec_report` | Download a specific SEC filing as HTML |
| 3 | `parse_sec_report` | Parse HTML into page-split JSON using edgartools |
| 4 | `keyword_search` | Full-text keyword search with TF relevance scoring |
| 5 | `get_report_pages` | Read report content by page number range |
| 6 | `get_report_toc` | Get the Table of Contents page(s) |
| 7 | `lookup_ticker_cik` | **Diagnostic**: look up ticker→CIK mapping when CIK resolution fails |

### Tool 1: `list_sec_filings`

List available SEC filings for a company. Use this tool ONLY when the exact year/date is unspecified by the user, or when a download attempt fails due to an invalid date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker, e.g. `"AAPL"` |
| `form` | string | ❌ | Filing type filter, e.g. `"10-K"`. Omit to list all financial report types (10-K, 10-Q, 20-F, 6-K, 8-K, 40-F) |
| `limit` | int | ❌ | Max filings to return, default 5, max 20 |

### Tool 2: `download_sec_report`

Download a specific SEC filing from EDGAR. One filing per call. Idempotent (skips if file exists and is valid).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker, e.g. `"AAPL"` |
| `form` | string | ✅ | Filing type: `"10-K"`, `"10-Q"`, `"20-F"`, `"6-K"` |
| `report_date` | string | ✅ | Report date (fiscal period end date), e.g. `"2025-01-31"` |

### Tool 3: `parse_sec_report`

Parse a downloaded HTML filing into page-split JSON. Uses edgartools `mark_page_breaks()` + `parse_html()` for professional SEC document parsing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker |
| `form` | string | ✅ | Filing type |
| `report_date` | string | ✅ | Report date (fiscal period end date) |

### Tool 4: `keyword_search`

Full-text keyword search across all pages. Results ranked by TF + position-boost score.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker |
| `form` | string | ✅ | Filing type |
| `report_date` | string | ✅ | Report date (fiscal period end date) |
| `keywords` | string[] | ✅ | 1–5 search keywords |
| `match_mode` | string | ❌ | `"ANY"` (default, any keyword matches) / `"ALL"` (all must match) |
| `max_results` | int | ❌ | Max results to return, default 5, max 50 |

### Tool 5: `get_report_pages`

Read full page content by page number range.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker |
| `form` | string | ✅ | Filing type |
| `report_date` | string | ✅ | Report date (fiscal period end date) |
| `start_page` | int | ✅ | Start page number (1-based) |
| `page_count` | int | ❌ | Number of pages to return, default 3, max 5 |

### Tool 6: `get_report_toc`

Get the Table of Contents page(s). Searches the first 10 pages for "Table of Contents".

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker |
| `form` | string | ✅ | Filing type |
| `report_date` | string | ✅ | Report date (fiscal period end date) |

### Tool 7: `lookup_ticker_cik`

Diagnostic tool: look up ticker→CIK mapping. Use only when `download_sec_report` / `list_sec_filings` returns `CIK not found` or `Ticker not found`. Bypasses the session failed-ticker cache and returns same-CIK alias tickers.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | ✅ | Stock ticker, e.g. `"BABA"` |
| `refresh` | bool | ❌ | Force re-download of `company_tickers.json` from SEC (default: `false`) |

## Configuration

On first run, a default config file is created at `~/.agentladle/mcp-sec/config.yaml`:

```yaml
sec:
  email: ""

paths:
  data_dir: "~/.agentladle/mcp-sec/data"
  html_dir: "~/.agentladle/mcp-sec/data/html"
  json_dir: "~/.agentladle/mcp-sec/data/json"

download:
  delay_between_requests: 0.2
  min_file_size: 5000
```

The `email` field is used to build the SEC-compliant User-Agent header (`AgentLadleMcpSec {email}`). You can configure it in three ways (in order of priority):

1. **Environment variable** `SEC_EMAIL` — recommended, set it in your MCP client JSON config
2. **Config file** — edit `~/.agentladle/mcp-sec/config.yaml` and set `email`
3. **Default** — if empty, a placeholder email is used (not recommended for production)

> ⚠️ **SEC User-Agent Policy**: The SEC requires a real email in the User-Agent header. Using the default placeholder may result in your IP being blocked and can cause intermittent ticker→CIK lookup failures. `SEC_EMAIL` is required — please configure it.

## Data Directory Structure

```
~/.agentladle/mcp-sec/
├── config.yaml                        # Configuration (auto-created)
└── data/
    ├── company_tickers.json           # ticker→CIK mapping (auto-downloaded & cached)
    ├── html/                          # Downloaded HTML filings
    │   ├── AAPL_10-K_2025-01-31.htm
    │   └── ...
    └── json/                          # Parsed page-split JSON
        ├── AAPL_10-K_2025-01-31.json
        └── ...
```

**File naming convention:** `{TICKER}_{FORM}_{REPORT_DATE}.htm/json`

## Example Usage

The tools are designed with an **EAFP (Easier to Ask for Forgiveness than Permission)** approach. AI assistants should attempt to retrieve data directly and rely on errors to trigger downloads.

**Scenario A: File already exists locally (Shortest Path)**
```
User: "Analyze AAPL's latest 10-K management discussion"

1. keyword_search(ticker="AAPL", form="10-K", report_date="2025-01-31", keywords=["management", "discussion"])
   → Returns page snippets matching the keywords immediately.
```

**Scenario B: File missing (Fallback triggered)**
```
User: "What is Tesla's 2024 revenue?"

1. keyword_search(ticker="TSLA", form="10-K", report_date="2024-12-31", keywords=["revenue", "net sales"])
   → Error: File not found.
   
2. download_sec_report(ticker="TSLA", form="10-K", report_date="2024-12-31")
   → Downloads HTML to ~/.agentladle/mcp-sec/data/html/
   
3. parse_sec_report(ticker="TSLA", form="10-K", report_date="2024-12-31")
   → Parses into JSON.
   
4. keyword_search(ticker="TSLA", form="10-K", report_date="2024-12-31", keywords=["revenue", "net sales"])
   → Retries search and returns data.
```

## Tech Stack

| Component | Choice | Purpose |
|-----------|--------|---------|
| MCP Framework | `mcp` (FastMCP) | MCP server with stdio transport |
| HTTP Client | `httpx` | SEC API requests & file downloads |
| HTML Parsing | `edgartools` + `beautifulsoup4` | Professional SEC iXBRL parsing (page-break detection + node tree) |
| Search | Python built-in | TF + position-boost scoring |
| Config | `pyyaml` | YAML configuration file |

## Project Structure

```
src/mcp_sec/
├── __init__.py
├── server.py          # MCP Server entry point
├── config.py          # Config loading (~/.agentladle/mcp-sec/config.yaml, singleton cached)
├── models.py          # Data models
├── tools/
│   ├── list_filings.py # Tool 1: list_sec_filings
│   ├── download.py    # Tool 2: download_sec_report
│   ├── parse.py       # Tool 3: parse_sec_report
│   ├── search.py      # Tool 4: keyword_search
│   ├── page.py        # Tool 5: get_report_pages
│   └── toc.py         # Tool 6: get_report_toc
└── services/
    ├── downloader.py  # SEC EDGAR download + ticker→CIK
    ├── parser.py      # HTML→JSON parsing (edgartools)
    └── searcher.py    # Local JSON search + TF scoring
```

## License

MIT