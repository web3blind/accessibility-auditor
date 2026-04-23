import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project_auditor import (
    audit_many_project_paths,
    audit_project_path,
    detect_many_target_types,
    detect_target_type,
    export_many_projects_to_sarif,
    export_project_path_to_sarif,
)


def test_detect_android_project(tmp_path):
    project = tmp_path / "android-app"
    manifest_dir = project / "app" / "src" / "main"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "AndroidManifest.xml").write_text("<manifest package='com.example.app'></manifest>", encoding="utf-8")
    (project / "layout.xml").write_text(
        '<LinearLayout><ImageView android:src="@drawable/logo" /><EditText android:id="@+id/name" /></LinearLayout>',
        encoding="utf-8",
    )

    result = detect_target_type(str(project))
    report = audit_project_path(str(project))

    assert result["platform"] == "android"
    assert "android" in result["candidate_platforms"]
    assert any(item["rule_id"] == "android_missing_content_description" for item in report["findings"])
    assert any(item["line"] is None or item["line"] > 0 for item in report["findings"])


def test_audit_flutter_project_returns_findings(tmp_path):
    project = tmp_path / "flutter-app"
    project.mkdir()
    (project / "pubspec.yaml").write_text("name: test_app\nflutter:\n  uses-material-design: true\n", encoding="utf-8")
    (project / "main.dart").write_text(
        "import 'package:flutter/widgets.dart';\n"
        "Widget build() => GestureDetector(child: Image.asset('hero.png'));\n"
        "Widget icon() => IconButton(onPressed: () {}, icon: Icon(Icons.add));\n"
        "Widget hide() => ExcludeSemantics(child: Text('secret'));\n",
        encoding="utf-8",
    )

    report = audit_project_path(str(project))

    assert report["platform"] == "flutter"
    assert report["findings"]
    assert report["mcp_payload"]["summary"]["detected_platform"] == "flutter"
    rule_ids = [item["rule_id"] for item in report["findings"]]
    assert any(item.startswith("flutter_") for item in rule_ids)
    assert "flutter_iconbutton_missing_label" in rule_ids
    assert all(item.get("line") is None or item.get("line") > 0 for item in report["findings"])


def test_audit_electron_project_detects_web_like_issues(tmp_path):
    project = tmp_path / "electron-app"
    project.mkdir()
    (project / "package.json").write_text('{"dependencies":{"electron":"^1.0.0"}}', encoding="utf-8")
    (project / "index.html").write_text('<html><body><img src="x.png"><button></button><iframe src="a.html"></iframe></body></html>', encoding="utf-8")

    report = audit_project_path(str(project))

    assert report["platform"] == "electron"
    assert any(item["severity"] == "critical" for item in report["findings"])
    assert any(item["platform"] == "electron" for item in report["findings"])
    assert any(item["rule_id"] == "electron_iframe_missing_title" for item in report["findings"])


def test_php_folder_detected_as_web_and_scanned(tmp_path):
    project = tmp_path / "php-site"
    project.mkdir()
    (project / "index.php").write_text('<?php echo "ok"; ?><html><body><img src="hero.png"><input id="email"></body></html>', encoding="utf-8")

    detected = detect_target_type(str(project))
    report = audit_project_path(str(project))

    assert detected["platform"] == "web"
    rule_ids = [item["rule_id"] for item in report["findings"]]
    assert "web_img_missing_alt" in rule_ids
    assert "web_form_label_review" in rule_ids


def test_ios_project_generates_review_findings(tmp_path):
    project = tmp_path / "ios-app"
    project.mkdir()
    (project / "ViewController.swift").write_text(
        'import UIKit\nclass VC: UIViewController {\n let button = UIButton()\n let image = UIImageView()\n func x(){ button.isAccessibilityElement = false }\n }',
        encoding="utf-8",
    )

    report = audit_project_path(str(project))

    assert report["platform"] == "ios"
    rule_ids = [item["rule_id"] for item in report["findings"]]
    assert "ios_missing_accessibility_label_review" in rule_ids
    assert "ios_accessibility_element_false_review" in rule_ids


def test_audit_many_project_paths_summarizes_results(tmp_path):
    flutter = tmp_path / "flutter-app"
    flutter.mkdir()
    (flutter / "pubspec.yaml").write_text("name: test\nflutter:\n  uses-material-design: true\n", encoding="utf-8")
    (flutter / "main.dart").write_text("Widget build() => IconButton(onPressed: () {}, icon: Icon(Icons.add));", encoding="utf-8")

    electron = tmp_path / "electron-app"
    electron.mkdir()
    (electron / "package.json").write_text('{"dependencies":{"electron":"^1.0.0"}}', encoding="utf-8")
    (electron / "index.html").write_text('<html><body><img src="x.png"></body></html>', encoding="utf-8")

    detected = detect_many_target_types([str(flutter), str(electron)])
    audited = audit_many_project_paths([str(flutter), str(electron)])
    sarif = export_many_projects_to_sarif([str(flutter), str(electron)])
    single_sarif = export_project_path_to_sarif(str(electron))

    assert detected["count"] == 2
    assert audited["count"] == 2
    assert audited["summary"]["audited"] == 2
    assert audited["summary"]["critical"] + audited["summary"]["warning"] + audited["summary"]["info"] > 0
    assert all(item["ok"] for item in audited["results"])
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"]) == 2
    assert single_sarif["runs"][0]["results"]
