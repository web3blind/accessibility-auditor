#!/usr/bin/env python3
"""CLI for accessibility-auditor.

Run audits and export results in multiple formats without setting up an MCP server.

Examples:
    # Audit a local project and print JSON
    python cli.py audit ./my-project

    # Audit and generate PR comment markdown
    python cli.py audit ./my-project --format pr-markdown -o comment.md

    # Audit a URL
    python cli.py audit-url https://example.com --format json

    # CI summary with fail threshold (exit 1 if score < 70 or critical > 0)
    python cli.py audit ./my-project --format ci-summary --fail-threshold 70

    # Batch audit multiple projects
    python cli.py audit ./project-a ./project-b --format pr-markdown

    # SARIF export for CI integration
    python cli.py audit ./my-project --format sarif -o results.sarif.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from auditor import audit_html_content, audit_html_file, audit_website
from project_auditor import (
    audit_many_project_paths,
    audit_project_path,
    export_many_projects_to_sarif,
    export_project_path_to_sarif,
)
from review_exporter import (
    export_many_projects_to_ci_summary,
    export_many_projects_to_github_annotations,
    export_many_projects_to_pr_markdown,
    export_project_path_to_ci_summary,
    export_project_path_to_github_annotations,
    export_project_path_to_pr_markdown,
    export_report_to_ci_summary,
    export_report_to_github_annotations,
    export_report_to_pr_markdown,
)


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _write_or_print(text: str, output: Optional[str], quiet: bool = False) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
        if not quiet:
            print(f"Wrote {len(text)} characters to {output}")
    else:
        print(text)


def _exit_code_for_report(report: Dict[str, Any], fail_threshold: int) -> int:
    score = report.get("score", 100)
    critical = report.get("summary", {}).get("critical", 0)
    if score < fail_threshold or critical > 0:
        return 1
    return 0


async def _audit_url(url: str, fmt: str, output: Optional[str], quiet: bool) -> int:
    report = await audit_website(url)
    return _render_and_exit(report, fmt, output, quiet, fail_threshold=0)


def _audit_html_file(file_path: str, fmt: str, output: Optional[str], quiet: bool) -> int:
    report = audit_html_file(file_path)
    return _render_and_exit(report, fmt, output, quiet, fail_threshold=0)


def _audit_html(html: str, fmt: str, output: Optional[str], quiet: bool) -> int:
    report = audit_html_content(html, source_name="cli-inline")
    return _render_and_exit(report, fmt, output, quiet, fail_threshold=0)


def _render_report(report: Dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return _json_dump(report)
    if fmt == "sarif":
        return _json_dump(export_project_path_to_sarif(report.get("target", {}).get("value", ".")))
    if fmt == "pr-markdown":
        return export_report_to_pr_markdown(report)
    if fmt == "ci-summary":
        return export_report_to_ci_summary(report)
    if fmt == "github-annotations":
        return export_report_to_github_annotations(report.get("findings") or [])
    raise ValueError(f"Unknown format: {fmt}")


def _render_and_exit(
    report: Dict[str, Any],
    fmt: str,
    output: Optional[str],
    quiet: bool,
    fail_threshold: int,
) -> int:
    try:
        text = _render_report(report, fmt)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    _write_or_print(text, output, quiet=quiet)
    return _exit_code_for_report(report, fail_threshold)


def _audit_project(
    paths: List[str],
    fmt: str,
    output: Optional[str],
    quiet: bool,
    fail_threshold: int,
    max_files: int,
    max_findings: int,
) -> int:
    if len(paths) == 1:
        report = audit_project_path(paths[0])
        if fmt == "json":
            text = _json_dump(report)
        elif fmt == "sarif":
            text = _json_dump(export_project_path_to_sarif(paths[0]))
        elif fmt == "pr-markdown":
            text = export_project_path_to_pr_markdown(paths[0], max_files_shown=max_files, max_findings_per_file=max_findings)
        elif fmt == "ci-summary":
            text = export_project_path_to_ci_summary(paths[0], fail_threshold_score=fail_threshold)
        elif fmt == "github-annotations":
            text = export_project_path_to_github_annotations(paths[0])
        else:
            print(f"Error: Unknown format: {fmt}", file=sys.stderr)
            return 2
        _write_or_print(text, output, quiet=quiet)
        return _exit_code_for_report(report, fail_threshold)
    else:
        # Batch
        if fmt == "json":
            result = audit_many_project_paths(paths)
            text = _json_dump(result)
        elif fmt == "sarif":
            text = _json_dump(export_many_projects_to_sarif(paths))
        elif fmt == "pr-markdown":
            text = export_many_projects_to_pr_markdown(paths, max_files_shown=max_files, max_findings_per_file=max_findings)
        elif fmt == "ci-summary":
            text = export_many_projects_to_ci_summary(paths, fail_threshold_score=fail_threshold)
        elif fmt == "github-annotations":
            text = export_many_projects_to_github_annotations(paths)
        else:
            print(f"Error: Unknown format: {fmt}", file=sys.stderr)
            return 2
        _write_or_print(text, output, quiet=quiet)
        # Determine exit code from worst project
        worst = 0
        for path in paths:
            try:
                report = audit_project_path(path)
                code = _exit_code_for_report(report, fail_threshold)
                if code > worst:
                    worst = code
            except Exception:
                worst = 1
        return worst


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="accessibility-auditor",
        description="Accessibility audit CLI — local, privacy-first, no MCP required.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    sub = parser.add_subparsers(dest="command", required=True)

    # audit project(s)
    audit_parser = sub.add_parser("audit", help="Audit one or more local project directories.")
    audit_parser.add_argument("paths", nargs="+", help="Project path(s) to audit.")
    audit_parser.add_argument(
        "--format",
        choices=["json", "sarif", "pr-markdown", "ci-summary", "github-annotations"],
        default="json",
        help="Output format (default: json)",
    )
    audit_parser.add_argument("-o", "--output", help="Write output to file instead of stdout.")
    audit_parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    audit_parser.add_argument(
        "--fail-threshold",
        type=int,
        default=60,
        help="Exit with non-zero if score < threshold or any critical issues exist (default: 60).",
    )
    audit_parser.add_argument(
        "--max-files",
        type=int,
        default=30,
        help="Max files shown in pr-markdown (default: 30).",
    )
    audit_parser.add_argument(
        "--max-findings",
        type=int,
        default=8,
        help="Max findings per file in pr-markdown (default: 8).",
    )

    # audit URL
    url_parser = sub.add_parser("audit-url", help="Audit a public URL.")
    url_parser.add_argument("url", help="URL to audit.")
    url_parser.add_argument(
        "--format",
        choices=["json", "pr-markdown", "ci-summary"],
        default="json",
        help="Output format (default: json)",
    )
    url_parser.add_argument("-o", "--output", help="Write output to file instead of stdout.")
    url_parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")

    # audit HTML file
    html_file_parser = sub.add_parser("audit-html-file", help="Audit a local HTML file.")
    html_file_parser.add_argument("file_path", help="Path to HTML file.")
    html_file_parser.add_argument(
        "--format",
        choices=["json", "pr-markdown", "ci-summary"],
        default="json",
        help="Output format (default: json)",
    )
    html_file_parser.add_argument("-o", "--output", help="Write output to file instead of stdout.")
    html_file_parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")

    # audit raw HTML
    html_parser = sub.add_parser("audit-html", help="Audit raw HTML passed as argument or stdin.")
    html_parser.add_argument("html", nargs="?", help="HTML string. If omitted, reads from stdin.")
    html_parser.add_argument(
        "--format",
        choices=["json", "pr-markdown", "ci-summary"],
        default="json",
        help="Output format (default: json)",
    )
    html_parser.add_argument("-o", "--output", help="Write output to file instead of stdout.")
    html_parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        return _audit_project(
            paths=args.paths,
            fmt=args.format,
            output=args.output,
            quiet=args.quiet,
            fail_threshold=args.fail_threshold,
            max_files=args.max_files,
            max_findings=args.max_findings,
        )
    elif args.command == "audit-url":
        return asyncio.run(_audit_url(args.url, args.format, args.output, args.quiet))
    elif args.command == "audit-html-file":
        return _audit_html_file(args.file_path, args.format, args.output, args.quiet)
    elif args.command == "audit-html":
        html = args.html
        if html is None:
            html = sys.stdin.read()
        return _audit_html(html, args.format, args.output, args.quiet)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
