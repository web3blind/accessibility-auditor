#!/usr/bin/env python3
"""Local stdio MCP server for Accessibility Auditor Errloop.

It reads the same local SQLite inbox as the production API when run on the
server. If ERRLOOP_REMOTE_BASE_URL and ERRLOOP_API_TOKEN are set, it can proxy to a protected remote Errloop API instead.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - runtime setup guard
    raise SystemExit("Install MCP dependencies first: pip install -r mcp-requirements.txt") from exc

from errloop.inbox import error_summary, get_error, list_errors, mark_error_status

mcp = FastMCP(
    name="accessibility-auditor-errloop",
    instructions="Agent-readable safe Errloop inbox for Accessibility Auditor production errors.",
)


def _remote_request(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    base = os.getenv("ERRLOOP_REMOTE_BASE_URL", "").rstrip("/")
    token = os.getenv("ERRLOOP_API_TOKEN", "")
    if not base or not token:
        return None
    data = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool(name="error_summary", description="Return grouped counts and recent safe Errloop error records.", structured_output=True)
def error_summary_tool(limit: int = 10) -> Dict[str, Any]:
    remote = _remote_request(f"/api/agent/errors/summary?limit={int(limit)}")
    return remote or error_summary(limit=limit)


@mcp.tool(name="list_errors", description="List safe, redacted Errloop records by status/since/limit.", structured_output=True)
def list_errors_tool(status: str = "active", limit: int = 20, since: Optional[str] = None) -> Dict[str, Any]:
    params = urllib.parse.urlencode({k: v for k, v in {"status": status, "limit": limit, "since": since}.items() if v is not None})
    remote = _remote_request(f"/api/agent/errors?{params}")
    return remote or {"errors": list_errors(status=status, limit=limit, since=since)}


@mcp.tool(name="get_error", description="Get one safe Errloop record by fingerprint.", structured_output=True)
def get_error_tool(fingerprint: str) -> Dict[str, Any]:
    remote = _remote_request(f"/api/agent/errors/{urllib.parse.quote(fingerprint)}")
    item = remote if remote is not None else get_error(fingerprint)
    return {"error": item} if item else {"error": "not_found", "fingerprint": fingerprint}


@mcp.tool(name="mark_error_status", description="Set an Errloop record status: active, investigating, fixed, ignored, or fixed_notified.", structured_output=True)
def mark_error_status_tool(fingerprint: str, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
    remote = _remote_request(
        f"/api/agent/errors/{urllib.parse.quote(fingerprint)}/status",
        method="POST",
        payload={"status": status, "reason": reason},
    )
    item = remote if remote is not None else mark_error_status(fingerprint, status, reason=reason)
    return {"error": item} if item else {"error": "not_found", "fingerprint": fingerprint}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
