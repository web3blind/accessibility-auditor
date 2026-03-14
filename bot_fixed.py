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
from pathlib import Path
import uvicorn
import json

# Setup
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set")
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
    logger.info(f"START from {update.effective_user.id}")
    await update.message.reply_text(
        "🤖 Hermes Agent - Accessibility Auditor\n\n"
        "Analyzes websites for WCAG 2.1 & GOST compliance\n\n"
        "Usage:\n"
        "/audit https://example.com\n\n"
        "What we check:\n"
        "✅ Semantic HTML\n"
        "✅ Image alt text\n"
        "✅ Link quality\n"
        "✅ Heading structure\n"
        "✅ Forms\n"
        "✅ Keyboard navigation\n"
        "✅ ARIA attributes\n"
        "✅ Media captions\n"
        "✅ Contrast ratios\n"
        "✅ Language declaration\n"
        "✅ Page structure\n"
        "✅ Responsive design\n\n"
        "Web interface: https://hexdrive.tech"
    )


async def audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /audit command or URL submission"""
    url = None
    
    # Check if it's a command or plain text
    if context.args:
        url = context.args[0]
    elif update.message.text and not update.message.text.startswith('/'):
        url = update.message.text.strip()
    
    if not url:
        await update.message.reply_text(
            "❌ Usage: /audit <URL>\n"
            "Example: /audit https://example.com"
        )
        return
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Validate URL
    if not is_valid_url(url):
        await update.message.reply_text("❌ Invalid URL format")
        return
    
    # Send typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)
    await update.message.reply_text(f"🔍 Auditing {url}...\nThis may take a minute...")
    
    try:
        logger.info(f"AUDIT START: {url}")
        report = await audit_website(url)
        
        # Save to storage
        audit_id = storage.save_audit(report, is_public=False)
        
        # Generate HTML report
        html_report = report_gen.generate_html(report)
        
        # Create summary message
        summary = (
            f"📊 Audit Complete for {url}\n\n"
            f"Score: {report.get('overall_score', 'N/A')}%\n\n"
            f"View Full Report: https://hexdrive.tech/audits/{audit_id}\n\n"
            f"Key Findings:\n"
        )
        
        # Add issues if any
        issues = report.get('issues', [])
        if issues:
            for issue in issues[:5]:  # Show top 5
                summary += f"• {issue.get('message', 'Unknown issue')}\n"
            if len(issues) > 5:
                summary += f"\n... and {len(issues) - 5} more issues"
        else:
            summary += "✅ No critical issues found!"
        
        await update.message.reply_text(summary)
        logger.info(f"AUDIT COMPLETE: {url} (ID: {audit_id})")
        
    except Exception as e:
        logger.error(f"Audit error for {url}: {str(e)}")
        await update.message.reply_text(f"❌ Audit failed: {str(e)}")


async def run_telegram_bot_async():
    """Run Telegram bot with proper async handling"""
    try:
        app = Application.builder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("audit", audit))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, audit))
        
        logger.info("Telegram bot initializing...")
        
        # Use start/stop instead of run_polling to avoid signal handler issues
        async with app:
            await app.start()
            logger.info("Bot polling started")
            # This will block and poll for updates
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Telegram bot error: {str(e)}", exc_info=True)
    finally:
        try:
            if app.running:
                await app.stop()
        except:
            pass


def run_telegram_bot():
    """Run Telegram bot in separate thread"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_telegram_bot_async())
    except Exception as e:
        logger.error(f"Telegram bot thread error: {str(e)}", exc_info=True)
    finally:
        try:
            loop.close()
        except:
            pass


def create_fastapi_app():
    """Create and configure FastAPI application"""
    api_app = FastAPI(title="Accessibility Auditor API")
    
    # Define request model
    class AuditRequestExtended(BaseModel):
        url: str
        is_public: bool = False
    
    # Serve static files if they exist
    web_dir = Path("web")
    if web_dir.exists():
        try:
            from fastapi.staticfiles import StaticFiles
            api_app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")
        except:
            pass
    
    # API endpoints
    @api_app.post("/api/audit")
    async def create_audit(request: AuditRequestExtended):
        if not request.url:
            return {"error": "URL required"}, 400
        
        url = request.url
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            report = await audit_website(url)
            audit_id = storage.save_audit(report, is_public=request.is_public)
            return {
                "audit_id": audit_id,
                "message": f"Audit completed. View results at /audits/{audit_id}"
            }
        except Exception as e:
            logger.error(f"API audit error: {str(e)}")
            return {"error": str(e)}, 500
    
    @api_app.get("/audits/{audit_id}")
    async def get_audit_html(audit_id: str):
        report = storage.get_audit(audit_id)
        if not report:
            return HTMLResponse("<h1>404 - Audit not found</h1>", status_code=404)
        
        html = report_gen.generate_html(report)
        return HTMLResponse(content=html)
    
    @api_app.get("/")
    async def serve_root():
        web_index = Path("web/index.html")
        if web_index.exists():
            return FileResponse(str(web_index), media_type="text/html")
        return HTMLResponse("<h1>Accessibility Auditor</h1><p>Web interface loading...</p>")
    
    @api_app.get("/api/audits")
    async def list_audits(limit: int = 10, public_only: bool = True):
        return storage.list_audits(limit, public_only=public_only)
    
    @api_app.get("/health")
    async def health_check():
        return {"status": "ok"}
    
    return api_app


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API")
    logger.info("=" * 60)
    
    # Create FastAPI app
    api_app = create_fastapi_app()
    
    # Start Telegram bot in separate thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    logger.info("Telegram bot started in background thread")
    
    # Give bot time to initialize
    import time
    time.sleep(2)
    
    # Start FastAPI server (blocks main thread)
    try:
        logger.info("Starting FastAPI server on http://127.0.0.1:3000 (localhost only)")
        uvicorn.run(
            api_app,
            host="127.0.0.1",
            port=3000,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"API server error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Startup error: {str(e)}", exc_info=True)
        sys.exit(1)
