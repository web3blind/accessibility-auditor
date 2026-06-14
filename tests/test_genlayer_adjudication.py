import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from genlayer_adjudication import adjudicate_report, build_evidence


def _report(score=48, critical=2, warnings=3):
    return {
        "schema_id": "https://hexdrive.tech/schemas/accessibility-audit-report.schema.json",
        "url": "https://example.com",
        "timestamp": "2026-06-14T00:00:00",
        "score": score,
        "grade": "F (Fail)",
        "total_issues": critical + warnings,
        "critical": critical,
        "warnings": warnings,
        "info": 0,
        "summary": {"overall_assessment": "Critical blockers found."},
        "top_findings": [{"severity": "critical", "title": "Missing labels"}],
        "manual_checks": ["Verify with screen reader."],
    }


def test_build_evidence_contains_claim_inputs():
    evidence = build_evidence(_report(), report_url="https://hexdrive.tech/audits/demo")
    assert evidence["schema_version"] == "genlayer-accessibility-evidence/1.0"
    assert evidence["score"] == 48
    assert evidence["issue_counts"]["critical"] == 2
    assert evidence["proof"]["report_url"] == "https://hexdrive.tech/audits/demo"


@pytest.mark.asyncio
async def test_adjudication_local_preview_is_english(monkeypatch):
    monkeypatch.setenv("GENLAYER_ENABLED", "false")
    result = await adjudicate_report(_report(), audit_id="demo", report_url="https://hexdrive.tech/audits/demo")
    assert result["status"] == "local_preview"
    assert result["network"]
    assert result["decision"]["verdict"] == "not_supported"
    assert "rationale_en" in result["decision"]
    assert result["decision"]["rationale_en"]
