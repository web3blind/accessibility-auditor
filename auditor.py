#!/usr/bin/env python3
"""
Accessibility Auditor - Web Accessibility Analysis Tool
Analyzes websites for WCAG 2.1 and Russian GOST R 52872-2019 compliance
"""

import asyncio
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import json
from datetime import datetime
import os
import sys
import subprocess
import tempfile


@dataclass
class AuditIssue:
    """Single accessibility issue found"""
    category: str
    severity: str  # critical, warning, info
    title: str
    description: str
    element: Optional[str] = None
    recommendation: Optional[str] = None


class AccessibilityAuditor:
    """Main auditor class"""
    
    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.html = None
        self.soup = None
        self.issues: List[AuditIssue] = []
        self.score = 0
        self.timestamp = datetime.now().isoformat()
        
    async def fetch_page(self) -> bool:
        """Fetch rendered HTML via headless Chromium running in a subprocess."""
        import os
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_page.py')
        python = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'bin', 'python3')
        if not os.path.exists(python):
            python = sys.executable

        try:
            proc = await asyncio.create_subprocess_exec(
                python, script, self.url, str(self.timeout),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout + 10
            )

            if proc.returncode == 0:
                self.html = stdout.decode('utf-8', errors='replace')
                self.soup = BeautifulSoup(self.html, 'html.parser')
                return True
            else:
                err = stderr.decode('utf-8', errors='replace').strip()
                # Parse error type from message
                if err.startswith('Timeout'):
                    title, desc = 'Timeout', err
                elif err.startswith('HTTP'):
                    title, desc = err.split(':', 1)[0].strip(), err
                else:
                    title, desc = 'Connection Error', err
                self.issues.append(AuditIssue(
                    category="Network", severity="critical",
                    title=title, description=desc
                ))
                return False

        except asyncio.TimeoutError:
            self.issues.append(AuditIssue(
                category="Network", severity="critical",
                title="Timeout",
                description=f"Page took longer than {self.timeout}s to load"
            ))
            return False
        except Exception as e:
            self.issues.append(AuditIssue(
                category="Network", severity="critical",
                title="Connection Error", description=str(e)
            ))
            return False

    async def audit(self) -> Dict:
        """Run full accessibility audit"""
        if not await self.fetch_page():
            return self.generate_report()
        
        # Run all checks
        self._check_semantic_html()
        self._check_images()
        self._check_links()
        self._check_headings()
        self._check_forms()
        self._check_contrast()
        self._check_keyboard_nav()
        self._check_aria()
        self._check_text_alternatives()
        self._check_page_structure()
        self._check_language()
        self._check_responsive_design()
        
        # Calculate score (100 - issues * weights)
        self._calculate_score()
        
        return self.generate_report()
    
    def _check_semantic_html(self):
        """Check for semantic HTML usage"""
        issues = 0
        total = 0
        
        # Check for divs used instead of semantic tags
        main_divs = self.soup.find_all('div', class_=re.compile(r'(main|header|footer|nav|article|section)', re.I))
        if main_divs:
            for div in main_divs[:3]:  # Show first 3
                self.issues.append(AuditIssue(
                    category="Semantic HTML",
                    severity="warning",
                    title="Non-semantic div used",
                    description=f"Div with class '{div.get('class', [''])[0]}' should use semantic tag",
                    element=str(div)[:50],
                    recommendation=f"Use <main>, <header>, <footer>, <nav>, <article>, or <section> instead"
                ))
                issues += 1
            total += 1
        
        # Check for missing lang attribute
        html_tag = self.soup.find('html')
        if not html_tag or not html_tag.get('lang'):
            self.issues.append(AuditIssue(
                category="Semantic HTML",
                severity="warning",
                title="Missing language declaration",
                description="<html> tag missing 'lang' attribute",
                recommendation="Add lang='en' to <html> tag"
            ))
    
    def _check_images(self):
        """Check image accessibility (alt text)"""
        images = self.soup.find_all('img')
        
        if not images:
            return
        
        missing_alt = []
        empty_alt = []
        
        for img in images:
            alt = img.get('alt', '').strip()
            src = img.get('src', 'unknown')
            
            if not alt:
                if 'alt' not in img.attrs:
                    missing_alt.append(src[:50])
                else:
                    empty_alt.append(src[:50])
        
        if missing_alt:
            self.issues.append(AuditIssue(
                category="Images",
                severity="critical",
                title=f"{len(missing_alt)} images missing alt text",
                description=f"Found {len(missing_alt)} images without alt attribute",
                recommendation="Add descriptive alt text to all images. For decorative images, use alt=''",
                element=f"Examples: {', '.join(missing_alt[:2])}"
            ))
        
        if empty_alt:
            self.issues.append(AuditIssue(
                category="Images",
                severity="warning",
                title=f"{len(empty_alt)} images have empty alt text",
                description=f"Found {len(empty_alt)} images with empty alt attribute",
                recommendation="If decorative, mark with aria-hidden='true'. Otherwise, add description."
            ))
    
    def _check_links(self):
        """Check link accessibility"""
        links = self.soup.find_all('a', href=True)
        
        if not links:
            return
        
        generic_links = []
        no_text = []
        
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if not text:
                no_text.append(href[:30])
            elif text.lower() in ['click here', 'read more', 'link', 'more']:
                generic_links.append(text)
        
        if no_text:
            self.issues.append(AuditIssue(
                category="Links",
                severity="critical",
                title=f"{len(no_text)} links have no text",
                description=f"Found {len(no_text)} <a> tags without text content",
                recommendation="Add descriptive text to all links or use aria-label"
            ))
        
        if generic_links:
            self.issues.append(AuditIssue(
                category="Links",
                severity="warning",
                title=f"{len(generic_links)} links have generic text",
                description=f"Found {len(generic_links)} links like 'click here', 'read more', 'link'",
                recommendation="Use descriptive link text. Screen reader users see only the link text."
            ))
    
    def _check_headings(self):
        """Check heading structure"""
        headings = self.soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        if not headings:
            self.issues.append(AuditIssue(
                category="Headings",
                severity="warning",
                title="No headings found",
                description="Page has no heading tags (h1-h6)",
                recommendation="Use proper heading hierarchy starting with h1"
            ))
            return
        
        # Check for multiple h1s
        h1s = self.soup.find_all('h1')
        if len(h1s) > 1:
            self.issues.append(AuditIssue(
                category="Headings",
                severity="warning",
                title=f"{len(h1s)} h1 tags found",
                description="Page should have only one h1",
                recommendation="Use one h1 per page for main title, use h2-h6 for subsections"
            ))
        elif len(h1s) == 0:
            self.issues.append(AuditIssue(
                category="Headings",
                severity="critical",
                title="No h1 found",
                description="Page is missing h1 tag",
                recommendation="Add one h1 with main page title"
            ))
        
        # Check heading hierarchy
        heading_levels = [int(h.name[1]) for h in headings]
        for i, level in enumerate(heading_levels[:-1]):
            next_level = heading_levels[i + 1]
            if next_level > level + 1:
                self.issues.append(AuditIssue(
                    category="Headings",
                    severity="warning",
                    title="Heading hierarchy broken",
                    description=f"Jump from h{level} to h{next_level}",
                    recommendation="Use proper heading hierarchy (h1 → h2 → h3, not h1 → h3)"
                ))
                break
    
    def _check_forms(self):
        """Check form accessibility"""
        forms = self.soup.find_all('form')
        
        if not forms:
            return
        
        for form in forms:
            inputs = form.find_all(['input', 'textarea', 'select'])
            
            for input_elem in inputs:
                input_id = input_elem.get('id', '')
                input_name = input_elem.get('name', '')
                
                if not input_id and not input_name:
                    self.issues.append(AuditIssue(
                        category="Forms",
                        severity="critical",
                        title="Form input missing name",
                        description="Form input without id or name attribute",
                        recommendation="Add 'id' attribute to form inputs"
                    ))
                    continue
                
                # Check for associated label
                label = form.find('label', {'for': input_id}) if input_id else None
                if not label and input_id:
                    self.issues.append(AuditIssue(
                        category="Forms",
                        severity="critical",
                        title="Form input missing label",
                        description=f"Input (id='{input_id}') has no associated <label>",
                        recommendation="Use <label for='input_id'> to associate labels with inputs"
                    ))
    
    def _check_contrast(self):
        """Check for potential contrast issues"""
        # Note: This is a simplified check without actual color parsing
        styles = self.soup.find_all('style')
        style_content = ''.join([s.string or '' for s in styles])
        
        # Look for explicit low contrast patterns (simplified)
        if re.search(r'(color|background):\s*(white|#fff|#ffffff)', style_content, re.I):
            if re.search(r'(color|background):\s*(gray|grey|#ccc|#999)', style_content, re.I):
                self.issues.append(AuditIssue(
                    category="Contrast",
                    severity="warning",
                    title="Potential contrast issues detected",
                    description="Found light colors that may have insufficient contrast",
                    recommendation="Ensure text contrast ratio is at least 4.5:1 for normal text, 3:1 for large text"
                ))
    
    def _check_keyboard_nav(self):
        """Check for keyboard navigation support"""
        # Check for onclick handlers without keyboard support
        clickables = self.soup.find_all(string=re.compile(r'onclick', re.I))
        divs_with_onclick = self.soup.find_all('div', attrs={'onclick': True})
        spans_with_onclick = self.soup.find_all('span', attrs={'onclick': True})
        
        if divs_with_onclick or spans_with_onclick:
            self.issues.append(AuditIssue(
                category="Keyboard Navigation",
                severity="warning",
                title="Interactive elements using onclick",
                description=f"Found {len(divs_with_onclick) + len(spans_with_onclick)} div/span elements with onclick handlers",
                recommendation="Use <button> or <a> tags for interactive elements, or add proper ARIA roles and keyboard handlers"
            ))
    
    def _check_aria(self):
        """Check ARIA usage"""
        # Check for common ARIA issues
        aria_labels = self.soup.find_all(attrs={'aria-label': True})
        aria_hidden = self.soup.find_all(attrs={'aria-hidden': 'true'})
        
        if not aria_labels and not aria_hidden:
            # Basic check - not necessarily bad
            pass
        
        # Check for invalid aria-hidden on interactive elements
        buttons_hidden = self.soup.find_all(['button', 'a'], attrs={'aria-hidden': 'true'})
        if buttons_hidden:
            self.issues.append(AuditIssue(
                category="ARIA",
                severity="critical",
                title="Interactive elements hidden from screen readers",
                description=f"Found {len(buttons_hidden)} interactive elements with aria-hidden='true'",
                recommendation="Never hide interactive elements from screen readers. Remove aria-hidden='true'."
            ))
    
    def _check_text_alternatives(self):
        """Check for text alternatives to non-text content"""
        videos = self.soup.find_all(['video', 'iframe'])
        
        if videos:
            for video in videos:
                # Check for captions/transcript
                track = video.find('track')
                aria_label = video.get('aria-label')
                title = video.get('title')
                
                if not track and not aria_label and not title:
                    self.issues.append(AuditIssue(
                        category="Media",
                        severity="warning",
                        title="Video/iframe without accessible alternative",
                        description="Embedded video/iframe lacks captions or description",
                        recommendation="Add <track> element for captions, or provide transcript"
                    ))
    
    def _check_page_structure(self):
        """Check overall page structure"""
        body = self.soup.find('body')
        if not body:
            self.issues.append(AuditIssue(
                category="Structure",
                severity="critical",
                title="Missing body tag",
                description="HTML page missing <body> element"
            ))
    
    def _check_language(self):
        """Check language declaration"""
        html_tag = self.soup.find('html')
        if not html_tag or not html_tag.get('lang'):
            self.issues.append(AuditIssue(
                category="Language",
                severity="info",
                title="Language not declared",
                description="<html> tag missing 'lang' attribute",
                recommendation="Add lang='en' (or appropriate language code)"
            ))
    
    def _check_responsive_design(self):
        """Check for responsive design indicators"""
        head = self.soup.find('head')
        if head:
            viewport = head.find('meta', attrs={'name': 'viewport'})
            if not viewport:
                self.issues.append(AuditIssue(
                    category="Responsive Design",
                    severity="info",
                    title="Viewport meta tag missing",
                    description="Page may not be optimized for mobile devices",
                    recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1'>"
                ))
    
    def _calculate_score(self):
        """Calculate accessibility score (0-100)"""
        if not self.issues:
            self.score = 100
            return
        
        # Weight issues by severity
        weights = {'critical': 10, 'warning': 5, 'info': 1}
        total_deduction = sum(weights.get(issue.severity, 0) for issue in self.issues)
        
        # Score calculation
        self.score = max(0, 100 - total_deduction)
    
    def generate_report(self) -> Dict:
        """Generate audit report"""
        findings = _issues_to_findings(self.issues)
        return _build_report(
            url=self.url,
            timestamp=self.timestamp,
            score=self.score,
            grade=self._get_grade(self.score),
            findings=findings,
        )
    
    @staticmethod
    def _get_grade(score: int) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return 'A (Excellent)'
        elif score >= 80:
            return 'B (Good)'
        elif score >= 70:
            return 'C (Fair)'
        elif score >= 60:
            return 'D (Poor)'
        else:
            return 'F (Fail)'


