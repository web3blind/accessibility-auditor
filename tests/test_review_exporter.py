import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from review_exporter import (
    export_many_projects_to_ci_summary,
    export_many_projects_to_pr_markdown,
    export_project_path_to_ci_summary,
    export_project_path_to_pr_markdown,
    export_report_to_ci_summary,
    export_report_to_pr_markdown,
)


def test_export_report_to_pr_markdown_structure():
    report = {
        "target": {"type": "project_path", "value": "/tmp/demo"},
        "platform": "web",
        "score": 72,
        "grade": "C (Fair)",
        "summary": {
            "critical": 1,
            "warning": 2,
            "info": 1,
            "overall_assessment": "Some issues found.",
        },
        "findings": [
            {
                "rule_id": "web_img_missing_alt",
                "severity": "critical",
                "title": "Image missing alt",
                "message": "img has no alt",
                "file_path": "/tmp/demo/index.html",
                "line": 5,
                "recommendation": "Add alt text.",
                "standards": {"wcag": "1.1.1"},
            },
            {
                "rule_id": "web_form_label_review",
                "severity": "warning",
                "title": "Form label review",
                "message": "input may lack label",
                "file_path": "/tmp/demo/index.html",
                "line": 10,
                "recommendation": "Add label.",
                "standards": {"wcag": "3.3.2"},
            },
            {
                "rule_id": "web_iframe_missing_title",
                "severity": "warning",
                "title": "Iframe missing title",
                "message": "iframe has no title",
                "file_path": "/tmp/demo/about.html",
                "line": 3,
                "recommendation": "Add title.",
                "standards": {},
            },
            {
                "rule_id": "manual_check",
                "severity": "info",
                "title": "Manual check note",
                "message": "Check focus order",
                "file_path": None,
                "line": None,
                "recommendation": "Test with keyboard.",
                "standards": {},
            },
        ],
        "next_steps": ["Fix alt texts", "Add labels"],
        "manual_checks": ["Screen reader test"],
    }
    md = export_report_to_pr_markdown(report)
    assert "## ♿ Accessibility Audit" in md
    assert "Score:** 72/100" in md
    assert "📁 Findings by File" in md
    assert "`index.html`" in md or "index.html" in md
    assert "`about.html`" in md or "about.html" in md
    assert "🔴" in md
    assert "🟡" in md
    assert "Top Issues" not in md  # PR variant does not use Top Issues heading
    assert "🛠️ Recommended Next Steps" in md
    assert "👀 Manual Verification Required" in md


def test_export_report_to_pr_markdown_truncate_limits():
    report = {
        "target": {"type": "project_path", "value": "/tmp/demo"},
        "platform": "web",
        "score": 50,
        "grade": "F (Fail)",
        "summary": {"critical": 0, "warning": 0, "info": 0, "overall_assessment": "Bad."},
        "findings": [
            {
                "rule_id": f"web_img_missing_alt_{i}",
                "severity": "warning",
                "title": f"Image missing alt {i}",
                "message": "no alt",
                "file_path": f"/tmp/demo/page_{i}.html",
                "line": i,
                "recommendation": "Add alt.",
                "standards": {},
            }
            for i in range(40)
        ],
        "next_steps": [],
        "manual_checks": [],
    }
    md = export_report_to_pr_markdown(report, max_files_shown=10, max_findings_per_file=3)
    assert "⚠️" in md
    assert "additional finding(s) were truncated" in md


def test_export_report_to_ci_summary_structure():
    report = {
        "target": {"type": "project_path", "value": "/tmp/demo"},
        "platform": "web",
        "score": 55,
        "grade": "F (Fail)",
        "summary": {"critical": 2, "warning": 1, "info": 0, "overall_assessment": "Fail."},
        "findings": [
            {
                "rule_id": "web_img_missing_alt",
                "severity": "critical",
                "title": "Image missing alt",
                "message": "img has no alt",
                "file_path": "/tmp/demo/index.html",
                "line": 5,
                "recommendation": "Add alt text.",
                "standards": {"wcag": "1.1.1"},
            },
            {
                "rule_id": "web_interactive_empty_name",
                "severity": "critical",
                "title": "Empty button",
                "message": "button is empty",
                "file_path": "/tmp/demo/index.html",
                "line": 7,
                "recommendation": "Add text.",
                "standards": {},
            },
            {
                "rule_id": "web_form_label_review",
                "severity": "warning",
                "title": "Form label review",
                "message": "input may lack label",
                "file_path": "/tmp/demo/index.html",
                "line": 10,
                "recommendation": "Add label.",
                "standards": {},
            },
        ],
        "next_steps": [],
        "manual_checks": [],
    }
    md = export_report_to_ci_summary(report, fail_threshold_score=60)
    assert "# ♿" in md
    assert "Status:** ❌ FAIL" in md
    assert "Top Issues" in md
    assert "🔴" in md
    assert "`index.html:5`" not in md  # full path used in CI summary
    assert "`/tmp/demo/index.html:5`" in md
    assert "Static analysis only" in md


def test_export_project_path_pr_markdown(tmp_path):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"><button></button></body></html>', encoding="utf-8")
    md = export_project_path_to_pr_markdown(str(project))
    assert "## ♿ Accessibility Audit" in md
    assert "web" in md.lower()
    assert "index.html" in md


def test_export_project_path_ci_summary(tmp_path):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")
    md = export_project_path_to_ci_summary(str(project))
    assert "# ♿" in md
    assert "Status:" in md
    assert "index.html" in md


def test_export_many_projects_pr_markdown(tmp_path):
    web = tmp_path / "site"
    web.mkdir()
    (web / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    flutter = tmp_path / "app"
    flutter.mkdir()
    (flutter / "pubspec.yaml").write_text("name: test\nflutter:\n  uses-material-design: true\n", encoding="utf-8")
    (flutter / "main.dart").write_text("Widget build() => IconButton(onPressed: () {}, icon: Icon(Icons.add));", encoding="utf-8")

    md = export_many_projects_to_pr_markdown([str(web), str(flutter)])
    assert "## ♿ Accessibility Audit — Multi-Project Summary" in md
    assert "site" in md
    assert "app" in md
    assert "Projects audited" in md


def test_export_many_projects_ci_summary(tmp_path):
    web = tmp_path / "site"
    web.mkdir()
    (web / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    md = export_many_projects_to_ci_summary([str(web)])
    assert "# ♿ Accessibility Auditor — Multi-Project CI Summary" in md
    assert "Overall Status:" in md
    assert "Projects Audited:" in md
