"""
Unified response builders for MCP tool returns.
All tools return JSON strings for structured AI consumption.
"""

import json


def success_response(data: dict, hint: str = "") -> str:
    """Build a success response JSON string."""
    resp: dict = {"status": "success", "data": data}
    if hint:
        resp["hint"] = hint
    return json.dumps(resp, ensure_ascii=False)


def skipped_response(data: dict, hint: str = "") -> str:
    """Build a skipped (idempotent) response JSON string."""
    resp: dict = {"status": "skipped", "data": data}
    if hint:
        resp["hint"] = hint
    return json.dumps(resp, ensure_ascii=False)


def error_response(error: str, hint: str = "") -> str:
    """Build an error response JSON string."""
    resp: dict = {"status": "error", "error": error}
    if hint:
        resp["hint"] = hint
    return json.dumps(resp, ensure_ascii=False)