def _issue_to_dict(issue: AuditIssue) -> Dict:
    return {
        'category': issue.category,
        'severity': issue.severity,
        'title': issue.title,
        'description': issue.description,
        'element': issue.element,
        'recommendation': issue.recommendation,
        'wcag': _wcag_for_category(issue.category),
    }


def _wcag_for_category(category: str) -> str:
    mapping = {
        'Images': '1.1.1 Non-text Content',
        'Links': '2.4.4 Link Purpose',
        'Headings': '1.3.1 Info and Relationships',
        'Forms': '3.3.2 Labels or Instructions',
        'Keyboard': '2.1.1 Keyboard',
        'ARIA': '4.1.2 Name, Role, Value',
        'Semantic HTML': '1.3.1 Info and Relationships',
        'Language': '3.1.1 Language of Page',
        'Responsive Design': '1.4.10 Reflow',
        'Contrast': '1.4.3 Contrast (Minimum)',
    }
    return mapping.get(category, 'WCAG 2.1 AA review')


def _issues_to_findings(issues: List[AuditIssue]) -> List[Dict]:
    findings = []
    for idx, issue in enumerate(issues, start=1):
        item = _issue_to_dict(issue)
        item.update({
            'id': f'a11y-{idx:03d}',
            'rule_id': re.sub(r'[^a-z0-9]+', '-', f"{issue.category}-{issue.title}".lower()).strip('-')[:80],
            'message': issue.description,
            'selector_hint': issue.element,
            'standards': {'wcag': [_wcag_for_category(issue.category)]},
        })
        findings.append(item)
    return findings


