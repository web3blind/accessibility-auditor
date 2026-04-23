import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from review_exporter import (
    export_findings_to_github_annotations,
    export_many_projects_to_github_annotations,
    export_project_path_to_github_annotations,
)


def test_export_findings_to_github_annotations_basic():
    findings = [
        {
            "rule_id": "web_img_missing_alt",
            "severity": "critical",
            "title": "Image missing alt",
            "message": "img has no alt",
            "file_path": "index.html",
            "line": 5,
            "recommendation": "Add alt text.",
        },
        {
            "rule_id": "web_form_label_review",
            "severity": "warning",
            "title": "Form label review",
            "message": "input may lack label",
            "file_path": "about.html",
            "line": 10,
            "recommendation": "Add label.",
        },
        {
            "rule_id": "manual_check",
            "severity": "info",
            "title": "Manual check",
            "message": "Check focus order",
            "file_path": None,
            "line": None,
            "recommendation": "Test with keyboard.",
        },
    ]
    output = export_findings_to_github_annotations(findings)
    lines = output.split("\n")

    # Critical → error
    assert any("::error" in line and "file=index.html" in line and "line=5" in line for line in lines)
    # Warning → warning
    assert any("::warning" in line and "file=about.html" in line and "line=10" in line for line in lines)
    # Info → notice
    assert any("::notice" in line and "Manual check" in line for line in lines)


def test_export_findings_escapes_special_chars():
    findings = [
        {
            "severity": "critical",
            "title": "Bad\nchar\rhere",
            "message": "100% broken\nline",
            "file_path": "x.html",
            "line": 1,
            "recommendation": "Fix %",
        }
    ]
    output = export_findings_to_github_annotations(findings)
    assert "%0A" in output  # newline escaped
    assert "%0D" in output  # carriage return escaped
    assert "%25" in output  # percent escaped


def test_export_project_path_to_github_annotations(tmp_path):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    output = export_project_path_to_github_annotations(str(project))
    assert "::error" in output or "::warning" in output or "::notice" in output
    assert "index.html" in output


def test_export_many_projects_to_github_annotations(tmp_path):
    web = tmp_path / "site"
    web.mkdir()
    (web / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    flutter = tmp_path / "app"
    flutter.mkdir()
    (flutter / "pubspec.yaml").write_text("name: test\nflutter:\n  uses-material-design: true\n", encoding="utf-8")
    (flutter / "main.dart").write_text("Widget build() => IconButton(onPressed: () {}, icon: Icon(Icons.add));", encoding="utf-8")

    output = export_many_projects_to_github_annotations([str(web), str(flutter)])
    assert "::error" in output or "::warning" in output or "::notice" in output
