#!/usr/bin/env python3
"""
Accessibility Auditor - Combined Telegram Bot + Web API
Runs both bot and FastAPI server in a single asyncio event loop
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
        "Web interface: https://localhost:3000"
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
    
    if not is_valid_url(url):
        await update.message.reply_text(f"❌ Invalid URL: {url}")
        return
    
    await update.message.chat.send_action(ChatAction.TYPING)
    
    logger.info(f"AUDIT requested for {url}")
    await update.message.reply_text(f"🔍 Analyzing {url}...\n\nThis may take a moment...")
    
    try:
        # Run audit
        result = await audit_website(url)
        
        # Save to storage
        audit_id = storage.save_audit(result)
        audit_link = f"https://yourdomain.com/audits/{audit_id}"  # Update with actual domain
        
        # Build report
        score = result.get("score", 0)
        grade = result.get("grade", "N/A")
        total = result.get("total_issues", 0)
        critical = result.get("critical", 0)
        warnings = result.get("warnings", 0)
        info = result.get("info", 0)
        
        score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        
        report = f"{score_emoji} **Score: {score}/100 ({grade})**\n\n"
        report += f"📊 **Summary:**\n"
        report += f"• Total issues: {total}\n"
        report += f"• Critical: {critical}\n"
        report += f"• Warnings: {warnings}\n"
        report += f"• Info: {info}\n\n"
        
        # Issues by category
        issues_by_cat = result.get("issues_by_category", {})
        if issues_by_cat:
            report += "**Issues Found:**\n\n"
            for category, issues in issues_by_cat.items():
                report += f"**{category}**\n"
                for issue in issues[:2]:  # Show first 2 per category
                    severity = issue.get('severity', 'info')
                    emoji = "🔴" if severity == 'critical' else "🟡" if severity == 'warning' else "🔵"
                    title = issue.get('title', 'Unknown')
                    report += f"{emoji} {title}\n"
                    
                    if len(issues) > 2 and issue == issues[1]:
                        report += f"... and {len(issues) - 2} more\n"
                
                report += "\n"
        else:
            report += "✅ No issues found! This website is very accessible.\n\n"
        
        # Truncate if too long
        if len(report) > 3500:
            report = report[:3400] + "\n\n... (see full report on web)"
        
        # Send main report
        await update.message.reply_text(report)
        
        # Send link to detailed report
        await update.message.reply_text(
            f"📖 **More details:**\n"
            f"View full report: {audit_link}"
        )
        
        logger.info(f"AUDIT completed for {url} (ID: {audit_id})")
        
    except Exception as e:
        logger.error(f"AUDIT error for {url}: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error analyzing {url}:\n\n"
            f"{str(e)[:200]}"
        )


async def start_telegram_bot():
    """Start Telegram bot in async mode"""
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audit", audit))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, audit))
    
    logger.info("Telegram bot initializing...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False  # Keep loop open for API server
    )
    
    return app


def start_api_server():
    """Start FastAPI server in background thread"""
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, HTMLResponse
        from pydantic import BaseModel
        from pathlib import Path
        import uvicorn
        
        # Create FastAPI app
        api_app = FastAPI(title="Accessibility Auditor API")
        
        # Mount static files
        web_dir = Path("web")
        if web_dir.exists():
            api_app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")
        
        # Define models
        class AuditRequest(BaseModel):
            url: str
        
        # Define extended request model
        class AuditRequestExtended(BaseModel):
            url: str
            is_public: bool = False
        
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
        
        # Run server (only localhost, nginx will proxy from outside)
        logger.info("Starting FastAPI server on http://127.0.0.1:3000 (localhost only)")
        uvicorn.run(
            api_app,
            host="127.0.0.1",
            port=3000,
            log_level="info"
        )
        
    except Exception as e:
        logger.error(f"API server error: {str(e)}", exc_info=True)


def main():
    """Main entry point - runs bot and API together"""
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API")
    logger.info("=" * 60)
    
    # Start API server in background thread
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    logger.info("API server started in background thread")
    
    # Give API time to start
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
    
    # Start Telegram bot (blocks main thread)
    try:
        asyncio.get_event_loop().run_until_complete(start_telegram_bot())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
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
