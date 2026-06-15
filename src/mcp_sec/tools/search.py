"""
Full-text search tool
"""

import json

from mcp.server.fastmcp import FastMCP

from mcp_sec.config import load_config
from mcp_sec.services.searcher import LocalSearcher
from mcp_sec.response import success_response, error_response


def register_search_tool(mcp: FastMCP):
    
    @mcp.tool()
    def keyword_search(
        ticker: str, 
        form: str, 
        report_date: str,
        keywords: list[str], 
        match_mode: str = "ANY", 
        max_results: int = 5
    ) -> str:
        """
        Search parsed reports by keyword full-text search, results sorted by relevance (TF).
        Uses word-boundary matching for precise results.

        <strategy>
        Directly invoke this tool to find specific financial data, facts, or keyword discussions.
        Do not pre-check if the file exists. If it's missing, the system will return an error, prompting you to download and parse.
        For precise information extraction, rely solely on this tool. If the user requires an entire lengthy chapter, use this tool first to locate the starting page number, then use get_report_pages.
        </strategy>

        <critical_rules>
        1. NEVER pass full natural language sentences. You MUST extract 1 to 5 core keywords.
        2. COGNITIVE TRANSLATION: Convert conversational terms to SEC financial terminology (e.g., "how much they made" -> "net income", "revenue").
        3. SYNONYM EXPANSION: Maximize recall by providing synonyms (e.g., if looking for R&D, use ["R&D", "Research and Development", "Research"]).
        4. Omit stop words entirely.
        </critical_rules>

        <examples>
        User: "What was Apple's Q3 revenue in 2023?"
        -> keywords=["revenue", "net sales", "Q3"], ticker="AAPL", form="10-Q", report_date="2023-09-30" (or similar depending on input)
        
        User: "Did Tesla mention self-driving risks?"
        -> keywords=["self-driving", "autonomous", "FSD", "risk", "liability"], match_mode="ANY"
        </examples>
        
        Args:
            ticker: Stock ticker symbol
            form: Report type
            report_date: Report date (fiscal period end date)
            keywords: 1-5 search keywords
            match_mode: "ANY" (any match) or "ALL" (all must match), default ANY
            max_results: Maximum number of matching snippets to return, default 5
        """
        if not keywords:
            return error_response(error="Please provide at least one keyword")

        # Parameter limit check (keywords 1-5, max_results max 50)
        if len(keywords) > 5:
            keywords = keywords[:5]
        max_results = min(max(1, max_results), 50)
            
        config = load_config()
        json_path = LocalSearcher.find_json_file(config.json_dir_path, ticker, form, report_date)
        
        if not json_path:
            return error_response(
                error=f"Parsed file not found: {ticker}_{form}_{report_date}.json",
                hint="Ensure the report has been downloaded and parsed first."
            )
            
        matches = LocalSearcher.search(json_path, keywords, match_mode, max_results)
        
        if not matches:
            return success_response(
                data={"matches": [], "keywords": keywords, "match_mode": match_mode},
                hint="No pages found containing the specified keywords. Try different keywords."
            )
            
        match_data = [
            {
                "page_number": m.page_number,
                "score": m.score,
                "keyword_hits": m.keyword_hits,
                "snippet": m.snippet,
            }
            for m in matches
        ]
            
        return success_response(
            data={
                "document": json_path.stem,
                "keywords": keywords,
                "match_mode": match_mode,
                "total_matches": len(match_data),
                "matches": match_data,
            }
        )
