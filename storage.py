#!/usr/bin/env python3
"""
Storage module for audit results
Saves and retrieves audit reports in .md format
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4


class AuditStorage:
    """Manages audit result storage"""
    
    def __init__(self, storage_dir: str = "audits"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
    
    def generate_id(self) -> str:
        """Generate unique audit ID"""
        return str(uuid4())[:8]
    
    def save_audit_with_id(self, audit_id: str, report: Dict, is_public: bool = False) -> str:
        """Save audit report with a pre-generated ID"""
        markdown = self._report_to_markdown(report)
        file_path = self.storage_dir / f"audit_{audit_id}.md"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        report['is_public'] = is_public
        json_path = self.storage_dir / f"audit_{audit_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return audit_id

    def save_audit(self, report: Dict, is_public: bool = False) -> str:
        """
        Save audit report as markdown
        Args:
            report: audit report dict
            is_public: whether to show in public audits list
        Returns: audit ID
        """
        audit_id = self.generate_id()
        markdown = self._report_to_markdown(report)
        
        file_path = self.storage_dir / f"audit_{audit_id}.md"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        # Add public flag to report
        report['is_public'] = is_public
        
        # Also save raw JSON for API
        json_path = self.storage_dir / f"audit_{audit_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return audit_id
    
    def get_audit_path(self, audit_id: str) -> Path:
        """Get markdown file path for audit"""
        return self.storage_dir / f"audit_{audit_id}.md"
    
    def get_audit(self, audit_id: str) -> Optional[Dict]:
        """Get audit report by ID"""
        json_path = self.storage_dir / f"audit_{audit_id}.json"
        
        if not json_path.exists():
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_site_audit_with_id(self, site_audit_id: str, report: Dict, is_public: bool = False) -> str:
        """Save a multi-page site audit without changing single-page filenames."""
        report['is_public'] = is_public
        markdown = self.site_report_to_markdown(report)
        md_path = self.storage_dir / f"site_audit_{site_audit_id}.md"
        json_path = self.storage_dir / f"site_audit_{site_audit_id}.json"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return site_audit_id

    def save_site_audit(self, report: Dict, is_public: bool = False) -> str:
        site_audit_id = report.get('site_audit_id') or f"site_{self.generate_id()}"
        report['site_audit_id'] = site_audit_id
        return self.save_site_audit_with_id(site_audit_id, report, is_public=is_public)

    def get_site_audit(self, site_audit_id: str) -> Optional[Dict]:
        json_path = self.storage_dir / f"site_audit_{site_audit_id}.json"
        if not json_path.exists():
            return None
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_pending_escrow(self, escrow_id: str, data: Dict) -> str:
        """Persist a live escrow before doing paid work so recovery can release/refund."""
        pending_dir = self.storage_dir / "pending_escrows"
        pending_dir.mkdir(exist_ok=True)
        safe_id = escrow_id.replace("/", "_")
        payload = dict(data)
        payload.setdefault('updated_at', datetime.now().isoformat())
        with open(pending_dir / f"{safe_id}.json", 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return escrow_id

    def get_pending_escrow(self, escrow_id: str) -> Optional[Dict]:
        pending_dir = self.storage_dir / "pending_escrows"
        safe_id = escrow_id.replace("/", "_")
        path = pending_dir / f"{safe_id}.json"
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def mark_escrow_released(self, escrow_id: str, release_data: Dict) -> None:
        pending = self.get_pending_escrow(escrow_id) or {}
        pending.update(release_data)
        pending['status'] = release_data.get('status', 'released')
        pending['updated_at'] = datetime.now().isoformat()
        self.save_pending_escrow(escrow_id, pending)
    
    def _report_to_markdown(self, report: Dict) -> str:
        """Convert audit report to markdown format"""
        lines = []
        
        # Header
        lines.append(f"# Accessibility Audit Report")
        lines.append("")
        lines.append(f"**URL:** {report['url']}")
        lines.append(f"**Date:** {report['timestamp']}")
        lines.append("")
        
        # Score
        lines.append(f"## Results")
        lines.append("")
        lines.append(f"**Score:** {report['score']}/100")
        lines.append(f"**Grade:** {report['grade']}")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Issues:** {report['total_issues']}")
        lines.append(f"- **Critical:** {report['critical']}")
        lines.append(f"- **Warnings:** {report['warnings']}")
        lines.append(f"- **Info:** {report['info']}")
        lines.append("")
        
        # Issues by category
        if report['issues_by_category']:
            lines.append("## Issues by Category")
            lines.append("")
            
            for category, issues in report['issues_by_category'].items():
                lines.append(f"### {category}")
                lines.append("")
                
                for issue in issues:
                    severity_emoji = {
                        'critical': '🔴',
                        'warning': '🟡',
                        'info': '🔵'
                    }.get(issue['severity'], '⚪')
                    
                    lines.append(f"{severity_emoji} **{issue['severity'].upper()}**: {issue['title']}")
                    lines.append(f"  - {issue['description']}")
                    
                    if issue['element']:
                        lines.append(f"  - Element: {issue['element']}")
                    
                    if issue['recommendation']:
                        lines.append(f"  - Recommendation: {issue['recommendation']}")
                    
                    lines.append("")
        else:
            lines.append("✅ No accessibility issues found!")
            lines.append("")
        
        return "\n".join(lines)

    def site_report_to_markdown(self, report: Dict) -> str:
        """Convert a multi-page site report to compact markdown."""
        summary = report.get('summary', {})
        lines = [
            "# Multi-Page Accessibility Audit Report",
            "",
            f"**Root URL:** {report.get('root_url', report.get('url', 'N/A'))}",
            f"**Date:** {report.get('timestamp', '')}",
            f"**Score:** {report.get('score', 0)}/100 ({report.get('grade', 'N/A')})",
            "",
            "## Summary",
            "",
            f"- **Pages audited:** {summary.get('pages_audited', 0)}",
            f"- **Pages failed:** {summary.get('pages_failed', 0)}",
            f"- **Critical:** {report.get('critical', 0)}",
            f"- **Warnings:** {report.get('warnings', 0)}",
            f"- **Info:** {report.get('info', 0)}",
            f"- **Assessment:** {summary.get('overall_assessment', '')}",
            "",
            "## Repeated Issues",
            "",
        ]
        for issue in report.get('repeated_issues', [])[:20]:
            lines.append(f"- **{issue.get('severity', 'info').upper()}** {issue.get('title')} — {issue.get('affected_pages')} pages")
            examples = issue.get('example_urls') or []
            if examples:
                lines.append(f"  - Examples: {', '.join(examples[:3])}")
        lines.extend(["", "## Worst Pages", ""])
        for page in report.get('worst_pages', [])[:10]:
            lines.append(f"- {page.get('url')} — score {page.get('score')}, critical {page.get('critical')}, warnings {page.get('warnings')}")
        return "\n".join(lines)
    
    def list_audits(self, limit: int = 10, public_only: bool = False) -> list:
        """
        List recent audits
        Args:
            limit: max number of audits to return
            public_only: only return audits marked as public
        """
        json_files = sorted(
            self.storage_dir.glob("audit_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        audits = []
        for json_file in json_files:
            audit_id = json_file.stem.replace("audit_", "")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                continue
            
            # Filter by public status if needed
            if public_only and not data.get('is_public', False):
                continue
            
            audits.append({
                'id': audit_id,
                'url': data['url'],
                'score': data['score'],
                'timestamp': data['timestamp'],
                'grade': data['grade'],
                'is_public': data.get('is_public', False)
            })
            
            if len(audits) >= limit:
                break
        
        return audits


if __name__ == '__main__':
    # Test
    storage = AuditStorage()
    
    test_report = {
        'url': 'https://example.com',
        'timestamp': datetime.now().isoformat(),
        'score': 75,
        'total_issues': 5,
        'critical': 1,
        'warnings': 2,
        'info': 2,
        'grade': 'C (Fair)',
        'issues_by_category': {
            'Images': [
                {
                    'severity': 'critical',
                    'title': '2 images missing alt text',
                    'description': 'Found 2 images without alt attribute',
                    'element': 'logo.png',
                    'recommendation': 'Add descriptive alt text to all images'
                }
            ]
        }
    }
    
    audit_id = storage.save_audit(test_report)
    print(f"Saved audit: {audit_id}")
    print(f"Retrieved: {storage.get_audit(audit_id)}")
