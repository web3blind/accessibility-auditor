import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from site_auditor import audit_site
from site_discovery import DiscoveryResult


def fake_report(url: str, score: int, critical: int = 0, warnings: int = 0):
    findings = []
    if critical:
        findings.append({
            "rule_id": "images-missing-alt-text",
            "severity": "critical",
            "title": "Images missing alt text",
            "recommendation": "Add alt text.",
        })
    if warnings:
        findings.append({
            "rule_id": "generic-link-text",
            "severity": "warning",
            "title": "Generic link text",
            "recommendation": "Use descriptive link text.",
        })
    return {
        "url": url,
        "score": score,
        "grade": "C (Fair)",
        "critical": critical,
        "warnings": warnings,
        "info": 0,
        "total_issues": critical + warnings,
        "findings": findings,
        "top_findings": findings,
    }


def network_failure_report(url: str):
    return {
        "url": url,
        "score": 0,
        "grade": "F (Fail)",
        "critical": 1,
        "warnings": 0,
        "info": 0,
        "total_issues": 1,
        "findings": [{
            "rule_id": "network-connection-error",
            "category": "Network",
            "severity": "critical",
            "title": "Connection Error",
            "description": "browser failed",
        }],
        "top_findings": [{"category": "Network", "severity": "critical", "title": "Connection Error", "description": "browser failed"}],
    }


@pytest.mark.asyncio
async def test_audit_site_aggregates_page_reports_and_pricing():
    discovery = DiscoveryResult(
        root_url="https://example.com/",
        method="test",
        candidate_urls=2,
        selected_urls=["https://example.com/", "https://example.com/about"],
    )

    async def audit_fn(url: str):
        if url.endswith("about"):
            return fake_report(url, score=70, warnings=1)
        return fake_report(url, score=50, critical=1)

    report = await audit_site(
        "https://example.com/",
        max_pages=2,
        include_summary=True,
        max_budget_usdc="0.50",
        audit_fn=audit_fn,
        discovery_result=discovery,
    )

    assert report["audit_type"] == "site"
    assert report["mode"] == "multi_page"
    assert report["summary"]["pages_audited"] == 2
    assert report["critical"] == 1
    assert report["warnings"] == 1
    assert report["score"] == 60
    assert report["pricing"]["actual_settled"] == "0.50"
    assert report["pricing"]["refund"] == "0.00"
    assert report["repeated_issues"][0]["affected_pages"] == 1
    assert report["worst_pages"][0]["url"] == "https://example.com/"


@pytest.mark.asyncio
async def test_audit_site_records_partial_failures_without_crashing():
    discovery = DiscoveryResult(
        root_url="https://example.com/",
        method="test",
        candidate_urls=2,
        selected_urls=["https://example.com/", "https://example.com/broken"],
    )

    async def audit_fn(url: str):
        if url.endswith("broken"):
            raise RuntimeError("boom")
        return fake_report(url, score=95)

    report = await audit_site(
        "https://example.com/",
        max_pages=2,
        include_summary=True,
        max_budget_usdc="0.50",
        audit_fn=audit_fn,
        discovery_result=discovery,
    )

    assert report["summary"]["pages_audited"] == 1
    assert report["summary"]["pages_failed"] == 1
    assert any(page.get("status") == "failed" for page in report["page_reports"])
    assert report["pricing"]["actual_settled"] == "0.10"
    assert report["pricing"]["refund"] == "0.40"


@pytest.mark.asyncio
async def test_network_fetch_reports_are_failed_and_not_billed():
    discovery = DiscoveryResult(
        root_url="https://example.com/",
        method="test",
        candidate_urls=1,
        selected_urls=["https://example.com/"],
    )

    report = await audit_site(
        "https://example.com/",
        max_pages=1,
        max_budget_usdc="0.10",
        audit_fn=network_failure_report,
        discovery_result=discovery,
    )

    assert report["summary"]["pages_audited"] == 0
    assert report["summary"]["pages_failed"] == 1
    assert report["pricing"]["actual_settled"] == "0.00"
    assert report["pricing"]["refund"] == "0.10"


@pytest.mark.asyncio
async def test_audit_site_runtime_limit_marks_remaining_pages_skipped():
    discovery = DiscoveryResult(
        root_url="https://example.com/",
        method="test",
        candidate_urls=2,
        selected_urls=["https://example.com/", "https://example.com/second"],
    )

    async def slow_audit_fn(url: str):
        import asyncio
        await asyncio.sleep(0.05)
        return fake_report(url, score=95)

    report = await audit_site(
        "https://example.com/",
        max_pages=2,
        audit_fn=slow_audit_fn,
        discovery_result=discovery,
        per_page_timeout_seconds=1,
        max_duration_seconds=1,
    )

    assert report["limits"]["max_duration_seconds"] == 1
    assert report["summary"]["pages_audited"] >= 1
