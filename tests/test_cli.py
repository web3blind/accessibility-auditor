import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli import main


def test_cli_audit_project_json(tmp_path, capsys):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"><button></button></body></html>', encoding="utf-8")

    exit_code = main(["audit", str(project), "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert '"score"' in captured.out
    assert '"findings"' in captured.out


def test_cli_audit_project_pr_markdown(tmp_path, capsys):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    exit_code = main(["audit", str(project), "--format", "pr-markdown"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert "## ♿ Accessibility Audit" in captured.out
    assert "index.html" in captured.out


def test_cli_audit_project_ci_summary(tmp_path, capsys):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    exit_code = main(["audit", str(project), "--format", "ci-summary"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert "# ♿" in captured.out
    assert "Status:" in captured.out


def test_cli_audit_project_sarif(tmp_path, capsys):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    exit_code = main(["audit", str(project), "--format", "sarif"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert '"$schema"' in captured.out
    assert '"version": "2.1.0"' in captured.out


def test_cli_audit_project_output_file(tmp_path):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")
    output_file = tmp_path / "result.md"

    exit_code = main(["audit", str(project), "--format", "pr-markdown", "-o", str(output_file)])
    assert exit_code in (0, 1)
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "## ♿ Accessibility Audit" in content


def test_cli_audit_batch_projects(tmp_path, capsys):
    web = tmp_path / "site"
    web.mkdir()
    (web / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    flutter = tmp_path / "app"
    flutter.mkdir()
    (flutter / "pubspec.yaml").write_text("name: test\nflutter:\n  uses-material-design: true\n", encoding="utf-8")
    (flutter / "main.dart").write_text("Widget build() => IconButton(onPressed: () {}, icon: Icon(Icons.add));", encoding="utf-8")

    exit_code = main(["audit", str(web), str(flutter), "--format", "pr-markdown"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert "Multi-Project Summary" in captured.out
    assert "site" in captured.out
    assert "app" in captured.out


def test_cli_audit_project_fail_threshold(tmp_path, capsys):
    # Project with only warnings — no critical issues
    project = tmp_path / "ok-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><input id="x"></body></html>', encoding="utf-8")

    # With low threshold, should pass (exit 0) — no critical issues, score should be fine
    exit_code = main(["audit", str(project), "--format", "json", "--fail-threshold", "10"])
    assert exit_code == 0

    # With high threshold, should fail (exit 1) because score < 100
    exit_code = main(["audit", str(project), "--format", "json", "--fail-threshold", "100"])
    assert exit_code == 1

    # Now project with critical issues — should always fail regardless of threshold
    bad = tmp_path / "bad-project"
    bad.mkdir()
    (bad / "index.html").write_text('<html><body><img src="a.png"><button></button></body></html>', encoding="utf-8")
    exit_code = main(["audit", str(bad), "--format", "json", "--fail-threshold", "10"])
    assert exit_code == 1  # critical > 0 triggers failure


def test_cli_audit_project_github_annotations(tmp_path, capsys):
    project = tmp_path / "web-project"
    project.mkdir()
    (project / "index.html").write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    exit_code = main(["audit", str(project), "--format", "github-annotations"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert "::error" in captured.out or "::warning" in captured.out or "::notice" in captured.out
    assert "index.html" in captured.out


def test_cli_audit_html_file(tmp_path, capsys):
    html_file = tmp_path / "page.html"
    html_file.write_text('<html><body><img src="a.png"></body></html>', encoding="utf-8")

    exit_code = main(["audit-html-file", str(html_file), "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert '"findings"' in captured.out


def test_cli_audit_html_inline(capsys):
    exit_code = main(["audit-html", '<html><body><img src="a.png"></body></html>', "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert '"findings"' in captured.out


def test_cli_audit_html_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO('<html><body><img src="a.png"></body></html>'))
    exit_code = main(["audit-html", "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert '"findings"' in captured.out


def test_cli_help(capsys):
    try:
        main(["--help"])
    except SystemExit:
        pass
    captured = capsys.readouterr()
    assert "accessibility-auditor" in captured.out
    assert "audit" in captured.out
