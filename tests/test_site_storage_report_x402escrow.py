import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from report_generator import ReportGenerator
from storage import AuditStorage
from x402escrow import build_dry_run_escrow, build_x402escrow_info, compute_escrow_id


def sample_site_report():
    return {
        "schema_version": "site-accessibility-audit/1.0.0",
        "audit_type": "site",
        "root_url": "https://example.com/",
        "url": "https://example.com/",
        "site_audit_id": "site_test123",
        "timestamp": "2026-07-17T00:00:00",
        "score": 72,
        "grade": "C (Fair)",
        "critical": 1,
        "warnings": 2,
        "info": 0,
        "summary": {
            "pages_audited": 2,
            "pages_failed": 1,
            "overall_assessment": "Critical accessibility blockers were found.",
        },
        "pricing": {
            "currency": "USDC",
            "price_per_page": "0.10",
            "summary_fee": "0.30",
            "max_locked": "0.60",
            "actual_settled": "0.50",
            "refund": "0.10",
        },
        "escrow": {"mode": "dry_run", "network": "base", "escrow_id": "escrow_test"},
        "repeated_issues": [{
            "rule_id": "images-missing-alt-text",
            "severity": "critical",
            "title": "Images missing alt text",
            "affected_pages": 2,
            "example_urls": ["https://example.com/", "https://example.com/about"],
        }],
        "worst_pages": [{"url": "https://example.com/", "score": 50, "critical": 1, "warnings": 0}],
        "page_reports": [{"url": "https://example.com/", "status": "ok", "score": 50, "critical": 1, "warnings": 0}],
        "manual_checks": ["Verify with a screen reader."],
    }


def test_storage_saves_and_loads_site_audit(tmp_path):
    storage = AuditStorage(storage_dir=str(tmp_path))
    report = sample_site_report()
    site_id = storage.save_site_audit(dict(report), is_public=True)
    loaded = storage.get_site_audit(site_id)
    assert loaded is not None
    assert loaded["audit_type"] == "site"
    assert loaded["is_public"] is True
    assert (tmp_path / f"site_audit_{site_id}.md").exists()


def test_report_generator_renders_site_sections():
    html = ReportGenerator().generate_html(sample_site_report())
    assert "Multi-page Accessibility Audit Report" in html
    assert "Fortytwo x402Escrow pricing" in html
    assert "Repeated issues across pages" in html
    assert "0.10" in html


def test_site_markdown_export_is_agent_readable():
    markdown = AuditStorage(storage_dir="/tmp/nonexistent-audit-test-dir").site_report_to_markdown(sample_site_report())
    assert "# Multi-Page Accessibility Audit Report" in markdown
    assert "## Repeated Issues" in markdown
    assert "Images missing alt text" in markdown


def test_x402escrow_info_and_dry_run_metadata_are_safe(monkeypatch):
    monkeypatch.setenv("X402ESCROW_DRY_RUN", "true")
    info = build_x402escrow_info()
    assert info["escrow_endpoint"] == "POST /api/x402escrow/site-audit"
    assert info["pricing_model"] == "metered_per_page"
    escrow = build_dry_run_escrow("https://example.com", "1.00")
    assert escrow["mode"] == "dry_run"
    assert escrow["settle_tx"] is None
    assert escrow["release_tx"] is None


def test_compute_escrow_id_is_deterministic():
    one = compute_escrow_id("0xabc", "nonce", "https://example.com")
    two = compute_escrow_id("0xABC", "nonce", "https://example.com")
    assert one == two
    assert one.startswith("escrow_")
