#!/usr/bin/env python3
"""Local-first MCP server for Accessibility Auditor.

Privacy model:
- Runs locally over stdio by default.
- `audit_html_file` reads local files on the same machine.
- `audit_html` audits caller-provided HTML in-memory.
- `audit_url` fetches only the target URL directly from this machine; it does not send
  source code/HTML to a hosted Accessibility Auditor service.
- Tool outputs are normalized findings and summaries rather than full HTML dumps.

Recommended usage for privacy-sensitive companies:
- run this server locally or inside the company's network
- connect the agent to the local stdio server
- prefer `audit_html_file` for checked-out repos / built HTML artifacts
- prefer `audit_html` for generated snapshots from internal pipelines
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from auditor import audit_html_content, audit_html_file, audit_website, load_report_schema
from project_auditor import (
    audit_many_project_paths,
    audit_project_path,
    detect_many_target_types,
    detect_target_type,
    export_many_projects_to_sarif,
    export_project_path_to_sarif,
)
from review_exporter import (
    export_many_projects_to_ci_summary,
    export_many_projects_to_pr_markdown,
    export_project_path_to_ci_summary,
    export_project_path_to_pr_markdown,
)


SERVER_NAME = "accessibility-auditor"
SERVER_INSTRUCTIONS = (
    "Local-first accessibility auditing server. Use this to audit URLs, local HTML files, "
    "or raw HTML content without sending private source code to a hosted third-party service. "
    "Results are returned as structured findings using a stable schema."
)

mcp = FastMCP(
    name=SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
)


def _privacy_notice(source_type: str) -> str:
    if source_type == "url":
        return (
            "URL was fetched directly by the local MCP server. No private source code was uploaded to a hosted Accessibility Auditor API."
        )
    if source_type == "file":
        return (
            "Local file was read and audited on the same machine as the MCP server. The response contains only structured findings, not raw file contents."
        )
    return (
        "HTML was audited in-memory by the local MCP server. The response contains structured findings rather than the original HTML."
    )


def _to_mcp_result(report: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    payload = dict(report.get("mcp_payload") or {})
    payload["privacy"] = {
        "mode": "local-first",
        "source_type": source_type,
        "notice": _privacy_notice(source_type),
    }
    payload["report_meta"] = {
        "platform": report.get("platform"),
        "mode": report.get("mode"),
        "timestamp": report.get("timestamp"),
        "source_type": report.get("source_type", source_type),
    }
    if report.get("file_path"):
        payload["report_meta"]["file_path"] = report["file_path"]
    return payload


@mcp.tool(
    name="audit_url",
    description=(
        "Audit a URL locally and return normalized accessibility findings. "
        "Use for public or internal URLs reachable from the MCP server machine."
    ),
    structured_output=True,
)
async def audit_url(url: str) -> Dict[str, Any]:
    report = await audit_website(url)
    report["source_type"] = "url"
    return _to_mcp_result(report, source_type="url")


@mcp.tool(
    name="audit_html_file",
    description=(
        "Audit a local HTML file path on the same machine as the MCP server. "
        "Best option for privacy-sensitive company use because raw file contents stay local."
    ),
    structured_output=True,
)
def audit_html_file_tool(file_path: str) -> Dict[str, Any]:
    report = audit_html_file(file_path)
    return _to_mcp_result(report, source_type="file")


@mcp.tool(
    name="audit_html",
    description=(
        "Audit raw HTML content in-memory and return normalized findings. "
        "Useful when a local pipeline already has the HTML snapshot and wants a structured report."
    ),
    structured_output=True,
)
def audit_html(html: str, source_name: Optional[str] = None) -> Dict[str, Any]:
    report = audit_html_content(html, source_name=source_name or "inline-html")
    return _to_mcp_result(report, source_type="html")


@mcp.tool(
    name="detect_target_type",
    description=(
        "Detect what kind of local project lives at a directory path: web, Android, iOS, Flutter, React Native, Electron, PyQt, WPF, or unknown."
    ),
    structured_output=True,
)
def detect_target_type_tool(project_path: str) -> Dict[str, Any]:
    return detect_target_type(project_path)


@mcp.tool(
    name="audit_project_path",
    description=(
        "Audit a local project directory with platform auto-detection and platform-specific static accessibility heuristics. "
        "Designed for privacy-sensitive company use inside local or internal environments."
    ),
    structured_output=True,
)
def audit_project_path_tool(project_path: str) -> Dict[str, Any]:
    report = audit_project_path(project_path)
    payload = dict(report.get("mcp_payload") or {})
    payload["privacy"] = {
        "mode": "local-first",
        "source_type": "project_path",
        "notice": "Project files were scanned locally on the MCP server machine. Structured findings were returned instead of raw source code.",
    }
    return payload


@mcp.tool(
    name="detect_many_target_types",
    description="Detect target types for multiple local project paths in one call.",
    structured_output=True,
)
def detect_many_target_types_tool(project_paths: list[str]) -> Dict[str, Any]:
    return detect_many_target_types(project_paths)


@mcp.tool(
    name="audit_many_project_paths",
    description="Audit multiple local project directories in one call and return structured per-project results.",
    structured_output=True,
)
def audit_many_project_paths_tool(project_paths: list[str]) -> Dict[str, Any]:
    result = audit_many_project_paths(project_paths)
    result["privacy"] = {
        "mode": "local-first",
        "source_type": "project_path_batch",
        "notice": "Project files were scanned locally on the MCP server machine. Structured findings were returned instead of raw source code.",
    }
    return result


@mcp.tool(
    name="export_project_path_sarif",
    description="Export a single local project accessibility audit as SARIF for CI/code-review systems.",
    structured_output=True,
)
def export_project_path_sarif_tool(project_path: str) -> Dict[str, Any]:
    return export_project_path_to_sarif(project_path)


@mcp.tool(
    name="export_many_projects_sarif",
    description="Export multiple local project accessibility audits as a multi-run SARIF payload.",
    structured_output=True,
)
def export_many_projects_sarif_tool(project_paths: list[str]) -> Dict[str, Any]:
    return export_many_projects_to_sarif(project_paths)


@mcp.tool(
    name="export_project_path_pr_markdown",
    description="Export a single local project audit as a GitHub/GitLab-friendly PR comment markdown.",
    structured_output=True,
)
def export_project_path_pr_markdown_tool(project_path: str) -> Dict[str, Any]:
    return {
        "format": "markdown",
        "variant": "pr_comment",
        "content": export_project_path_to_pr_markdown(project_path),
    }


@mcp.tool(
    name="export_many_projects_pr_markdown",
    description="Export multiple local project audits as a single GitHub/GitLab-friendly PR comment markdown.",
    structured_output=True,
)
def export_many_projects_pr_markdown_tool(project_paths: list[str]) -> Dict[str, Any]:
    return {
        "format": "markdown",
        "variant": "pr_comment",
        "content": export_many_projects_to_pr_markdown(project_paths),
    }


@mcp.tool(
    name="export_project_path_ci_summary",
    description="Export a single local project audit as a compact CI summary markdown (e.g. GitHub Actions step summary).",
    structured_output=True,
)
def export_project_path_ci_summary_tool(project_path: str) -> Dict[str, Any]:
    return {
        "format": "markdown",
        "variant": "ci_summary",
        "content": export_project_path_to_ci_summary(project_path),
    }


@mcp.tool(
    name="export_many_projects_ci_summary",
    description="Export multiple local project audits as a compact multi-project CI summary markdown.",
    structured_output=True,
)
def export_many_projects_ci_summary_tool(project_paths: list[str]) -> Dict[str, Any]:
    return {
        "format": "markdown",
        "variant": "ci_summary",
        "content": export_many_projects_to_ci_summary(project_paths),
    }


@mcp.tool(
    name="get_audit_schema",
    description="Return the JSON schema for the normalized accessibility audit result.",
    structured_output=True,
)
def get_audit_schema() -> Dict[str, Any]:
    return load_report_schema()


@mcp.tool(
    name="health_check",
    description="Return basic server health and privacy posture information.",
    structured_output=True,
)
def health_check() -> Dict[str, Any]:
    schema = load_report_schema()
    return {
        "server": SERVER_NAME,
        "status": "ok",
        "transport": "stdio-by-default",
        "privacy_mode": "local-first",
        "schema_id": schema.get("$id"),
        "available_tools": [
            "audit_url",
            "audit_html_file",
            "audit_html",
            "detect_target_type",
            "audit_project_path",
            "detect_many_target_types",
            "audit_many_project_paths",
            "export_project_path_sarif",
            "export_many_projects_sarif",
            "export_project_path_pr_markdown",
            "export_many_projects_pr_markdown",
            "export_project_path_ci_summary",
            "export_many_projects_ci_summary",
            "get_audit_schema",
            "health_check",
        ],
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
