#!/usr/bin/env python3
"""
HTML Report Generator
Converts audit reports to beautiful, accessible HTML
"""

from typing import Dict
from datetime import datetime
import html as html_module


class ReportGenerator:
    """Generates beautiful HTML audit reports"""
    
    def generate_html(self, report: Dict) -> str:
        """Convert audit report dict to HTML"""
        if report.get('audit_type') == 'site':
            return self.generate_site_html(report)
        
        score = report.get('score', 0)
        grade = report.get('grade', 'N/A')
        url = report.get('url', 'N/A')
        timestamp = report.get('timestamp', '')
        total = report.get('total_issues', 0)
        critical = report.get('critical', 0)
        warnings = report.get('warnings', 0)
        info = report.get('info', 0)
        issues_by_category = report.get('issues_by_category', {})
        
        # Score color
        score_color = self._get_score_color(score)
        grade_class = self._get_grade_class(score)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accessibility Audit - {url}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 0.95em;
            opacity: 0.9;
            word-break: break-all;
        }}
        
        .score-section {{
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 40px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .score-card {{
            text-align: center;
            padding: 20px;
        }}
        
        .score-circle {{
            width: 150px;
            height: 150px;
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 0 auto 15px;
            font-size: 3em;
            font-weight: bold;
            color: white;
            background: {score_color};
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }}
        
        .grade-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
            background: {score_color};
            color: white;
            margin-bottom: 10px;
        }}
        
        .grade-badge.{grade_class} {{
            background: {score_color};
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            padding: 20px;
        }}
        
        .stat {{
            text-align: center;
            padding: 15px;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .stat.critical {{
            border-left-color: #dc3545;
        }}
        
        .stat.warning {{
            border-left-color: #ffc107;
        }}
        
        .stat.info {{
            border-left-color: #17a2b8;
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: {score_color};
        }}
        
        .stat-label {{
            font-size: 0.85em;
            color: #666;
            margin-top: 5px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            font-size: 1.5em;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .issue {{
            background: #f8f9fa;
            border-left: 4px solid #dc3545;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 4px;
        }}
        
        .issue.warning {{
            border-left-color: #ffc107;
        }}
        
        .issue.info {{
            border-left-color: #17a2b8;
        }}
        
        .issue-severity {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: bold;
            font-size: 0.85em;
            margin-bottom: 10px;
        }}
        
        .issue-severity.critical {{
            background: #dc3545;
            color: white;
        }}
        
        .issue-severity.warning {{
            background: #ffc107;
            color: #333;
        }}
        
        .issue-severity.info {{
            background: #17a2b8;
            color: white;
        }}
        
        .issue-title {{
            font-size: 1.1em;
            font-weight: bold;
            margin: 10px 0;
            color: #333;
        }}
        
        .issue-description {{
            color: #666;
            margin: 8px 0;
        }}
        
        .issue-recommendation {{
            background: white;
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
            color: #2c5aa0;
            font-size: 0.95em;
        }}
        
        .issue-recommendation::before {{
            content: "💡 ";
        }}
        
        .no-issues {{
            text-align: center;
            padding: 40px;
            color: #28a745;
            font-size: 1.2em;
        }}
        
        .no-issues::before {{
            content: "✅ ";
            font-size: 2em;
            display: block;
            margin-bottom: 10px;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
            border-top: 1px solid #e9ecef;
        }}
        
        .timestamp {{
            font-size: 0.85em;
            color: #999;
            margin-top: 5px;
        }}
        
        @media (max-width: 768px) {{
            .score-section {{
                flex-direction: column;
            }}
            
            .header {{
                padding: 20px;
            }}
            
            .header h1 {{
                font-size: 1.5em;
            }}
            
            .content {{
                padding: 20px;
            }}
            
            .score-circle {{
                width: 120px;
                height: 120px;
                font-size: 2em;
            }}
        }}
        
        /* Accessibility improvements */
        a:focus,
        button:focus {{
            outline: 3px solid #667eea;
            outline-offset: 2px;
        }}
        
        .skip-link {{
            position: absolute;
            top: -40px;
            left: 0;
            background: #667eea;
            color: white;
            padding: 8px;
            text-decoration: none;
            z-index: 100;
        }}
        
        .skip-link:focus {{
            top: 0;
        }}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>
    
    <div class="container">
        <header class="header">
            <h1>♿ Accessibility Audit Report</h1>
            <p>{url}</p>
            <div class="timestamp">{timestamp}</div>
        </header>
        
        <section class="score-section">
            <div class="score-card">
                <div class="score-circle">{score}</div>
                <span class="grade-badge {grade_class}">{grade}</span>
            </div>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total}</div>
                    <div class="stat-label">Total Issues</div>
                </div>
                <div class="stat critical">
                    <div class="stat-value">{critical}</div>
                    <div class="stat-label">Critical</div>
                </div>
                <div class="stat warning">
                    <div class="stat-value">{warnings}</div>
                    <div class="stat-label">Warnings</div>
                </div>
                <div class="stat info">
                    <div class="stat-value">{info}</div>
                    <div class="stat-label">Info</div>
                </div>
            </div>
        </section>
        
        <main id="main-content" class="content">
"""
        summary = report.get('summary') or {}
        if summary:
            html += f"""
            <section class="section">
                <h2>Executive summary</h2>
                <p>{html_module.escape(summary.get('overall_assessment') or '')}</p>
            </section>
"""

        genlayer = report.get('genlayer_adjudication') or {}
        if genlayer:
            decision = genlayer.get('decision') or {}
            verdict = html_module.escape(str(decision.get('verdict', 'unknown')))
            rationale = html_module.escape(str(decision.get('rationale_en') or decision.get('rationale') or ''))
            confidence = html_module.escape(str(decision.get('confidence', 'n/a')))
            network = html_module.escape(str(genlayer.get('network', 'n/a')))
            contract = html_module.escape(str(genlayer.get('contract_address', 'n/a')))
            contract_url = html_module.escape(str(genlayer.get('contract_url') or ''))
            transaction_hash = html_module.escape(str(genlayer.get('transaction_hash') or ''))
            transaction_url = html_module.escape(str(genlayer.get('transaction_url') or ''))
            rollup_hash = html_module.escape(str(genlayer.get('rollup_transaction_hash') or ''))
            rollup_url = html_module.escape(str(genlayer.get('rollup_transaction_url') or ''))
            status = html_module.escape(str(genlayer.get('status', 'n/a')))
            contract_html = (
                f'<a href="{contract_url}" target="_blank" rel="noopener noreferrer"><code>{contract}</code></a>'
                if contract_url else f'<code>{contract}</code>'
            )
            tx_html = ""
            if transaction_hash and transaction_url:
                tx_html += f'<p class="issue-description"><strong>GenLayer transaction:</strong> <a href="{transaction_url}" target="_blank" rel="noopener noreferrer"><code>{transaction_hash}</code></a></p>'
            if rollup_hash and rollup_url:
                tx_html += f'<p class="issue-description"><strong>Rollup transaction:</strong> <a href="{rollup_url}" target="_blank" rel="noopener noreferrer"><code>{rollup_hash}</code></a></p>'
            html += f"""
            <section class="section">
                <h2>GenLayer adjudication</h2>
                <article class="issue info">
                    <span class="issue-severity info">{status.upper()}</span>
                    <h3 class="issue-title">Claim verdict: {verdict}</h3>
                    <p class="issue-description"><strong>Confidence:</strong> {confidence}/100</p>
                    <p class="issue-description"><strong>Rationale:</strong> {rationale}</p>
                    <p class="issue-description"><strong>Network:</strong> {network}</p>
                    <p class="issue-description"><strong>Contract:</strong> {contract_html}</p>
                    {tx_html}
                </article>
            </section>
"""

        passed_checks = report.get('passed_checks') or []
        if passed_checks:
            html += """
            <section class="section">
                <h2>Passed checks</h2>
"""
            for item in passed_checks:
                html += f"                <p>✅ <strong>{html_module.escape(item.get('title', 'Passed'))}</strong>: {html_module.escape(item.get('description', ''))}</p>\n"
            html += "            </section>\n"

        manual_checks = report.get('manual_checks') or []
        if manual_checks:
            html += """
            <section class="section">
                <h2>What needs manual testing</h2>
                <ul>
"""
            for item in manual_checks:
                html += f"                    <li>{html_module.escape(str(item))}</li>\n"
            html += "                </ul>\n            </section>\n"

        next_steps = report.get('next_steps') or []
        if next_steps:
            html += """
            <section class="section">
                <h2>Next steps</h2>
                <ul>
"""
            for item in next_steps:
                html += f"                    <li>{html_module.escape(str(item))}</li>\n"
            html += "                </ul>\n            </section>\n"

        
        # Issues section
        if critical:
            html += """
            <section class="section">
                <h2>Critical issues</h2>
                <p>Critical findings are listed below in their categories.</p>
            </section>
"""
        if issues_by_category:
            for category, issues in issues_by_category.items():
                html += f"""
            <section class="section">
                <h2>{category}</h2>
"""
                for issue in issues:
                    severity = issue.get('severity', 'info')
                    title = html_module.escape(issue.get('title') or 'Unknown Issue')
                    description = html_module.escape(issue.get('description') or '')
                    recommendation = html_module.escape(issue.get('recommendation') or '')
                    element = html_module.escape(issue.get('element') or '')
                    
                    output = f"""
                <article class="issue {severity}">
                    <span class="issue-severity {severity}">{severity.upper()}</span>
                    <h3 class="issue-title">{title}</h3>
                    <p class="issue-description">{description}</p>
"""
                    if element:
                        output += f'                    <p class="issue-description"><strong>Element:</strong> <code>{element}</code></p>\n'
                    
                    if recommendation:
                        output += f'                    <div class="issue-recommendation">{recommendation}</div>\n'
                    
                    output += "                </article>\n"
                    html += output
                
                html += "            </section>\n"
        else:
            html += """
            <div class="no-issues">
                <p>No accessibility issues found!</p>
                <p>This website follows WCAG 2.1 guidelines.</p>
            </div>
"""
        
        html += """
        </main>
        
        <footer class="footer">
            <p>Powered by Accessibility Auditor 🤖</p>
            <p>Based on WCAG 2.1 and GOST R 52872-2019 standards</p>
        </footer>
    </div>
</body>
</html>
"""
        
        return html

    def generate_site_html(self, report: Dict) -> str:
        """Render a site-level multi-page audit report."""
        score = report.get('score', 0)
        grade = html_module.escape(str(report.get('grade', 'N/A')))
        root_url = html_module.escape(str(report.get('root_url') or report.get('url') or 'N/A'))
        timestamp = html_module.escape(str(report.get('timestamp', '')))
        summary = report.get('summary') or {}
        pricing = report.get('pricing') or {}
        escrow = report.get('escrow') or {}
        score_color = self._get_score_color(score)

        def esc(value):
            return html_module.escape(str(value if value is not None else ''))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-page Accessibility Audit - {root_url}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #222; background: #f3f4f8; margin: 0; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.14); overflow: hidden; }}
        header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 34px; }}
        main {{ padding: 30px; }}
        h1, h2, h3 {{ line-height: 1.25; }}
        .score {{ display: inline-block; min-width: 110px; text-align: center; padding: 18px; border-radius: 999px; background: {score_color}; color: white; font-size: 2rem; font-weight: 700; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 20px 0; }}
        .card {{ border: 1px solid #e5e7eb; border-left: 5px solid #667eea; border-radius: 8px; padding: 14px; background: #fff; }}
        .critical {{ border-left-color: #dc3545; }} .warning {{ border-left-color: #b7791f; }} .info {{ border-left-color: #0f7490; }}
        .muted {{ color: #555; }} code {{ word-break: break-all; }}
        a:focus {{ outline: 3px solid #111827; outline-offset: 2px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }} th, td {{ text-align: left; border-bottom: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
    </style>
</head>
<body>
<div class="container">
<header>
    <h1>Multi-page Accessibility Audit Report</h1>
    <p>{root_url}</p>
    <p class="muted">{timestamp}</p>
</header>
<main>
    <section aria-labelledby="summary-heading">
        <h2 id="summary-heading">Executive summary</h2>
        <p><span class="score">{score}</span> <strong>{grade}</strong></p>
        <p>{esc(summary.get('overall_assessment'))}</p>
        <div class="grid">
            <div class="card"><strong>Pages audited</strong><br>{esc(summary.get('pages_audited', 0))}</div>
            <div class="card"><strong>Pages failed</strong><br>{esc(summary.get('pages_failed', 0))}</div>
            <div class="card critical"><strong>Critical</strong><br>{esc(report.get('critical', 0))}</div>
            <div class="card warning"><strong>Warnings</strong><br>{esc(report.get('warnings', 0))}</div>
            <div class="card info"><strong>Info</strong><br>{esc(report.get('info', 0))}</div>
        </div>
    </section>
    <section aria-labelledby="pricing-heading">
        <h2 id="pricing-heading">Fortytwo x402Escrow pricing</h2>
        <p>Mode: <code>{esc(escrow.get('mode'))}</code>; network: <code>{esc(escrow.get('network'))}</code>; escrow id: <code>{esc(escrow.get('escrow_id'))}</code></p>
        <div class="grid">
            <div class="card"><strong>Max locked</strong><br>{esc(pricing.get('max_locked'))} {esc(pricing.get('currency', 'USDC'))}</div>
            <div class="card"><strong>Actual settled</strong><br>{esc(pricing.get('actual_settled'))} {esc(pricing.get('currency', 'USDC'))}</div>
            <div class="card"><strong>Refund</strong><br>{esc(pricing.get('refund'))} {esc(pricing.get('currency', 'USDC'))}</div>
            <div class="card"><strong>Price per page</strong><br>{esc(pricing.get('price_per_page'))} {esc(pricing.get('currency', 'USDC'))}</div>
        </div>
    </section>
"""
        repeated = report.get('repeated_issues') or []
        if repeated:
            html += "<section><h2>Repeated issues across pages</h2>"
            for issue in repeated[:20]:
                severity = esc(issue.get('severity', 'info'))
                html += f"<article class='card {severity}'><h3>{esc(issue.get('title'))}</h3><p><strong>{severity.upper()}</strong> on {esc(issue.get('affected_pages'))} page(s).</p>"
                examples = issue.get('example_urls') or []
                if examples:
                    html += "<ul>" + "".join(f"<li><code>{esc(url)}</code></li>" for url in examples[:5]) + "</ul>"
                html += "</article>"
            html += "</section>"

        pages = report.get('page_reports') or []
        if pages:
            html += "<section><h2>Audited pages</h2><table><thead><tr><th>URL</th><th>Status</th><th>Score</th><th>Critical</th><th>Warnings</th></tr></thead><tbody>"
            for page in pages:
                html += f"<tr><td><code>{esc(page.get('url'))}</code></td><td>{esc(page.get('status', 'ok'))}</td><td>{esc(page.get('score', ''))}</td><td>{esc(page.get('critical', ''))}</td><td>{esc(page.get('warnings', ''))}</td></tr>"
            html += "</tbody></table></section>"

        manual_checks = report.get('manual_checks') or []
        if manual_checks:
            html += "<section><h2>Manual follow-up</h2><ul>" + "".join(f"<li>{esc(item)}</li>" for item in manual_checks) + "</ul></section>"

        html += """
</main>
</div>
</body>
</html>
"""
        return html
    
    @staticmethod
    def _get_score_color(score: int) -> str:
        """Get color for score"""
        if score >= 90:
            return '#28a745'  # Green
        elif score >= 80:
            return '#20c997'  # Light green
        elif score >= 70:
            return '#ffc107'  # Yellow
        elif score >= 60:
            return '#fd7e14'  # Orange
        else:
            return '#dc3545'  # Red
    
    @staticmethod
    def _get_grade_class(score: int) -> str:
        """Get CSS class for grade"""
        if score >= 90:
            return 'grade-a'
        elif score >= 80:
            return 'grade-b'
        elif score >= 70:
            return 'grade-c'
        elif score >= 60:
            return 'grade-d'
        else:
            return 'grade-f'


if __name__ == '__main__':
    # Test
    gen = ReportGenerator()
    
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
            ],
            'Links': [
                {
                    'severity': 'warning',
                    'title': 'Generic link text',
                    'description': 'Found 2 links with generic text like "click here"',
                    'element': None,
                    'recommendation': 'Use descriptive link text instead'
                }
            ]
        }
    }
    
    html = gen.generate_html(test_report)
    
    with open('/tmp/test_report.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("Test report saved to /tmp/test_report.html")
