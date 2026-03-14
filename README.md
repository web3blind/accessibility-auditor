# 🤖 Hermes Agent: Accessibility Auditor

Autonomous AI agent analyzing websites for WCAG 2.1 + GOST compliance.
Built for blind and low-vision users.

🚀 **[Telegram Bot](https://t.me/accessibilityAuditAgentBot)** | 🌐 **[Web Interface](https://hexdrive.tech)**

**Direct Bot Link:** https://t.me/accessibilityAuditAgentBot

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

## Access Methods

### 🤖 Telegram Bot
**Telegram:** https://t.me/accessibilityAuditAgentBot

Send `/audit https://example.com` to get instant analysis

### 🌐 Web Interface
**URL:** https://hexdrive.tech (or localhost:3000 when running locally)

Beautiful, accessible web form for auditing websites

## How It Works

1. **Dual Interface** - Works via Telegram bot OR web form
2. **Real-time Analysis** - Fetches & parses HTML instantly
3. **12 Comprehensive Checks** - Validates WCAG 2.1 & GOST compliance
4. **Detailed Reports** - Beautiful HTML reports with scoring & recommendations
5. **Persistent Storage** - All results saved as markdown files
6. **Shareable Links** - Each audit gets a unique URL for sharing results

## Tech Stack

- Python 3.12
- FastAPI (API + static web server)
- BeautifulSoup4 (HTML parsing)
- python-telegram-bot
- Async architecture
- Hermes Agent framework

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/web3blind/accessibility-auditor.git
cd accessibility-auditor
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables
```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
```

### 5. Run Combined Bot + API
```bash
python3 -u bot_final.py
```

This starts:
- ✅ Telegram Bot (async polling)
- ✅ Web API on http://localhost:3000
- ✅ Web Interface at http://localhost:3000

## Usage

### Via Telegram
```
/start              - Show help
/audit https://...  - Audit a website
(or just send a URL) - Auto-detects URLs
```

### Via Web
1. Go to http://localhost:3000
2. Enter website URL
3. Click "Start Audit"
4. View beautiful report with detailed analysis

## File Structure
```
accessibility-auditor/
├── bot_final.py          # Combined Telegram bot + FastAPI server
├── auditor.py            # Core 12 accessibility checks
├── storage.py            # Save/load audit results
├── report_generator.py    # Generate beautiful HTML reports
├── api.py                # FastAPI endpoints (reference)
├── web/
│   └── index.html        # Web form interface
├── audits/               # Stored audit results (.json + .md)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Example Results

Each audit generates:
1. **JSON report** - Machine-readable data
2. **HTML report** - Beautiful interactive page
3. **Markdown report** - Readable text format

## Deployment

### Quick Start (Self-hosted)

See **DEPLOYMENT.md** for full instructions.

**TL;DR:**
```bash
# 1. nginx + Let's Encrypt
sudo cp nginx.conf /etc/nginx/sites-available/hexdrive.tech
sudo certbot certonly --nginx -d hexdrive.tech

# 2. Run bot
source venv/bin/activate
nohup python3 bot_final.py >> bot.log 2>&1 &

# 3. Keep-alive cronjob
chmod +x keep-alive.sh
crontab -e  # Add: */1 * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh
```

Then:
1. Point hexdrive.tech DNS to your server IP
2. Visit https://hexdrive.tech
3. Test bot: `/audit https://example.com`

## Built With

@NousResearch Hermes Agent Framework

Real problem. Real solution.