def _build_report(url: str, timestamp: str, score: int, grade: str, findings: List[Dict]) -> Dict:
    issues_by_category: Dict[str, List[Dict]] = {}
    findings_by_severity = {'critical': [], 'warning': [], 'info': []}
    for item in findings:
        category = item.get('category', 'General')
        severity = item.get('severity', 'info')
        legacy_item = {
            'category': category,
            'severity': severity,
            'title': item.get('title'),
            'description': item.get('description') or item.get('message'),
            'element': item.get('element') or item.get('selector_hint'),
            'recommendation': item.get('recommendation'),
            'wcag': item.get('wcag') or ', '.join(item.get('standards', {}).get('wcag', [])),
        }
        issues_by_category.setdefault(category, []).append(legacy_item)
        findings_by_severity.setdefault(severity, []).append(legacy_item)

    critical = len(findings_by_severity.get('critical', []))
    warnings = len(findings_by_severity.get('warning', []))
    info = len(findings_by_severity.get('info', []))
    manual_checks = [
        'Verify keyboard-only navigation, visible focus order, and absence of keyboard traps.',
        'Verify the main user flow with NVDA, JAWS, VoiceOver, or TalkBack.',
        'Check dynamic content, modals, error messages, and form validation with assistive technology.',
        'Validate color contrast and zoom/reflow in the final rendered UI.',
    ]
    passed_checks = []
    if score >= 80:
        passed_checks.append({'title': 'No dominant automated blocker', 'description': 'The automated score is high enough for further manual verification.', 'category': 'Summary'})

    top_findings = sorted(findings, key=lambda x: {'critical': 0, 'warning': 1, 'info': 2}.get(str(x.get('severity') or 'info'), 3))[:5]
    if critical > 0:
        assessment = 'Critical accessibility blockers were found. The page is not ready to claim accessibility compliance.'
    elif warnings > 0:
        assessment = 'No critical automated blocker dominates the report, but warnings require fixes and manual assistive-technology testing.'
    else:
        assessment = 'Automated checks did not find accessibility issues, but manual screen-reader and keyboard verification is still required.'

    report = {
        'schema_version': '1.0.0',
        'schema_id': 'https://hexdrive.tech/schemas/accessibility-audit-report.schema.json',
        'url': url,
        'timestamp': timestamp,
        'platform': 'web',
        'mode': 'full',
        'standards_checked': ['WCAG 2.1 AA', 'GOST R 52872-2019'],
        'score': score,
        'grade': grade,
        'total_issues': len(findings),
        'critical': critical,
        'warnings': warnings,
        'info': info,
        'issues_by_category': issues_by_category,
        'findings_by_severity': findings_by_severity,
        'findings': findings,
        'top_findings': top_findings,
        'passed_checks': passed_checks,
        'manual_checks': manual_checks,
        'next_steps': [
            'Fix critical findings first, then warnings.',
            'Run a repeat audit after fixes.',
            'Complete manual keyboard and screen-reader verification before claiming full accessibility.',
        ],
        'summary': {
            'overall_assessment': assessment,
            'checked_automatically': max(1, len(findings)),
            'manual_follow_up_count': len(manual_checks),
        },
    }
    report['mcp_payload'] = {
        'schema_version': report['schema_version'],
        'url': report['url'],
        'score': report['score'],
        'grade': report['grade'],
        'findings': report['findings'],
        'summary': report['summary'],
    }
    return report


def audit_html_content(html_content: str, source_name: str = 'inline-html') -> Dict:
    auditor = AccessibilityAuditor(source_name)
    auditor.html = html_content
    auditor.soup = BeautifulSoup(html_content, 'html.parser')
    auditor._check_semantic_html()
    auditor._check_images()
    auditor._check_links()
    auditor._check_headings()
    auditor._check_forms()
    auditor._check_contrast()
    auditor._check_keyboard_nav()
    auditor._check_aria()
    auditor._check_text_alternatives()
    auditor._check_page_structure()
    auditor._check_language()
    auditor._check_responsive_design()
    auditor._calculate_score()
    return auditor.generate_report()


def audit_html_file(path: str) -> Dict:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return audit_html_content(f.read(), source_name=path)


def load_report_schema() -> Dict:
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schemas', 'accessibility-audit-report.schema.json')
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def audit_website(url: str) -> Dict:
    """Main entry point for auditing a website"""
    auditor = AccessibilityAuditor(url)
    return await auditor.audit()


if __name__ == '__main__':
    # Test
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        report = asyncio.run(audit_website(url))
        print(json.dumps(report, indent=2))
