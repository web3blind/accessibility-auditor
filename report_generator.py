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
        
        # Issues section
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
