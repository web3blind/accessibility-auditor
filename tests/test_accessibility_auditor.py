import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from auditor import audit_html_content, load_report_schema
from report_generator import ReportGenerator
from storage import AuditStorage


def test_auditor_returns_rich_report():
    html = """
    <html>
      <head>
        <title>Home</title>
        <style>:focus{outline:none} .card{min-width:480px}</style>
      </head>
      <body>
        <div onclick="doThing()">Open</div>
        <img src="hero.png">
        <a href="/more">click here</a>
        <form>
          <input type="email" name="email">
        </form>
      </body>
    </html>
    """

    report = audit_html_content(html, source_name="https://example.com")

    assert report["mode"] == "full"
    assert report["platform"] == "web"
    assert report["schema_version"] == "1.0.0"
    assert report["schema_id"].endswith("accessibility-audit-report.schema.json")
    assert "summary" in report
    assert "passed_checks" in report
    assert "manual_checks" in report
    assert "next_steps" in report
    assert "findings" in report
    assert "mcp_payload" in report
    assert report["mcp_payload"]["schema_version"] == report["schema_version"]
    assert report["mcp_payload"]["findings"] == report["findings"]
    assert report["critical"] >= 1
    assert report["warnings"] >= 1
    assert report["manual_checks"]
    critical_titles = [item["title"] for item in report["findings_by_severity"]["critical"]]
    assert any("alt" in title.lower() or "language" in title.lower() for title in critical_titles)


def test_report_generator_renders_detailed_sections():
    report = {
        "url": "https://example.com",
        "timestamp": "2026-04-23T00:00:00",
        "score": 71,
        "grade": "C (Fair)",
        "total_issues": 3,
        "critical": 1,
        "warnings": 1,
        "info": 1,
        "platform": "web",
        "mode": "full",
        "standards_checked": ["WCAG 2.1 AA", "GOST R 52872-2019"],
        "summary": {
            "overall_assessment": "Есть заметные проблемы.",
            "checked_automatically": 14,
            "manual_follow_up_count": 3,
        },
        "findings_by_severity": {
            "critical": [{
                "category": "Images",
                "severity": "critical",
                "title": "Images missing alt text",
                "description": "Hero image has no alt.",
                "element": "img.hero",
                "recommendation": "Add descriptive alt text.",
                "wcag": "1.1.1 Non-text Content",
            }],
            "warning": [],
            "info": [],
        },
        "issues_by_category": {
            "Images": [{
                "category": "Images",
                "severity": "critical",
                "title": "Images missing alt text",
                "description": "Hero image has no alt.",
                "element": "img.hero",
                "recommendation": "Add descriptive alt text.",
                "wcag": "1.1.1 Non-text Content",
            }],
        },
        "passed_checks": [{"title": "Language declared", "description": "Found lang='en'.", "category": "Document"}],
        "manual_checks": ["Check with a screen reader."],
        "next_steps": ["Fix missing alt text first."],
    }

    html = ReportGenerator().generate_html(report)

    assert "Executive summary" in html
    assert "Critical issues" in html
    assert "Passed checks" in html
    assert "What needs manual testing" in html
    assert "Fix missing alt text first." in html


def test_storage_public_only_filter(tmp_path):
    storage = AuditStorage(storage_dir=str(tmp_path))
    base_report = {
        "schema_version": "1.0.0",
        "schema_id": "https://hexdrive.tech/schemas/accessibility-audit-report.schema.json",
        "url": "https://example.com",
        "timestamp": "2026-04-23T00:00:00",
        "score": 90,
        "grade": "A (Excellent)",
        "total_issues": 0,
        "critical": 0,
        "warnings": 0,
        "info": 0,
        "issues_by_category": {},
        "findings": [],
        "summary": {
            "overall_assessment": "No critical issues found.",
            "checked_automatically": 5,
            "manual_follow_up_count": 2,
        },
        "manual_checks": [],
        "next_steps": [],
    }

    storage.save_audit(dict(base_report), is_public=False)
    public_id = storage.save_audit(dict(base_report, url="https://public.example.com"), is_public=True)

    public_items = storage.list_audits(limit=10, public_only=True)

    assert len(public_items) == 1
    assert public_items[0]["id"] == public_id
    assert public_items[0]["is_public"] is True


def test_schema_loader_exposes_findings_definition():
    schema = load_report_schema()
    assert schema["$id"].endswith("accessibility-audit-report.schema.json")
    assert "findings" in schema["properties"]
    assert "finding" in schema["$defs"]
