#!/usr/bin/env python3
"""
Accessibility Auditor - Combined Telegram Bot + Web API
FastAPI server on :3000, Telegram bot polling in separate thread
"""

import asyncio
import logging
import sys
import os
import threading
import json
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction
from urllib.parse import urlparse
from auditor import audit_website
from storage import AuditStorage
from report_generator import ReportGenerator
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

# Load config
CONFIG_PATH = Path("/root/.hermes/agents/accessibility-auditor/config.json")
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    TOKEN = config.get("telegram_token")
    API_HOST = config.get("api_host", "127.0.0.1")
    API_PORT = config.get("api_port", 3000)
else:
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    API_HOST = "127.0.0.1"
    API_PORT = 3000

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set in config.json or environment")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/root/.hermes/agents/accessibility-auditor/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize services
storage = AuditStorage()
report_gen = ReportGenerator()


def is_valid_url(url: str) -> bool:
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await update.message.reply_text(
        f"🔍 **Accessibility Auditor Bot**\\n\\n"
        f"Hi {user.first_name}! Send me a website URL to check for accessibility issues.\\n\\n"
        f"Example: https://example.com",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages with URLs"""
    text = update.message.text.strip()
    
    if not is_valid_url(text):
        await update.message.reply_text(
            "❌ Please send a valid URL (http:// or https://)"
        )
        return
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
    try:
        audit_result = await audit_website(text)
        audit_id = storage.save_audit(text, audit_result)
        
        summary = f"✅ Audit Complete\\n\\n"
        summary += f"🌐 Website: {text}\\n"
        summary += f"📊 Issues Found: {len(audit_result.get('issues', []))}\\n"
        
        if audit_result.get('issues'):
            summary += "\\n**Top Issues:**\\n"
            for issue in audit_result['issues'][:3]:
                summary += f"• {issue}\\n"
        
        link = f"https://hexdrive.tech/audits/{audit_id}"
        summary += f"\\n📄 Full Report: {link}"
        
        await update.message.reply_text(summary, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Audit error: {e}")
        await update.message.reply_text(
            f"❌ Audit error: {str(e)}"
        )


async def run_telegram_bot():
    """Run Telegram bot polling"""
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API")
    logger.info("=" * 60)
    logger.info("Starting Telegram bot in background thread...")
    
    logger.info("Telegram bot initializing...")
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot initialized, starting polling...")
    await application.initialize()
    await application.start()
    logger.info("Bot polling started successfully")
    
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    return application


# FastAPI app
app = FastAPI()


class AuditRequest(BaseModel):
    url: str


@app.get("/")
async def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>Accessibility Auditor</title>
        <style>
            body { font-family: Arial; margin: 20px; }
            .container { max-width: 600px; margin: 0 auto; }
            input { padding: 10px; width: 100%; }
            button { padding: 10px; background: #007bff; color: white; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class=\"container\">
            <h1>🔍 Accessibility Auditor</h1>
            <p>Check your website for accessibility issues</p>
            <input type=\"url\" id=\"url\" placeholder=\"https://example.com\">
            <button onclick=\"audit()\">Audit</button>
            <div id=\"result\"></div>
        </div>
        <script>
            async function audit() {
                const url = document.getElementById('url').value;
                const result = await fetch('/api/audit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                }).then(r => r.json());
                document.getElementById('result').innerHTML = '<p>' + JSON.stringify(result, null, 2) + '</p>';
            }
        </script>
    </body>
    </html>
    """)


@app.post("/api/audit")
async def audit(request: AuditRequest):
    """API endpoint for audits"""
    try:
        result = await audit_website(request.url)
        audit_id = storage.save_audit(request.url, result)
        return {"status": "ok", "audit_id": audit_id, "issues_count": len(result.get('issues', []))}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/audits/{audit_id}")
async def get_audit(audit_id: str):
    """Get audit report"""
    audit_data = storage.get_audit(audit_id)
    if not audit_data:
        return HTMLResponse("<h1>❌ Audit not found</h1>", status_code=404)
    
    html = report_gen.generate_html_report(audit_data)
    return HTMLResponse(html)


@app.get(\"/audits\")
async def list_audits():
    \"\"\"List recent audits\"\"\"
    audits = storage.list_audits(limit=10)
    html = \"<h1>📊 Recent Audits</h1><ul>\"
    for audit in audits:
        html += f\"<li><a href='/audits/{audit['id']}'>{audit['url']}</a> - {len(audit.get('data', {}).get('issues', []))} issues</li>\"
    html += \"</ul>\"
    return HTMLResponse(html)


def run_fastapi():
    """Run FastAPI server"""
    logger.info(f"Starting FastAPI server on http://{API_HOST}:{API_PORT} (localhost only)")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


async def main():
    """Main async entry point"""
    # Start FastAPI in a separate thread
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()
    
    # Run Telegram bot
    tg_app = await run_telegram_bot()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await tg_app.stop()


if __name__ == "__main__":
    asyncio.run(main())
