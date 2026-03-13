# 🤖 Hermes Agent: Accessibility Auditor

Autonomous AI agent analyzing websites for WCAG 2.1 + GOST compliance.
Built for blind and low-vision users.

## Features

✅ 12 Automated Accessibility Checks:
- Semantic HTML structure
- Image alt text validation
- Link text quality
- Heading hierarchy
- Form accessibility
- Keyboard navigation
- ARIA attributes
- Media captions
- Contrast ratios
- Language declaration
- Page structure
- Responsive design

## Tech Stack

- Python 3.12
- BeautifulSoup4 (HTML parsing)
- python-telegram-bot
- Async architecture
- Hermes Agent framework

## Live Bot

Telegram: @accessibilityAuditAgentBot

Usage: /audit https://example.com

## How It Works

1. Autonomous - runs 24/7 without human intervention
2. Real-time analysis - fetches & parses HTML
3. 12 checks - runs accessibility validation
4. Detailed reports - scoring & recommendations
5. 24/7 monitoring - Hermes cronjob ensures uptime

## Installation

```bash
git clone https://github.com/web3blind/accessibility-auditor.git
pip install -r requirements.txt
python3 -u -B bot_final.py
```

## Built With

@NousResearch Hermes Agent Framework

Real problem. Real solution.
