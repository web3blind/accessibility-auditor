#!/usr/bin/env python3
"""Local project/source accessibility scanning helpers for MCP.

This module provides a privacy-first foundation for auditing local project folders
without sending code to a hosted service. It currently focuses on static analysis
heuristics for platform detection and the most important accessibility signals.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "1.0.0"
SCHEMA_ID = "https://hexdrive.tech/schemas/accessibility-audit-report.schema.json"

MAX_FILE_SIZE = 300_000
MAX_FILES_PER_AUDIT = 80

PLATFORMS = [
    "web",
    "android",
    "ios",
    "flutter",
    "react-native",
    "electron",
    "pyqt",
    "wpf",
    "unknown",
]

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _collect_files(root: Path, patterns: Iterable[str], limit: int = MAX_FILES_PER_AUDIT) -> List[Path]:
    results: List[Path] = []
    seen = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            if path in seen:
                continue
            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            seen.add(path)
            results.append(path)
            if len(results) >= limit:
                return results
    return results


def detect_target_type(project_path: str) -> Dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Project path not found or not a directory: {project_path}")

    indicators: List[Dict[str, str]] = []
    scores = {platform: 0 for platform in PLATFORMS}

    def hit(platform: str, reason: str) -> None:
        scores[platform] += 1
        indicators.append({"platform": platform, "reason": reason})

    if (root / "pubspec.yaml").exists():
        text = _read_text(root / "pubspec.yaml")
        if "flutter:" in text:
            hit("flutter", "pubspec.yaml contains flutter configuration")

    package_json = root / "package.json"
    if package_json.exists():
        text = _read_text(package_json)
        if '"react-native"' in text or '"expo"' in text:
            hit("react-native", "package.json references react-native/expo")
        if '"electron"' in text or '"electron-builder"' in text or '"electron-forge"' in text:
            hit("electron", "package.json references electron tooling")
        if any(token in text for token in ["react", "vite", "next", "nuxt", "webpack", "@angular", "svelte"]):
            hit("web", "package.json references web frontend tooling")

    build_gradle_files = list(root.rglob("build.gradle")) + list(root.rglob("build.gradle.kts"))
    if build_gradle_files or (root / "AndroidManifest.xml").exists() or (root / "app" / "src" / "main" / "AndroidManifest.xml").exists():
        hit("android", "Android Gradle/manifest files detected")

    ios_files = _collect_files(root, ["*.xcodeproj", "*.xcworkspace", "Info.plist", "*.swift", "*.storyboard"], limit=10)
    if ios_files:
        hit("ios", "iOS/Xcode project files detected")

    xaml_files = _collect_files(root, ["*.xaml", "*.csproj"], limit=20)
    if xaml_files:
        if any("AutomationProperties." in _read_text(path) or path.suffix.lower() == ".xaml" for path in xaml_files[:5]):
            hit("wpf", "XAML/WPF project files detected")

    py_files = _collect_files(root, ["*.py"], limit=60)
    for path in py_files[:20]:
        text = _read_text(path)
        if any(token in text for token in ["PyQt5", "PyQt6", "PySide6", "setAccessibleName", "setAccessibleDescription"]):
            hit("pyqt", f"PyQt/PySide usage detected in {_safe_rel(path, root)}")
            break

    web_files = _collect_files(root, ["*.html", "*.php", "*.jsx", "*.tsx", "*.vue"], limit=30)
    if web_files:
        hit("web", "HTML/PHP/JSX/TSX/Vue source files detected")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_platform, top_score = ranked[0]
    if top_score <= 0:
        top_platform = "unknown"
    elif scores.get("electron", 0) > 0 and top_score == scores.get("web", 0):
        top_platform = "electron"
    elif scores.get("react-native", 0) > 0 and top_score == scores.get("web", 0):
        top_platform = "react-native"
    elif scores.get("flutter", 0) > 0 and top_score == scores.get("android", 0):
        top_platform = "flutter"

    relevant_files = {
        "web": [str(p) for p in _collect_files(root, ["*.html", "*.php", "*.jsx", "*.tsx", "*.vue"], limit=20)],
        "android": [str(p) for p in _collect_files(root, ["*.xml", "*.kt", "*.java"], limit=20)],
        "ios": [str(p) for p in _collect_files(root, ["*.swift", "*.storyboard", "*.xib", "Info.plist"], limit=20)],
        "flutter": [str(p) for p in _collect_files(root, ["*.dart", "pubspec.yaml"], limit=20)],
        "react-native": [str(p) for p in _collect_files(root, ["*.js", "*.jsx", "*.ts", "*.tsx"], limit=20)],
        "electron": [str(p) for p in _collect_files(root, ["*.html", "*.php", "*.js", "*.ts", "package.json"], limit=20)],
        "pyqt": [str(p) for p in _collect_files(root, ["*.py", "*.ui"], limit=20)],
        "wpf": [str(p) for p in _collect_files(root, ["*.xaml", "*.cs"], limit=20)],
    }

    return {
        "path": str(root),
        "platform": top_platform,
        "confidence": "high" if top_score >= 2 else "medium" if top_score == 1 else "low",
        "scores": scores,
        "indicators": indicators,
        "relevant_files": relevant_files.get(top_platform, []),
        "candidate_platforms": [platform for platform, score in ranked if score > 0],
    }


def _finding(rule_id: str, severity: str, title: str, message: str, file_path: Optional[str], recommendation: str, platform: str, wcag: Optional[str] = None, line: Optional[int] = None, requires_manual_check: bool = False, confidence: str = "medium") -> Dict[str, Any]:
    return {
        "id": None,
        "rule_id": rule_id,
        "category": platform,
        "platform": platform,
        "severity": severity,
        "title": title,
        "message": message,
        "description": message,
        "file_path": file_path,
        "line": line,
        "selector_hint": None,
        "recommendation": recommendation,
        "standards": {"wcag": wcag},
        "confidence": confidence,
        "requires_manual_check": requires_manual_check,
    }


def _line_number(text: str, needle: str) -> Optional[int]:
    idx = text.find(needle)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def _match_line(text: str, match: re.Match) -> int:
    return text.count("\n", 0, match.start()) + 1


def _append_once(findings: List[Dict[str, Any]], item: Dict[str, Any]) -> None:
    fingerprint = (
        item.get("rule_id"),
        item.get("file_path"),
        item.get("line"),
        item.get("title"),
    )
    for existing in findings:
        if (
            existing.get("rule_id"),
            existing.get("file_path"),
            existing.get("line"),
            existing.get("title"),
        ) == fingerprint:
            return
    findings.append(item)


def _enumerate_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(findings, key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), item.get("file_path") or "", item["rule_id"]))
    for idx, item in enumerate(ordered, start=1):
        item["id"] = f"finding-{idx:03d}"
    return ordered


def _scan_android(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.xml"], limit=40):
        text = _read_text(path)
        rel = _safe_rel(path, root)

        for match in re.finditer(r"<Image(?:View|Button)([^>]*?)(/?>)", text, re.S):
            attrs = match.group(1)
            if "contentDescription=" not in attrs and "importantForAccessibility=\"no\"" not in attrs and "importantForAccessibility=\"noHideDescendants\"" not in attrs:
                _append_once(findings, _finding(
                    "android_missing_content_description",
                    "critical",
                    "ImageView/ImageButton missing contentDescription",
                    f"Android layout may expose an unlabeled image control in {rel}.",
                    rel,
                    "Add android:contentDescription for meaningful images/buttons or explicitly mark decorative content not important for accessibility.",
                    "android",
                    wcag="1.1.1 Non-text Content",
                    line=_match_line(text, match),
                ))

        for match in re.finditer(r"<(TextView|EditText|Button|CheckBox|RadioButton|Switch|SwitchCompat)([^>]*?)(/?>)", text, re.S):
            attrs = match.group(2)
            if "android:text=" not in attrs and "android:hint=" not in attrs and "android:contentDescription=" not in attrs and "android:labelFor=" not in attrs:
                _append_once(findings, _finding(
                    "android_control_missing_text_or_label",
                    "warning",
                    "Android view may lack text/label metadata",
                    f"{match.group(1)} in {rel} appears without text, hint, labelFor, or contentDescription.",
                    rel,
                    "Ensure meaningful controls expose text, hint, labelFor, or contentDescription for TalkBack users.",
                    "android",
                    wcag="3.3.2 Labels or Instructions",
                    line=_match_line(text, match),
                    requires_manual_check=True,
                ))

        for match in re.finditer(r"<(LinearLayout|RelativeLayout|FrameLayout|ConstraintLayout)([^>]*?android:clickable=\"true\"[^>]*?)(/?>)", text, re.S):
            attrs = match.group(2)
            if "contentDescription=" not in attrs:
                _append_once(findings, _finding(
                    "android_clickable_container_unlabeled",
                    "warning",
                    "Clickable container may be unlabeled",
                    f"Clickable {match.group(1)} in {rel} may need accessibility labeling.",
                    rel,
                    "Prefer semantic controls where possible, or add contentDescription and verify TalkBack behavior.",
                    "android",
                    wcag="4.1.2 Name, Role, Value",
                    line=_match_line(text, match),
                ))

        for match in re.finditer(r"android:labelFor=", text):
            break
        else:
            if any(token in text for token in ["<EditText", "<TextInputEditText"]):
                _append_once(findings, _finding(
                    "android_label_for_review",
                    "info",
                    "Review labelFor usage for text inputs",
                    f"Text input controls found in {rel}; verify associated labels/labelFor relationships.",
                    rel,
                    "For external labels, connect TextView and input with android:labelFor where applicable.",
                    "android",
                    wcag="1.3.1 Info and Relationships",
                    requires_manual_check=True,
                ))

    for path in _collect_files(root, ["*.kt", "*.java"], limit=40):
        text = _read_text(path)
        rel = _safe_rel(path, root)
        if "importantForAccessibility" in text and any(token in text for token in ["NO", "NO_HIDE_DESCENDANTS", "noHideDescendants"]):
            _append_once(findings, _finding(
                "android_important_for_accessibility_review",
                "warning",
                "importantForAccessibility override detected",
                f"Review importantForAccessibility usage in {rel} to ensure interactive content is not hidden from TalkBack.",
                rel,
                "Avoid hiding meaningful interactive content from accessibility services.",
                "android",
                wcag="4.1.2 Name, Role, Value",
                line=_line_number(text, "importantForAccessibility"),
                requires_manual_check=True,
            ))
        if re.search(r"setContentDescription\s*\(", text) is None and any(token in text for token in ["ImageView", "ImageButton", "setImageResource", "setImageDrawable"]):
            _append_once(findings, _finding(
                "android_runtime_image_label_review",
                "info",
                "Review runtime image labeling in code",
                f"Image-related Android code in {rel} has no obvious setContentDescription call.",
                rel,
                "Verify dynamic image controls receive content descriptions in code when needed.",
                "android",
                wcag="1.1.1 Non-text Content",
                requires_manual_check=True,
            ))
    return findings


def _scan_flutter(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.dart"], limit=60):
        text = _read_text(path)
        rel = _safe_rel(path, root)
        for match in re.finditer(r"Image\.(asset|network|file|memory)\(", text):
            if "semanticLabel:" not in text and "Semantics(" not in text:
                _append_once(findings, _finding(
                    "flutter_image_missing_semantics",
                    "warning",
                    "Flutter image may lack semantic label",
                    f"Image widget in {rel} appears without semanticLabel or surrounding Semantics widget.",
                    rel,
                    "Add semanticLabel for meaningful images or wrap custom content in Semantics.",
                    "flutter",
                    wcag="1.1.1 Non-text Content",
                    line=_match_line(text, match),
                ))
        for widget_name in ["GestureDetector", "InkWell"]:
            for match in re.finditer(rf"{widget_name}\(", text):
                if "Semantics(" not in text and "onTapHint:" not in text:
                    _append_once(findings, _finding(
                        f"flutter_{widget_name.lower()}_semantics",
                        "warning",
                        f"{widget_name} without explicit semantics",
                        f"{widget_name} in {rel} may need Semantics or tap hints for screen-reader discoverability.",
                        rel,
                        "Wrap custom tappable widgets in Semantics or use accessible built-in controls where possible.",
                        "flutter",
                        wcag="4.1.2 Name, Role, Value",
                        line=_match_line(text, match),
                    ))
        for match in re.finditer(r"IconButton\(", text):
            if "tooltip:" not in text and "semanticLabel:" not in text:
                _append_once(findings, _finding(
                    "flutter_iconbutton_missing_label",
                    "critical",
                    "IconButton may lack semantic label",
                    f"IconButton in {rel} appears without tooltip or semanticLabel.",
                    rel,
                    "Add tooltip and/or semanticLabel so screen readers can announce the button purpose.",
                    "flutter",
                    wcag="4.1.2 Name, Role, Value",
                    line=_match_line(text, match),
                ))
        for match in re.finditer(r"ExcludeSemantics\(", text):
            _append_once(findings, _finding(
                "flutter_exclude_semantics_review",
                "info",
                "ExcludeSemantics usage requires review",
                f"ExcludeSemantics found in {rel}; verify meaningful content is not being hidden from assistive tech.",
                rel,
                "Use ExcludeSemantics carefully and confirm equivalent accessible output still exists.",
                "flutter",
                wcag="4.1.2 Name, Role, Value",
                line=_match_line(text, match),
                requires_manual_check=True,
            ))
    return findings


def _scan_react_native(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.js", "*.jsx", "*.ts", "*.tsx"], limit=60):
        text = _read_text(path)
        rel = _safe_rel(path, root)
        for match in re.finditer(r"<Image\b", text):
            snippet = text[match.start(): match.start() + 240]
            if "accessibilityLabel=" not in snippet and "alt=" not in snippet:
                _append_once(findings, _finding(
                    "rn_image_missing_accessibility_label",
                    "warning",
                    "React Native Image may lack accessibilityLabel",
                    f"Image component in {rel} appears without accessibilityLabel.",
                    rel,
                    "Add accessibilityLabel to meaningful images or mark decorative ones appropriately.",
                    "react-native",
                    wcag="1.1.1 Non-text Content",
                    line=_match_line(text, match),
                ))
        for match in re.finditer(r"<(TouchableOpacity|Pressable|TouchableHighlight)\b", text):
            snippet = text[match.start(): match.start() + 320]
            if "accessibilityLabel=" not in snippet and "accessibilityRole=" not in snippet and not re.search(r">\s*[^<{][^<]*<", snippet):
                _append_once(findings, _finding(
                    "rn_touchable_missing_label",
                    "critical",
                    "Touchable/Pressable may lack accessible label",
                    f"Touchable control in {rel} appears without accessibilityLabel or clear text content.",
                    rel,
                    "Ensure pressable controls expose accessibilityLabel, accessibilityRole, or clear visible text.",
                    "react-native",
                    wcag="4.1.2 Name, Role, Value",
                    line=_match_line(text, match),
                ))
            elif "accessibilityRole=" not in snippet:
                _append_once(findings, _finding(
                    "rn_touchable_missing_role",
                    "info",
                    "Pressable control should be reviewed for accessibilityRole",
                    f"Touchable/Pressable in {rel} has no explicit accessibilityRole nearby.",
                    rel,
                    "Add accessibilityRole when the default semantics are unclear, especially for custom controls.",
                    "react-native",
                    wcag="4.1.2 Name, Role, Value",
                    line=_match_line(text, match),
                    requires_manual_check=True,
                ))
        for match in re.finditer(r"<TextInput\b", text):
            snippet = text[match.start(): match.start() + 320]
            if "accessibilityLabel=" not in snippet and "placeholder=" not in snippet:
                _append_once(findings, _finding(
                    "rn_textinput_missing_label",
                    "warning",
                    "TextInput may lack accessible label",
                    f"TextInput in {rel} appears without accessibilityLabel or placeholder.",
                    rel,
                    "Add accessibilityLabel and ensure visible instructions are programmatically associated.",
                    "react-native",
                    wcag="3.3.2 Labels or Instructions",
                    line=_match_line(text, match),
                ))
        for match in re.finditer(r"accessible=\{?false\}?", text):
            _append_once(findings, _finding(
                "rn_accessible_false_review",
                "info",
                "accessible={false} usage requires review",
                f"React Native accessibility suppression found in {rel}; verify important content is not hidden from screen readers.",
                rel,
                "Use accessible={false} carefully and confirm child semantics remain appropriate.",
                "react-native",
                wcag="4.1.2 Name, Role, Value",
                line=_match_line(text, match),
                requires_manual_check=True,
            ))
    return findings


def _scan_electron_or_web(root: Path, platform: str) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.html", "*.php", "*.jsx", "*.tsx", "*.vue"], limit=60):
        text = _read_text(path)
        rel = _safe_rel(path, root)
        for match in re.finditer(r"<img\b(?![^>]*\balt=)", text, re.I):
            _append_once(findings, _finding(
                f"{platform}_img_missing_alt",
                "critical",
                "Image missing alt attribute",
                f"Found an <img> element without alt in {rel}.",
                rel,
                "Add descriptive alt text or alt='' for decorative images.",
                platform,
                wcag="1.1.1 Non-text Content",
                line=_match_line(text, match),
            ))
        for match in re.finditer(r"<(button|a)\b[^>]*>\s*</\1>", text, re.I | re.S):
            _append_once(findings, _finding(
                f"{platform}_interactive_empty_name",
                "critical",
                "Interactive element may have no accessible name",
                f"Found an apparently empty button/link in {rel}.",
                rel,
                "Add visible text or aria-label/aria-labelledby to interactive controls.",
                platform,
                wcag="4.1.2 Name, Role, Value",
                line=_match_line(text, match),
            ))
        for match in re.finditer(r"<(input|textarea|select)\b", text, re.I):
            snippet = text[match.start(): match.start() + 320]
            if "aria-label=" not in snippet and "aria-labelledby=" not in snippet and "id=" in snippet and "<label" not in text:
                _append_once(findings, _finding(
                    f"{platform}_form_label_review",
                    "warning",
                    "Form control should be reviewed for labeling",
                    f"Form control in {rel} may lack an associated label.",
                    rel,
                    "Ensure inputs, selects and textareas have visible labels or aria-label/aria-labelledby.",
                    platform,
                    wcag="3.3.2 Labels or Instructions",
                    line=_match_line(text, match),
                ))
        for match in re.finditer(r"<(iframe)\b(?![^>]*\btitle=)", text, re.I):
            _append_once(findings, _finding(
                f"{platform}_iframe_missing_title",
                "warning",
                "Iframe missing title",
                f"Found an iframe without title in {rel}.",
                rel,
                "Add a descriptive title attribute to embedded iframes.",
                platform,
                wcag="4.1.2 Name, Role, Value",
                line=_match_line(text, match),
            ))
    return findings


def _scan_pyqt(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.py", "*.ui"], limit=60):
        text = _read_text(path)
        if any(token in text for token in ["QPushButton", "QLabel", "QLineEdit", "QComboBox"]) and not any(token in text for token in ["setAccessibleName", "setAccessibleDescription"]):
            findings.append(_finding(
                "pyqt_missing_accessible_metadata",
                "warning",
                "PyQt widgets may lack accessible names/descriptions",
                f"File {_safe_rel(path, root)} uses Qt widgets without obvious setAccessibleName/setAccessibleDescription calls.",
                _safe_rel(path, root),
                "Add setAccessibleName/setAccessibleDescription to important custom or ambiguous widgets.",
                "pyqt",
                wcag="4.1.2 Name, Role, Value",
            ))
    return findings


def _scan_wpf(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.xaml"], limit=60):
        text = _read_text(path)
        if re.search(r"<(Button|TextBox|ComboBox|Image)\b", text) and "AutomationProperties.Name=" not in text:
            findings.append(_finding(
                "wpf_missing_automation_name",
                "warning",
                "WPF control may lack AutomationProperties.Name",
                f"XAML file {_safe_rel(path, root)} includes interactive controls without obvious AutomationProperties.Name usage.",
                _safe_rel(path, root),
                "Add AutomationProperties.Name (and HelpText where useful) to controls that need explicit screen-reader naming.",
                "wpf",
                wcag="4.1.2 Name, Role, Value",
            ))
    return findings


def _scan_ios(root: Path) -> List[Dict[str, Any]]:
    findings = []
    for path in _collect_files(root, ["*.swift", "*.storyboard", "*.xib"], limit=60):
        text = _read_text(path)
        rel = _safe_rel(path, root)

        if any(token in text for token in ["UIImageView", "UIButton", "UILabel", "UITextField", "UIBarButtonItem"]) and "accessibilityLabel" not in text and ".accessibilityLabel(" not in text:
            _append_once(findings, _finding(
                "ios_missing_accessibility_label_review",
                "warning",
                "iOS UI file should be reviewed for accessibility labels",
                f"File {rel} contains UI code without obvious accessibilityLabel usage.",
                rel,
                "Review buttons/images/custom controls and add accessibilityLabel / accessibilityIdentifier where needed.",
                "ios",
                wcag="4.1.2 Name, Role, Value",
                line=_line_number(text, "UIButton") or _line_number(text, "UIImageView") or _line_number(text, "UITextField"),
                requires_manual_check=True,
            ))

        for needle, rule_id, title, recommendation in [
            ("isAccessibilityElement = false", "ios_accessibility_element_false_review", "isAccessibilityElement set to false", "Verify meaningful content is not hidden from VoiceOver when disabling accessibility elements."),
            (".accessibilityHidden(true)", "ios_accessibility_hidden_review", "SwiftUI accessibilityHidden(true) usage", "Review accessibilityHidden(true) to ensure important content is not hidden from VoiceOver."),
        ]:
            if needle in text:
                _append_once(findings, _finding(
                    rule_id,
                    "info",
                    title,
                    f"Accessibility visibility override found in {rel}; review whether important content is being hidden.",
                    rel,
                    recommendation,
                    "ios",
                    wcag="4.1.2 Name, Role, Value",
                    line=_line_number(text, needle),
                    requires_manual_check=True,
                ))

        for needle, rule_id, title in [
            ("UIButton(", "ios_button_missing_accessibility_review", "UIButton should be reviewed for accessibility labeling"),
            ("UIBarButtonItem(", "ios_barbutton_missing_accessibility_review", "UIBarButtonItem should be reviewed for accessibility labeling"),
            ("UITextField(", "ios_textfield_missing_accessibility_review", "UITextField should be reviewed for labels and hints"),
            ("Image(", "ios_swiftui_image_missing_accessibility_review", "SwiftUI Image should be reviewed for accessibility labeling"),
            ("Button(", "ios_swiftui_button_missing_accessibility_review", "SwiftUI Button should be reviewed for accessible naming"),
        ]:
            if needle in text:
                has_nearby_accessibility = any(token in text for token in ["accessibilityLabel", ".accessibilityLabel(", ".accessibilityHint(", ".accessibilityIdentifier("])
                if not has_nearby_accessibility:
                    _append_once(findings, _finding(
                        rule_id,
                        "warning",
                        title,
                        f"UI control construction found in {rel} without obvious nearby accessibility metadata.",
                        rel,
                        "Review accessible labels, hints, and traits for this control.",
                        "ios",
                        wcag="4.1.2 Name, Role, Value",
                        line=_line_number(text, needle),
                        requires_manual_check=True,
                    ))
    return findings


def audit_project_path(project_path: str) -> Dict[str, Any]:
    detection = detect_target_type(project_path)
    root = Path(detection["path"])
    platform = detection["platform"]

    findings: List[Dict[str, Any]] = []
    if platform == "android":
        findings.extend(_scan_android(root))
    elif platform == "flutter":
        findings.extend(_scan_flutter(root))
    elif platform == "react-native":
        findings.extend(_scan_react_native(root))
    elif platform == "electron":
        findings.extend(_scan_electron_or_web(root, "electron"))
    elif platform == "pyqt":
        findings.extend(_scan_pyqt(root))
    elif platform == "wpf":
        findings.extend(_scan_wpf(root))
    elif platform == "ios":
        findings.extend(_scan_ios(root))
    elif platform == "web":
        findings.extend(_scan_electron_or_web(root, "web"))
    else:
        findings.append(_finding(
            "unknown_platform_manual_review",
            "info",
            "Project platform could not be classified confidently",
            f"Could not confidently classify project at {root}.",
            None,
            "Review the project structure manually or add platform-specific detection rules.",
            "unknown",
            requires_manual_check=True,
            confidence="low",
        ))

    findings = _enumerate_findings(findings)
    critical = sum(1 for item in findings if item["severity"] == "critical")
    warning = sum(1 for item in findings if item["severity"] == "warning")
    info = sum(1 for item in findings if item["severity"] == "info")
    score = max(0, 100 - critical * 10 - warning * 5 - info)
    grade = "A (Excellent)" if score >= 90 else "B (Good)" if score >= 80 else "C (Fair)" if score >= 70 else "D (Poor)" if score >= 60 else "F (Fail)"
    overall = (
        "Есть критические статические сигналы доступности в проекте." if critical else
        "Найдены предупреждения и платформо-специфичные риски, которые стоит проверить перед релизом." if warning else
        "Критических статических сигналов не найдено, но всё равно требуется ручная проверка с ассистивными технологиями."
    )
    next_steps = []
    for item in findings:
        rec = item.get("recommendation")
        if rec and rec not in next_steps:
            next_steps.append(rec)
        if len(next_steps) >= 5:
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "schema_id": SCHEMA_ID,
        "target": {"type": "project_path", "value": str(root)},
        "platform": platform,
        "mode": "full",
        "score": score,
        "grade": grade,
        "summary": {
            "overall_assessment": overall,
            "critical": critical,
            "warning": warning,
            "info": info,
            "detected_platform": platform,
            "detection_confidence": detection["confidence"],
            "candidate_platforms": detection["candidate_platforms"],
        },
        "detection": detection,
        "findings": findings,
        "manual_checks": [
            "Проверить реальный UI с screen reader на целевой платформе.",
            "Проверить порядок фокуса, озвучивание динамических состояний и touch target size в рантайме.",
        ],
        "next_steps": next_steps or ["Провести ручную accessibility-проверку на целевой платформе."],
        "mcp_payload": {
            "schema_version": SCHEMA_VERSION,
            "schema_id": SCHEMA_ID,
            "tool_name": "audit_project_path",
            "target": {"type": "project_path", "value": str(root)},
            "summary": {
                "score": score,
                "grade": grade,
                "total_findings": len(findings),
                "critical": critical,
                "warning": warning,
                "info": info,
                "overall_assessment": overall,
                "detected_platform": platform,
                "detection_confidence": detection["confidence"],
            },
            "detection": detection,
            "findings": findings,
            "manual_checks": [
                "Проверить реальный UI с screen reader на целевой платформе.",
                "Проверить порядок фокуса, озвучивание динамических состояний и touch target size в рантайме.",
            ],
            "next_steps": next_steps or ["Провести ручную accessibility-проверку на целевой платформе."],
        },
    }


def _sarif_level(severity: str) -> str:
    return {"critical": "error", "warning": "warning", "info": "note"}.get(severity, "note")


def _sarif_rule(finding: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": finding["rule_id"],
        "name": finding["title"],
        "shortDescription": {"text": finding["title"]},
        "fullDescription": {"text": finding.get("description") or finding.get("message") or finding["title"]},
        "help": {"text": finding.get("recommendation") or "Review this accessibility issue."},
        "properties": {
            "platform": finding.get("platform"),
            "confidence": finding.get("confidence"),
            "requires_manual_check": finding.get("requires_manual_check"),
            "wcag": (finding.get("standards") or {}).get("wcag"),
        },
    }


def export_report_to_sarif(report: Dict[str, Any], tool_name: str = "accessibility-auditor") -> Dict[str, Any]:
    findings = report.get("findings") or []
    rules = {}
    results = []
    for finding in findings:
        rules[finding["rule_id"]] = _sarif_rule(finding)
        result = {
            "ruleId": finding["rule_id"],
            "level": _sarif_level(finding["severity"]),
            "message": {"text": finding.get("message") or finding.get("title")},
            "properties": {
                "platform": finding.get("platform"),
                "severity": finding.get("severity"),
                "confidence": finding.get("confidence"),
                "requires_manual_check": finding.get("requires_manual_check"),
                "recommendation": finding.get("recommendation"),
                "wcag": (finding.get("standards") or {}).get("wcag"),
            },
        }
        if finding.get("file_path"):
            location = {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding["file_path"]},
                }
            }
            if finding.get("line"):
                location["physicalLocation"]["region"] = {"startLine": finding["line"]}
            result["locations"] = [location]
        results.append(result)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "informationUri": SCHEMA_ID,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }


def export_project_path_to_sarif(project_path: str) -> Dict[str, Any]:
    report = audit_project_path(project_path)
    return export_report_to_sarif(report, tool_name="accessibility-auditor-project")


def export_many_projects_to_sarif(project_paths: List[str]) -> Dict[str, Any]:
    runs = []
    for project_path in project_paths:
        report = audit_project_path(project_path)
        sarif = export_report_to_sarif(report, tool_name="accessibility-auditor-project")
        run = sarif["runs"][0]
        run.setdefault("properties", {})["project_path"] = project_path
        runs.append(run)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": runs,
    }


def detect_many_target_types(project_paths: List[str]) -> Dict[str, Any]:
    results = []
    for project_path in project_paths:
        try:
            results.append({"path": project_path, "ok": True, "result": detect_target_type(project_path)})
        except Exception as exc:
            results.append({"path": project_path, "ok": False, "error": str(exc)})
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_id": SCHEMA_ID,
        "tool_name": "detect_many_target_types",
        "count": len(results),
        "results": results,
    }


def audit_many_project_paths(project_paths: List[str]) -> Dict[str, Any]:
    results = []
    summary = {"critical": 0, "warning": 0, "info": 0, "audited": 0, "failed": 0}
    for project_path in project_paths:
        try:
            report = audit_project_path(project_path)
            payload = report["mcp_payload"]
            results.append({"path": project_path, "ok": True, "result": payload})
            summary["critical"] += payload["summary"]["critical"]
            summary["warning"] += payload["summary"]["warning"]
            summary["info"] += payload["summary"]["info"]
            summary["audited"] += 1
        except Exception as exc:
            results.append({"path": project_path, "ok": False, "error": str(exc)})
            summary["failed"] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_id": SCHEMA_ID,
        "tool_name": "audit_many_project_paths",
        "count": len(results),
        "summary": summary,
        "results": results,
    }


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(audit_project_path(path), ensure_ascii=False, indent=2))
