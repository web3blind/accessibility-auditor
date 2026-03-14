# Accessibility Auditor

Web accessibility analysis tool for WCAG 2.1 and GOST R 52872-2019 compliance.
Built for blind and low-vision users.

🤖 **[Telegram Bot: @accessibilityAuditAgentBot](https://t.me/accessibilityAuditAgentBot)** | 🌐 **[Web Interface: hexdrive.tech](https://hexdrive.tech)**

## Features

12 automated accessibility checks:

- Semantic HTML structure
- Image alt text validation
- Link text quality
- Heading hierarchy
- Form accessibility (labels, IDs)
- Keyboard navigation (onclick handlers)
- ARIA attributes correctness
- Media captions (video/iframe)
- Contrast ratio detection
- Language declaration (`lang` attribute)
- Page structure (`<body>`, landmarks)
- Responsive design (viewport meta tag)

Each audit produces a score from 0 to 100 and a letter grade (A–F).

## Access

### Telegram Bot

Send any URL to [@accessibilityAuditAgentBot](https://t.me/accessibilityAuditAgentBot):

```
/start              — welcome and help
/help               — usage instructions
/status             — check bot status
https://example.com — send a URL to audit
```

### Web Interface

Open [https://hexdrive.tech](https://hexdrive.tech), enter a URL and click **Analyze**.
Results appear at `https://hexdrive.tech/audits/<audit_id>`.

## How It Works

1. The URL is submitted via Telegram or the web form.
2. A headless Chromium browser (Playwright) fetches the fully rendered page.
3. BeautifulSoup parses the HTML and runs 12 accessibility checks.
4. A score is calculated; the report is saved as JSON + Markdown.
5. An HTML report is generated and served at a unique URL.

## Tech Stack

- Python 3.12
- FastAPI — API + web server
- Uvicorn — ASGI server
- Playwright — headless Chromium for page rendering
- BeautifulSoup4 — HTML parsing
- python-telegram-bot 20.x — Telegram bot
- Async architecture (asyncio + threading)

## Installation

### 1. Clone

```bash
git clone https://github.com/web3blind/accessibility-auditor.git
cd accessibility-auditor
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure

Create `config.json` (not committed to git — contains credentials):

```json
{
  "telegram_token": "YOUR_BOT_TOKEN",
  "api_host": "127.0.0.1",
  "api_port": 3000
}
```

Or use an environment variable:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
```

### 5. Run

```bash
python3 -u bot_final.py
```

This starts:
- Telegram Bot (async polling)
- Web API on http://localhost:3000
- Web Interface at http://localhost:3000

## File Structure

```
accessibility-auditor/
├── bot_final.py         # Combined Telegram bot + FastAPI server
├── auditor.py           # Core accessibility checks
├── fetch_page.py        # Headless browser page fetcher (Playwright subprocess)
├── storage.py           # Save/load audit results (JSON + Markdown)
├── report_generator.py  # Generate HTML audit reports
├── web/
│   └── index.html       # Web form interface
├── requirements.txt     # Python dependencies
├── nginx.conf           # nginx reverse proxy config
├── keep-alive.sh        # Cron script to restart bot if it crashes
└── README.md
```

## Output Formats

Each audit produces:

1. **JSON** — machine-readable data (`audits/audit_<id>.json`)
2. **Markdown** — plain text report (`audits/audit_<id>.md`)
3. **HTML** — interactive web report at `https://hexdrive.tech/audits/<id>`

## Deployment

See **DEPLOYMENT.md** for full server setup instructions.

**Quick reference:**

```bash
# 1. Set up nginx + TLS
sudo cp nginx.conf /etc/nginx/sites-available/hexdrive.tech
sudo certbot certonly --nginx -d hexdrive.tech

# 2. Run the bot
source venv/bin/activate
nohup python3 bot_final.py >> bot.log 2>&1 &

# 3. Add keep-alive cron job
chmod +x keep-alive.sh
crontab -e  # Add: */1 * * * * /path/to/keep-alive.sh
```

Point `hexdrive.tech` DNS to your server IP, then visit https://hexdrive.tech.

## Security

- Bot token is stored in `config.json` (excluded from git via `.gitignore`)
- Audit results are stored locally and not public by default
- All user input is validated before processing

---

Built with [Hermes Agent](https://nousresearch.com) · Real problem. Real solution.
