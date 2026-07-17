"""Multi-page public website accessibility audit orchestration."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Awaitable, Callable, Any

from auditor import audit_website
from site_discovery import discover_site_urls, DiscoveryResult
from site_pricing import calculate_site_audit_price, estimate_max_cost, format_usdc, clamp_max_pages

AuditFn = Callable[[str], Awaitable[dict] | dict]


def _grade(score: int) -> str:
    if score >= 90:
        return "A (Excellent)"
    if score >= 80:
        return "B (Good)"
    if score >= 70:
        return "C (Fair)"
    if score >= 60:
        return "D (Poor)"
    return "F (Fail)"


async def _call_audit(audit_fn: AuditFn, url: str) -> dict:
    result = audit_fn(url)
    if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
        return await result  # type: ignore[arg-type]
    return result  # type: ignore[return-value]


def _make_site_audit_id(root_url: str, timestamp: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{root_url}|{timestamp}".encode("utf-8")).hexdigest()[:10]
    return f"site_{digest}"


def _is_network_failure_report(report: dict) -> bool:
    """Treat auditor-generated fetch failures as failed pages, not billable audits."""
    if report.get("score") != 0:
        return False
    findings = report.get("findings") or []
    issues = []
    issues.extend(findings)
    for category_items in (report.get("issues_by_category") or {}).values():
        issues.extend(category_items or [])
    return any(
        str(item.get("category", "")).lower() == "network"
        and str(item.get("severity", "")).lower() == "critical"
        for item in issues
    )


def _aggregate_reports(
    root_url: str,
    discovery: DiscoveryResult,
    page_reports: list[dict],
    failed_pages: list[dict],
    include_summary: bool,
    max_pages_requested: int,
    max_budget_usdc: str | None,
    escrow: dict | None = None,
    per_page_timeout_seconds: int = 45,
    max_duration_seconds: int = 600,
) -> dict[str, Any]:
    timestamp = datetime.now().isoformat()
    site_audit_id = _make_site_audit_id(root_url, timestamp)

    critical = sum(int(r.get("critical", 0)) for r in page_reports)
    warnings = sum(int(r.get("warnings", 0)) for r in page_reports)
    info = sum(int(r.get("info", 0)) for r in page_reports)
    total = critical + warnings + info
    pages_audited = len(page_reports)
    pages_failed = len(failed_pages)

    if page_reports:
        overall_score = max(0, round(sum(int(r.get("score", 0)) for r in page_reports) / len(page_reports)))
    else:
        overall_score = 0

    repeated_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for report in page_reports:
        page_url = report.get("url")
        for finding in report.get("findings", []) or []:
            key = (
                finding.get("rule_id") or finding.get("title") or "unknown-rule",
                finding.get("severity") or "info",
                finding.get("title") or "Accessibility finding",
            )
            item = repeated_map.setdefault(
                key,
                {
                    "rule_id": key[0],
                    "severity": key[1],
                    "title": key[2],
                    "affected_pages": 0,
                    "example_urls": [],
                },
            )
            item["affected_pages"] += 1
            if page_url and len(item["example_urls"]) < 5:
                item["example_urls"].append(page_url)

    repeated_issues = sorted(
        repeated_map.values(),
        key=lambda i: ({"critical": 0, "warning": 1, "info": 2}.get(i["severity"], 3), -i["affected_pages"]),
    )[:20]

    worst_pages = sorted(
        [
            {
                "url": r.get("url"),
                "score": r.get("score", 0),
                "critical": r.get("critical", 0),
                "warnings": r.get("warnings", 0),
                "total_issues": r.get("total_issues", 0),
            }
            for r in page_reports
        ],
        key=lambda p: (p["score"], -p["critical"], -p["warnings"]),
    )[:10]

    page_summaries = [
        {
            "url": r.get("url"),
            "status": "ok",
            "score": r.get("score", 0),
            "grade": r.get("grade"),
            "critical": r.get("critical", 0),
            "warnings": r.get("warnings", 0),
            "info": r.get("info", 0),
            "total_issues": r.get("total_issues", 0),
            "top_findings": (r.get("top_findings") or [])[:3],
        }
        for r in page_reports
    ] + failed_pages

    max_locked = max_budget_usdc or format_usdc(estimate_max_cost(max_pages_requested, include_summary))
    pricing = calculate_site_audit_price(pages_audited, max_locked=max_locked, include_summary=include_summary).as_dict()

    if critical:
        assessment = "Critical accessibility blockers were found across the audited site pages. Fix repeated critical patterns first."
    elif warnings:
        assessment = "No critical automated blocker dominates the site report, but warnings repeat across pages and need manual verification."
    elif page_reports:
        assessment = "Automated checks did not find major issues in the audited pages; manual keyboard and screen-reader testing remains the follow-up stage."
    else:
        assessment = "No page produced a complete audit report; review failed page reasons and retry with a smaller or reachable URL set."

    return {
        "schema_version": "site-accessibility-audit/1.0.0",
        "audit_type": "site",
        "root_url": root_url,
        "url": root_url,
        "site_audit_id": site_audit_id,
        "timestamp": timestamp,
        "platform": "web",
        "mode": "multi_page",
        "standards_checked": ["WCAG 2.1 AA", "GOST R 52872-2019"],
        "limits": {
            "max_pages_requested": max_pages_requested,
            "max_pages_allowed": clamp_max_pages(max_pages_requested),
            "same_domain_only": True,
            "include_summary": include_summary,
            "per_page_timeout_seconds": per_page_timeout_seconds,
            "max_duration_seconds": max_duration_seconds,
        },
        "discovery": discovery.as_dict(),
        "summary": {
            "pages_audited": pages_audited,
            "pages_failed": pages_failed,
            "overall_score": overall_score,
            "critical": critical,
            "warnings": warnings,
            "info": info,
            "total_issues": total,
            "overall_assessment": assessment,
        },
        # Compatibility fields for existing consumers that expect a single report-like shape.
        "score": overall_score,
        "grade": _grade(overall_score),
        "total_issues": total,
        "critical": critical,
        "warnings": warnings,
        "info": info,
        "repeated_issues": repeated_issues,
        "worst_pages": worst_pages,
        "page_reports": page_summaries,
        "pricing": pricing,
        "escrow": escrow or {"mode": "dry_run", "status": "not_settled"},
        "manual_checks": [
            "Verify representative audited flows with keyboard-only navigation.",
            "Run NVDA, JAWS, VoiceOver, or TalkBack on the most important page templates.",
            "Check dynamic states, dialogs, validation errors, reflow, and contrast in the rendered UI.",
        ],
        "next_steps": [
            "Fix repeated critical findings that affect multiple pages.",
            "Fix the worst-scoring page templates next.",
            "Repeat the multi-page audit, then perform manual assistive-technology verification.",
        ],
    }


async def audit_site(
    root_url: str,
    max_pages: int = 10,
    include_summary: bool = True,
    max_budget_usdc: str | None = None,
    audit_fn: AuditFn = audit_website,
    discovery_result: DiscoveryResult | None = None,
    per_page_timeout_seconds: int = 45,
    max_duration_seconds: int = 600,
) -> dict[str, Any]:
    """Discover and audit a safe capped set of same-site pages.

    The hard page cap can be high, so runtime protection is explicit: each page
    is wrapped in a timeout and the whole site job stops after max_duration.
    """
    page_cap = clamp_max_pages(max_pages)
    discovery = discovery_result or discover_site_urls(root_url, max_pages=page_cap)

    reports: list[dict] = []
    failed: list[dict] = []
    started = time.monotonic()
    selected_urls = discovery.selected_urls[:page_cap]
    for index, url in enumerate(selected_urls):
        elapsed = time.monotonic() - started
        if elapsed >= max_duration_seconds:
            for skipped_url in selected_urls[index:]:
                failed.append({
                    "url": skipped_url,
                    "status": "skipped",
                    "error": "site_audit_runtime_limit_reached",
                })
            break
        try:
            remaining = max(1, max_duration_seconds - int(elapsed))
            timeout = max(1, min(per_page_timeout_seconds, remaining))
            report = await asyncio.wait_for(_call_audit(audit_fn, url), timeout=timeout)
            report.setdefault("url", url)
            if _is_network_failure_report(report):
                top = (report.get("top_findings") or report.get("findings") or [{}])[0]
                failed.append({
                    "url": url,
                    "status": "failed",
                    "error": top.get("description") or top.get("title") or "network_fetch_failed",
                })
            else:
                reports.append(report)
        except asyncio.TimeoutError:
            failed.append({"url": url, "status": "failed", "error": "page_audit_timeout"})
        except Exception as exc:
            failed.append({"url": url, "status": "failed", "error": str(exc)[:500]})

    return _aggregate_reports(
        root_url=discovery.root_url,
        discovery=discovery,
        page_reports=reports,
        failed_pages=failed,
        include_summary=include_summary,
        max_pages_requested=max_pages,
        max_budget_usdc=max_budget_usdc,
        per_page_timeout_seconds=per_page_timeout_seconds,
        max_duration_seconds=max_duration_seconds,
    )
