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
        return all([result.scheme, result.netloc])
    except:
        return False


# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "🔍 **Accessibility Auditor Bot**\n\n"
        "Send me a URL to audit its accessibility:\n\n"
        "Examples:\n"
        "• google.com\n"
        "• https://github.com\n\n"
        "Or use /audit <url>"
    )


async def audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audit requests"""
    user_input = None
    
    # Check if it's a command (/audit) or just text
    if update.message.text.startswith('/audit'):
        # /audit command format
        parts = update.message.text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Usage: /audit <url>")
            return
        user_input = parts[1]
    else:
        # Plain text message - treat as URL
        user_input = update.message.text
    
    # Validate and normalize URL
    url = user_input.strip()
    if not is_valid_url(url):
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
    
    if not is_valid_url(url):
        await update.message.reply_text("❌ Invalid URL. Please provide a valid website URL.")
        return
    
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
        await update.message.reply_text(f"🔍 Auditing: {url}\n\nPlease wait...")
        
        # Run audit
        report = await audit_website(url)
        audit_id = storage.save_audit(report, is_public=False)
        
        # Generate HTML report
        html_report = report_gen.generate_html(report)
        
        # Save HTML to file
        report_path = Path("audits") / f"audit_{audit_id}.html"
        report_path.write_text(html_report)
        
        # Create summary message
        summary = f"""
✅ **Audit Complete**

📊 Results:
• Errors: {len(report.get('errors', []))}
• Warnings: {len(report.get('warnings', []))}
• Info: {len(report.get('info', []))}

🔗 Full Report: https://hexdrive.tech/audits/audit_{audit_id}.html

More: https://hexdrive.tech/audits/audit_{audit_id}.html
        """
        
        await update.message.reply_text(summary)
        logger.info(f"AUDIT COMPLETE: {url} (ID: {audit_id})")
        
    except Exception as e:
        logger.error(f"Audit error for {url}: {str(e)}")
        await update.message.reply_text(f"❌ Audit failed: {str(e)}")


class TelegramBotManager:
    """Manage Telegram bot lifecycle"""
    
    def __init__(self, token: str):
        self.token = token
        self.app = None
        self.running = False
    
    async def start(self):
        """Start the bot"""
        try:
            logger.info("Telegram bot initializing...")
            self.app = Application.builder().token(self.token).build()
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", start))
            self.app.add_handler(CommandHandler("audit", audit))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, audit))
            
            # Start the application
            await self.app.initialize()
            logger.info("Bot initialized, starting polling...")
            
            # Start polling
            self.running = True
            await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("Bot polling started successfully")
            
        except Exception as e:
            logger.error(f"Telegram bot error: {str(e)}", exc_info=True)
            self.running = False
    
    async def stop(self):
        """Stop the bot gracefully"""
        try:
            if self.app and self.running:
                logger.info("Stopping bot polling...")
                await self.app.updater.stop()
                await self.app.shutdown()
                self.running = False
                logger.info("Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {str(e)}")


def run_telegram_bot_sync():
    """Run bot in a separate thread (synchronous wrapper)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot_manager = TelegramBotManager(TOKEN)
    
    try:
        loop.run_until_complete(bot_manager.start())
    except KeyboardInterrupt:
        logger.info("Bot interrupted")
        loop.run_until_complete(bot_manager.stop())
    except Exception as e:
        logger.error(f"Bot thread error: {str(e)}", exc_info=True)
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
    
    # Serve web interface
    web_dir = Path("web")
    
    @api_app.get("/")
    async def home():
        """Serve main page"""
        index_path = web_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text())
        return {"message": "Accessibility Auditor API"}
    
    @api_app.post("/api/audit")
    async def create_audit(request: AuditRequestExtended):
        """Create new audit"""
        if not request.url:
            return {"error": "URL required"}, 400
        
        url = request.url
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            report = await audit_website(url)
            audit_id = storage.save_audit(report, is_public=request.is_public)
            
            html_report = report_gen.generate_html(report)
            report_path = Path("audits") / f"audit_{audit_id}.html"
            report_path.write_text(html_report)
            
            return {
                "status": "success",
                "audit_id": audit_id,
                "report_url": f"/audits/audit_{audit_id}.html",
                "report": report
            }
        except Exception as e:
            logger.error(f"API audit error: {str(e)}")
            return {"error": str(e)}, 500
    
    @api_app.get("/audits/{filename}")
    async def get_audit(filename: str):
        """Get audit report by ID"""
        if not filename.endswith('.html'):
            filename += '.html'
        
        report_path = Path("audits") / filename
        if report_path.exists():
            return HTMLResponse(report_path.read_text())
        
        return {"error": "Audit not found"}, 404
    
    @api_app.get("/api/audits")
    async def list_audits():
        """List public audits"""
        audits = storage.list_audits(public_only=True, limit=10)
        return {"audits": audits}
    
    return api_app


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API")
    logger.info("=" * 60)
    
    # Start bot in background thread
    logger.info("Starting Telegram bot in background thread...")
    bot_thread = threading.Thread(target=run_telegram_bot_sync, daemon=True)
    bot_thread.start()
    
    # Give bot time to initialize
    import time
    time.sleep(2)
    
    # Start FastAPI server
    logger.info("Starting FastAPI server on http://127.0.0.1:3000 (localhost only)")
    api_app = create_fastapi_app()
    
    try:
        uvicorn.run(
            api_app,
            host="127.0.0.1",
            port=3000,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    except Exception as e:
        logger.error(f"Server error: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
