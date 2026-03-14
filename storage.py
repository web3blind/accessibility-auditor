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
    
    def save_audit(self, report: Dict) -> str:
        """
        Save audit report as markdown
        Returns: audit ID
        """
        audit_id = self.generate_id()
        markdown = self._report_to_markdown(report)
        
        file_path = self.storage_dir / f"audit_{audit_id}.md"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        # Also save raw JSON for API
        json_path = self.storage_dir / f"audit_{audit_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return audit_id
    
    def get_audit(self, audit_id: str) -> Optional[Dict]:
        """Get audit report by ID"""
        json_path = self.storage_dir / f"audit_{audit_id}.json"
        
        if not json_path.exists():
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
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
    
    def list_audits(self, limit: int = 10) -> list:
        """List recent audits"""
        json_files = sorted(
            self.storage_dir.glob("audit_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]
        
        audits = []
        for json_file in json_files:
            audit_id = json_file.stem.replace("audit_", "")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            audits.append({
                'id': audit_id,
                'url': data['url'],
                'score': data['score'],
                'timestamp': data['timestamp'],
                'grade': data['grade']
            })
        
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
