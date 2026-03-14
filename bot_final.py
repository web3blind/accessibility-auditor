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
        return all([result.scheme, result.netloc])
    except:
        return False


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await update.message.reply_text(
        "🔍 *Accessibility Auditor*\n\n"
        "Hi! Send me a website URL and I'll analyze it for accessibility issues.\n\n"
        "Example: https://example.com"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "📋 *How to use Accessibility Auditor:*\n\n"
        "1. Send any website URL\n"
        "2. Bot analyzes accessibility\n"
        "3. Get detailed report\n"
        "4. View results on web: https://hexdrive.tech\n\n"
        "*Commands:*\n"
        "/start - Welcome message\n"
        "/help - This message\n"
        "/status - Check bot status\n\n"
        "*Questions?* Contact @web3blind",
        parse_mode="Markdown"
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    await update.message.reply_text(
        "✅ Bot is online and ready!\n\n"
        "Send a URL to start auditing."
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with URLs"""
    user_message = update.message.text.strip()
    
    if not is_valid_url(user_message):
        await update.message.reply_text(
            "❌ Invalid URL format.\n\n"
            "Please send a valid URL:\n"
            "https://example.com"
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔄 Analyzing {user_message}...\n\n"
        "This may take a minute..."
    )
    
    try:
        # Run audit (audit_website is async)
        audit_result = await audit_website(user_message)
        
        if not audit_result:
            await processing_msg.edit_text(
                "❌ Failed to audit website.\n\n"
                "Unknown error"
            )
            return
        
        # Save result
        audit_id = storage.save_audit(user_message, audit_result)
        
        # Build summary message
        score = audit_result.get("score", 0)
        issues = audit_result.get("issues", {})
        
        summary = (
            f"✅ *Audit Complete*\n\n"
            f"🎯 *Score: {score}%*\n\n"
            f"📊 *Issues Found:*\n"
        )
        
        for category, count in issues.items():
            if count > 0:
                summary += f"• {category.title()}: {count}\n"
        
        summary += f"\n🌐 *Watch on the web:* https://hexdrive.tech/audits/{audit_id}\n\n"
        summary += (
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 *Accessibility Auditor*\n"
            "⭐️ Rating: 4.8/5.0\n\n"
            "*About Project*\n"
            "AI agent analyzing websites for WCAG 2.1 & GOST accessibility.\n"
            "Built for blind and low-vision developers.\n\n"
            "*Key Features*\n"
            "✓ WCAG 2.1 AA compliance\n"
            "✓ Contrast analysis\n"
            "✓ Alt text validation\n"
            "✓ Keyboard navigation\n"
            "✓ HTML reports\n\n"
            "*Contact*\n"
            "GitHub: github.com/web3blind\n"
            "Platform: @accessibilityAuditAgentBot"
        )
        
        await processing_msg.edit_text(summary, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Audit error: {str(e)}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ Error during audit:\n\n{str(e)[:200]}"
        )


# FastAPI setup
app = FastAPI()


@app.get("/")
async def root():
    """Health check"""
    return {"status": "ok", "service": "accessibility-auditor"}


@app.get("/audits/{audit_id}")
async def get_audit(audit_id: str):
    """Get audit report as HTML"""
    audit_file = storage.get_audit_path(audit_id)
    if not audit_file.exists():
        return {"error": "Audit not found"}, 404
    
    # Read markdown and convert to HTML
    content = audit_file.read_text()
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Accessibility Audit Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; margin: 40px; line-height: 1.6; }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            h1, h2, h3 {{ color: #333; }}
            .score {{ font-size: 2em; font-weight: bold; color: #4CAF50; }}
            .issues {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
            pre {{ background: #f9f9f9; padding: 10px; border-left: 3px solid #ddd; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Accessibility Audit Report</h1>
            <pre>{content}</pre>
            <hr>
            <p><small>Generated by Accessibility Auditor Bot</small></p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


class AuditRequest(BaseModel):
    url: str


@app.post("/api/audit")
async def submit_audit(request: AuditRequest):
    """API endpoint to submit audit request"""
    url = request.url.strip()
    
    if not is_valid_url(url):
        return {"status": "error", "message": "Invalid URL format"}, 400
    
    try:
        result = await audit_website(url)
        audit_id = storage.save_audit(url, result)
        return {
            "status": "success",
            "audit_id": audit_id,
            "url": f"/audits/{audit_id}"
        }
    except Exception as e:
        logger.error(f"API audit error: {str(e)}")
        return {"status": "error", "message": str(e)}, 500


def run_fastapi():
    """Run FastAPI server"""
    logger.info(f"Starting FastAPI server on http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API")
    logger.info("=" * 60)
    
    # Start FastAPI in background thread
    logger.info("Starting FastAPI server in background thread...")
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()
    
    # Give FastAPI time to start
    import time
    time.sleep(1)
    
    # Initialize bot
    logger.info("Initializing Telegram bot...")
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Application started")
    logger.info("Bot polling started successfully")
    
    # Run bot with run_polling (handles event loop internally)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
