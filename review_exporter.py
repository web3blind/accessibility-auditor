#!/usr/bin/env python3
"""PR / CI review exporters for accessibility audit findings.

Produces GitHub/GitLab-friendly markdown suitable for:
- pull-request comments / review threads
- CI job summaries (e.g. GitHub Actions step summary)
- inline code-review annotations (per-file grouped)

Privacy model:
- No source code is embedded in output — only file paths, line numbers, and recommendations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from project_auditor import audit_many_project_paths, audit_project_path

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
SEVERITY_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _escape_md(text: str) -> str:
    """Minimal Markdown escape for table cells and inline text."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def _format_badge(severity: str) -> str:
    color = {"critical": "red", "warning": "yellow", "info": "blue"}.get(severity, "lightgrey")
    label = SEVERITY_LABEL.get(severity, severity.upper())
    return f"![{label}](https://img.shields.io/badge/{label}-{color})"


def _grade_badge(grade: str) -> str:
    color_map = {
        "A (Excellent)": "brightgreen",
        "B (Good)": "green",
        "C (Fair)": "yellow",
        "D (Poor)": "orange",
        "F (Fail)": "red",
    }
    for key, color in color_map.items():
        if key in grade:
            short = grade.split()[0]
            return f"![Grade {short}](https://img.shields.io/badge/Grade-{short}-{color})"
    short = grade.split()[0] if grade else "?"
    return f"![Grade {short}](https://img.shields.io/badge/Grade-{short}-lightgrey)"


def _group_findings_by_file(findings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in findings:
        fp = item.get("file_path") or "(unknown file)"
        groups.setdefault(fp, []).append(item)
    # sort files by highest severity first, then by path
    for fp in groups:
        groups[fp].sort(key=lambda x: SEVERITY_ORDER.get(x.get("severity"), 99))
    sorted_keys = sorted(
        groups.keys(),
        key=lambda fp: (
            min(SEVERITY_ORDER.get(x.get("severity"), 99) for x in groups[fp]),
            fp,
        ),
    )
    return {k: groups[k] for k in sorted_keys}


def _generate_per_file_markdown(findings: List[Dict[str, Any]], root_path: Optional[str] = None) -> str:
    groups = _group_findings_by_file(findings)
    if not groups:
        return "_No file-specific findings._\n"

    lines: List[str] = []
    for fp, items in groups.items():
        display_fp = fp
        if root_path and fp.startswith(root_path):
            display_fp = fp[len(root_path):].lstrip("/")
        header = f"#### `{_escape_md(display_fp)}`"
        lines.append(header)
        for item in items:
            sev = item.get("severity", "info")
            emoji = SEVERITY_EMOJI.get(sev, "•")
            title = _escape_md(item.get("title", "Issue"))
            rule = item.get("rule_id", "")
            line_no = item.get("line")
            loc = f"line {line_no}" if line_no else "location unknown"
            msg = _escape_md(item.get("message", ""))
            rec = _escape_md(item.get("recommendation", ""))
            wcag = item.get("standards", {}).get("wcag") or ""
            wcag_tag = f"`{wcag}`" if wcag else ""
            lines.append(
                f"{emoji} **{title}** (`{rule}`) — *{loc}* {wcag_tag}\n"
                f"   - {msg}\n"
                f"   - 💡 *Fix:* {rec}\n"
            )
        lines.append("")
    return "\n".join(lines)


def export_report_to_pr_markdown(
    report: Dict[str, Any],
    tool_name: str = "accessibility-auditor",
    max_files_shown: int = 30,
    max_findings_per_file: int = 8,
) -> str:
    """Generate a GitHub/GitLab-friendly PR comment markdown from an audit report."""
    summary = report.get("summary", {})
    findings = report.get("findings") or []
    platform = report.get("platform", "unknown")
    score = report.get("score", 0)
    grade = report.get("grade", "N/A")
    target = report.get("target", {})
    target_value = target.get("value", "unknown")
    root_path = target_value if isinstance(target_value, str) else None

    critical = summary.get("critical", sum(1 for f in findings if f.get("severity") == "critical"))
    warning = summary.get("warning", sum(1 for f in findings if f.get("severity") == "warning"))
    info = summary.get("info", sum(1 for f in findings if f.get("severity") == "info"))
    overall = summary.get("overall_assessment", "")
    next_steps = report.get("next_steps") or []
    manual_checks = report.get("manual_checks") or []

    # Truncate findings per-file for PR brevity
    groups = _group_findings_by_file(findings)
    shown_findings: List[Dict[str, Any]] = []
    hidden_count = 0
    for idx, (fp, items) in enumerate(groups.items()):
        if idx >= max_files_shown:
            hidden_count += len(items)
            continue
        shown = items[:max_findings_per_file]
        hidden_count += max(0, len(items) - max_findings_per_file)
        shown_findings.extend(shown)

    lines: List[str] = []
    lines.append(f"## ♿ Accessibility Audit — {tool_name}")
    lines.append("")
    lines.append(f"**Target:** `{_escape_md(str(target_value))}`  ")
    lines.append(f"**Platform:** `{platform}`  ")
    lines.append(f"**Score:** {score}/100  {_grade_badge(grade)}")
    lines.append("")

    # Quick stats table
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| 🔴 Critical | {critical} |")
    lines.append(f"| 🟡 Warning | {warning} |")
    lines.append(f"| 🔵 Info | {info} |")
    lines.append("")

    if overall:
        lines.append(f"**Assessment:** {overall}")
        lines.append("")

    # Per-file grouped findings
    lines.append("### 📁 Findings by File")
    lines.append("")
    if shown_findings:
        file_md = _generate_per_file_markdown(shown_findings, root_path=root_path)
        lines.append(file_md)
    else:
        lines.append("_No findings to display._")
    lines.append("")

    if hidden_count:
        lines.append(f"> ⚠️ {hidden_count} additional finding(s) were truncated for brevity. Run the full audit locally to see everything.")
        lines.append("")

    # Next steps
    if next_steps:
        lines.append("### 🛠️ Recommended Next Steps")
        lines.append("")
        for step in next_steps[:7]:
            lines.append(f"- {step}")
        lines.append("")

    # Manual checks
    if manual_checks:
        lines.append("### 👀 Manual Verification Required")
        lines.append("")
        lines.append("> ⚠️ Static analysis can only detect ~40–60 % of accessibility issues. "
                   "The following always require runtime / device testing:\n")
        for check in manual_checks[:5]:
            lines.append(f"- {check}")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by accessibility-auditor. This comment contains only metadata and recommendations — no source code._")
    return "\n".join(lines)


def export_project_path_to_pr_markdown(project_path: str, **kwargs: Any) -> str:
    report = audit_project_path(project_path)
    return export_report_to_pr_markdown(report, tool_name="accessibility-auditor-project", **kwargs)


def export_many_projects_to_pr_markdown(
    project_paths: List[str],
    max_files_shown: int = 20,
    max_findings_per_file: int = 5,
) -> str:
    lines: List[str] = []
    lines.append("## ♿ Accessibility Audit — Multi-Project Summary")
    lines.append("")

    total_critical = 0
    total_warning = 0
    total_info = 0
    total_audited = 0

    for path in project_paths:
        try:
            report = audit_project_path(path)
            summary = report.get("summary", {})
            critical = summary.get("critical", 0)
            warning = summary.get("warning", 0)
            info = summary.get("info", 0)
            total_critical += critical
            total_warning += warning
            total_info += info
            total_audited += 1

            score = report.get("score", 0)
            grade = report.get("grade", "N/A")
            platform = report.get("platform", "unknown")
            findings = report.get("findings") or []

            lines.append(f"### `{_escape_md(path)}`")
            lines.append(f"- Platform: `{platform}` | Score: {score}/100 | Grade: {grade}")
            lines.append(f"- 🔴 {critical} 🟡 {warning} 🔵 {info}")
            lines.append("")

            if findings:
                groups = _group_findings_by_file(findings)
                for idx, (fp, items) in enumerate(groups.items()):
                    if idx >= max_files_shown:
                        lines.append(f"_… and {len(groups) - max_files_shown} more file(s)_")
                        break
                    display_fp = fp.replace(path, "").lstrip("/") if fp.startswith(path) else fp
                    lines.append(f"**`{_escape_md(display_fp)}`**")
                    for item in items[:max_findings_per_file]:
                        sev = item.get("severity", "info")
                        emoji = SEVERITY_EMOJI.get(sev, "•")
                        title = _escape_md(item.get("title", "Issue"))
                        line_no = item.get("line")
                        loc = f":{line_no}" if line_no else ""
                        rec = _escape_md(item.get("recommendation", ""))
                        lines.append(f"- {emoji} **{title}**{loc} — {rec}")
                    lines.append("")
            else:
                lines.append("_No findings._\n")
        except Exception as exc:
            lines.append(f"### `{_escape_md(path)}`")
            lines.append(f"⚠️ Audit failed: `{exc}`")
            lines.append("")

    lines.insert(2, "| Metric | Value |")
    lines.insert(3, "|--------|-------|")
    lines.insert(4, f"| Projects audited | {total_audited} |")
    lines.insert(5, f"| 🔴 Critical | {total_critical} |")
    lines.insert(6, f"| 🟡 Warning | {total_warning} |")
    lines.insert(7, f"| 🔵 Info | {total_info} |")
    lines.insert(8, "")

    lines.append("---")
    lines.append("_Generated by accessibility-auditor. This summary contains only metadata and recommendations — no source code._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CI Summary (compact, single-section, suitable for GitHub Actions step summary)
# ---------------------------------------------------------------------------


def export_report_to_ci_summary(
    report: Dict[str, Any],
    tool_name: str = "accessibility-auditor",
    fail_threshold_score: int = 60,
) -> str:
    """Generate a compact CI-friendly markdown summary (e.g. GitHub Actions job summary)."""
    summary = report.get("summary", {})
    findings = report.get("findings") or []
    platform = report.get("platform", "unknown")
    score = report.get("score", 0)
    grade = report.get("grade", "N/A")
    target = report.get("target", {})
    target_value = target.get("value", "unknown")

    critical = summary.get("critical", sum(1 for f in findings if f.get("severity") == "critical"))
    warning = summary.get("warning", sum(1 for f in findings if f.get("severity") == "warning"))
    info = summary.get("info", sum(1 for f in findings if f.get("severity") == "info"))

    status = "✅ PASS" if score >= fail_threshold_score and critical == 0 else "❌ FAIL"
    if score >= fail_threshold_score and critical > 0:
        status = "⚠️ WARN"

    lines: List[str] = []
    lines.append(f"# ♿ {tool_name} CI Summary")
    lines.append("")
    lines.append(f"**Status:** {status}  ")
    lines.append(f"**Target:** `{_escape_md(str(target_value))}`  ")
    lines.append(f"**Platform:** `{platform}`  ")
    lines.append(f"**Score:** {score}/100 ({grade})  ")
    lines.append(f"**Findings:** 🔴 {critical} critical | 🟡 {warning} warning | 🔵 {info} info")
    lines.append("")

    # Top critical/warning items only
    top = [f for f in findings if f.get("severity") in ("critical", "warning")]
    top.sort(key=lambda x: SEVERITY_ORDER.get(x.get("severity"), 99))
    if top:
        lines.append("## Top Issues")
        lines.append("")
        for item in top[:10]:
            sev = item.get("severity", "info")
            emoji = SEVERITY_EMOJI.get(sev, "•")
            title = _escape_md(item.get("title", "Issue"))
            fp = item.get("file_path", "")
            line_no = item.get("line")
            loc = f"`{fp}:{line_no}`" if fp and line_no else f"`{fp}`" if fp else ""
            rec = _escape_md(item.get("recommendation", ""))
            lines.append(f"- {emoji} **{title}** {loc}\n  - {rec}")
        lines.append("")
        if len(top) > 10:
            lines.append(f"_… and {len(top) - 10} more issue(s)_")
            lines.append("")
    else:
        lines.append("_No critical or warning issues found._")
        lines.append("")

    lines.append("---")
    lines.append("_Static analysis only. Full sign-off requires screen-reader and device testing._")
    return "\n".join(lines)


def export_project_path_to_ci_summary(project_path: str, **kwargs: Any) -> str:
    report = audit_project_path(project_path)
    return export_report_to_ci_summary(report, tool_name="accessibility-auditor-project", **kwargs)


def export_many_projects_to_ci_summary(
    project_paths: List[str],
    fail_threshold_score: int = 60,
) -> str:
    lines: List[str] = []
    lines.append("# ♿ Accessibility Auditor — Multi-Project CI Summary")
    lines.append("")

    total_critical = 0
    total_warning = 0
    total_info = 0
    total_audited = 0
    any_fail = False

    for path in project_paths:
        try:
            report = audit_project_path(path)
            summary = report.get("summary", {})
            critical = summary.get("critical", 0)
            warning = summary.get("warning", 0)
            info = summary.get("info", 0)
            score = report.get("score", 0)
            total_critical += critical
            total_warning += warning
            total_info += info
            total_audited += 1
            if score < fail_threshold_score or critical > 0:
                any_fail = True
        except Exception:
            any_fail = True

    status = "❌ FAIL" if any_fail else "✅ PASS"
    lines.append(f"**Overall Status:** {status}")
    lines.append(f"**Projects Audited:** {total_audited}")
    lines.append(f"**Total Findings:** 🔴 {total_critical} critical | 🟡 {total_warning} warning | 🔵 {total_info} info")
    lines.append("")

    # Per-project mini table
    lines.append("| Project | Platform | Score | 🔴 | 🟡 | 🔵 | Status |")
    lines.append("|---------|----------|-------|----|----|----|--------|")
    for path in project_paths:
        try:
            report = audit_project_path(path)
            summary = report.get("summary", {})
            critical = summary.get("critical", 0)
            warning = summary.get("warning", 0)
            info = summary.get("info", 0)
            score = report.get("score", 0)
            grade = report.get("grade", "N/A")
            platform = report.get("platform", "unknown")
            s = "❌" if score < fail_threshold_score or critical > 0 else "✅"
            lines.append(
                f"| `{_escape_md(path)}` | {platform} | {score} ({grade}) | {critical} | {warning} | {info} | {s} |"
            )
        except Exception as exc:
            lines.append(f"| `{_escape_md(path)}` | — | — | — | — | — | ❌ ({exc}) |")
    lines.append("")

    lines.append("---")
    lines.append("_Static analysis only. Full sign-off requires screen-reader and device testing._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub Actions workflow-command annotations
# ---------------------------------------------------------------------------


def _escape_workflow_command(text: str) -> str:
    """Escape special chars for GitHub Actions workflow commands.

    See: https://github.com/actions/toolkit/blob/main/docs/commands.md#workflow-commands
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _github_annotation_level(severity: str) -> str:
    return {"critical": "error", "warning": "warning", "info": "notice"}.get(severity, "notice")


def export_findings_to_github_annotations(
    findings: List[Dict[str, Any]],
    root_path: Optional[str] = None,
) -> str:
    """Generate GitHub Actions workflow-command annotations from findings.

    Output can be printed directly in a GitHub Actions step and will appear
    as inline annotations on the PR diff.
    """
    lines: List[str] = []
    for item in findings:
        sev = item.get("severity", "info")
        level = _github_annotation_level(sev)
        fp = item.get("file_path", "")
        line_no = item.get("line")
        title = _escape_workflow_command(item.get("title", "Accessibility issue"))
        msg = _escape_workflow_command(item.get("message", ""))
        rec = _escape_workflow_command(item.get("recommendation", ""))

        # Build command
        cmd_parts = [f"::{level}"]
        props = []
        if fp:
            display_fp = fp
            if root_path and fp.startswith(root_path):
                display_fp = fp[len(root_path):].lstrip("/")
            props.append(f"file={display_fp}")
        if line_no:
            props.append(f"line={line_no}")
        if title:
            props.append(f"title={title}")
        if props:
            cmd_parts.append(" ".join(props))
        cmd_parts.append("::")

        full_msg = msg
        if rec and rec != msg:
            full_msg = f"{msg} — Fix: {rec}"
        cmd_parts.append(full_msg)
        lines.append("".join(cmd_parts))
    return "\n".join(lines)


def export_report_to_github_annotations(
    report: Dict[str, Any],
    root_path: Optional[str] = None,
) -> str:
    """Generate GitHub Actions workflow-command annotations from an audit report."""
    findings = report.get("findings") or []
    return export_findings_to_github_annotations(findings, root_path=root_path)


def export_project_path_to_github_annotations(project_path: str) -> str:
    report = audit_project_path(project_path)
    return export_findings_to_github_annotations(report.get("findings") or [], root_path=project_path)


def export_many_projects_to_github_annotations(project_paths: List[str]) -> str:
    lines: List[str] = []
    for path in project_paths:
        try:
            ann = export_project_path_to_github_annotations(path)
            if ann:
                lines.append(ann)
        except Exception:
            lines.append(f"::error::Failed to audit {path}")
    return "\n".join(lines)
