#!/usr/bin/env python3
"""
Accessibility Auditor - Combined Telegram Bot + Web API (FIXED)
FastAPI server on :3000, Telegram bot polling in separate thread

Key fixes:
- Proper daemon thread supervision with error recovery
- Uvicorn server configuration for stability
- Graceful shutdown handling
- Thread-safe status tracking
"""

import asyncio
import logging
import sys
import os
import threading
import json
import time
import traceback
import signal
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

# Global state for shutdown coordination
shutdown_event = threading.Event()
api_server = None
api_thread = None

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
        audit_id = storage.save_audit(audit_result)
        audit_link = f"https://hexdrive.tech/audits/{audit_id}"
        
        # Build comprehensive report - ONE MESSAGE
        score = audit_result.get("score", 0)
        grade = audit_result.get("grade", "N/A")
        total = audit_result.get("total_issues", 0)
        critical = audit_result.get("critical", 0)
        warnings = audit_result.get("warnings", 0)
        info = audit_result.get("info", 0)
        domain = urlparse(user_message).netloc or user_message
        
        score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        
        # Start report
        report = f"{score_emoji} *Accessibility Audit Report*\n\n"
        report += f"🌐 *Domain:* {domain}\n"
        report += f"⭐️ *Score:* {score}/100 ({grade})\n\n"
        report += f"🔗 *Watch on the web:*\n"
        report += f"{audit_link}\n\n"
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Issues by severity
        report += f"📊 *Issues by Severity:*\n"
        report += f"🔴 Critical: {critical}\n"
        report += f"🟡 Warnings: {warnings}\n"
        report += f"ℹ️ Info: {info}\n"
        report += f"*Total Issues: {total}*\n\n"
        
        # Issues by category
        issues_by_cat = audit_result.get("issues_by_category", {})
        if issues_by_cat:
            for category, issues in issues_by_cat.items():
                report += f"*{category}* ({len(issues)} issues)\n"
                report += f"────────────────────────────────────────\n\n"
                
                for issue in issues:
                    severity = issue.get('severity', 'info')
                    emoji = "🔴" if severity == 'critical' else "🟡" if severity == 'warning' else "🔵"
                    title = issue.get('title', 'Unknown')
                    description = issue.get('description', '')
                    recommendation = issue.get('recommendation', '')
                    
                    report += f"{emoji} *{title}*\n"
                    if description:
                        report += f"   {description}\n"
                    if recommendation:
                        report += f"   💡 {recommendation}\n"
                    report += "\n"
        else:
            report += "✅ *No issues found!* This website is very accessible.\n\n"
        
        # Truncate if too long (Telegram limit)
        if len(report) > 4000:
            report = report[:3900] + f"\n\n_See full report on web_"
        
        # Send ONE comprehensive report
        await processing_msg.edit_text(report, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Audit error: {str(e)}", exc_info=True)
        await processing_msg.edit_text(
            f"❌ Error during audit:\n\n{str(e)[:200]}"
        )


# FastAPI setup
app = FastAPI()


@app.get("/")
async def root():
    """Homepage with form"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Accessibility Auditor</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6; 
                color: #333; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { 
                max-width: 800px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 10px; 
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }
            h1 { 
                text-align: center; 
                margin-bottom: 10px;
                color: #667eea;
            }
            .subtitle {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
                font-size: 16px;
            }
            form {
                margin: 30px 0;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: 500;
            }
            input[type="text"], input[type="url"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                font-size: 16px;
                margin-bottom: 20px;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            button {
                width: 100%;
                padding: 12px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.3s;
            }
            button:hover {
                background: #764ba2;
            }
            .features {
                margin-top: 50px;
                padding-top: 30px;
                border-top: 2px solid #f0f0f0;
            }
            .features h2 {
                color: #667eea;
                margin-bottom: 20px;
            }
            .feature-list {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
            .feature {
                padding: 15px;
                background: #f5f5f5;
                border-radius: 5px;
            }
            .feature strong {
                color: #667eea;
            }
            @media (max-width: 600px) {
                .feature-list {
                    grid-template-columns: 1fr;
                }
                .container {
                    padding: 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Accessibility Auditor</h1>
            <p class="subtitle">Analyze any website for accessibility issues</p>
            
            <form onsubmit="submitAudit(event)">
                <label for="url">Website URL:</label>
                <input type="url" id="url" name="url" placeholder="https://example.com" required>
                <button type="submit">🚀 Analyze</button>
            </form>
            
            <div class="features">
                <h2>Features</h2>
                <div class="feature-list">
                    <div class="feature">
                        <strong>🎯 WCAG Compliance</strong><br>
                        Checks against WCAG 2.1 guidelines
                    </div>
                    <div class="feature">
                        <strong>♿ Semantic HTML</strong><br>
                        Validates proper HTML structure
                    </div>
                    <div class="feature">
                        <strong>🏷️ ARIA Labels</strong><br>
                        Verifies ARIA attributes
                    </div>
                    <div class="feature">
                        <strong>⌨️ Keyboard Navigation</strong><br>
                        Tests keyboard accessibility
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            async function submitAudit(event) {
                event.preventDefault();
                const url = document.getElementById('url').value;
                
                try {
                    const response = await fetch('/api/audit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url })
                    });
                    
                    const data = await response.json();
                    if (data.status === 'success') {
                        window.location.href = data.url;
                    } else {
                        alert('Error: ' + data.message);
                    }
                } catch (e) {
                    alert('Error submitting audit: ' + e.message);
                }
            }
        </script>
    </body>
    </html>
    """)


@app.get("/audits/{audit_id}")
async def get_audit(audit_id: str):
    """Get audit result by ID"""
    try:
        result = storage.get_audit(audit_id)
        if not result:
            return HTMLResponse("<h1>404 - Audit not found</h1>", status_code=404)
        
        return HTMLResponse(content=report_gen.generate_html(result))
    except Exception as e:
        logger.error(f"Error retrieving audit {audit_id}: {str(e)}")
        return HTMLResponse(f"<h1>Error: {str(e)}</h1>", status_code=500)


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
        audit_id = storage.save_audit(result)
        return {
            "status": "success",
            "audit_id": audit_id,
            "url": f"/audits/{audit_id}"
        }
    except Exception as e:
        logger.error(f"API audit error: {str(e)}")
        return {"status": "error", "message": str(e)}, 500


class UvicornServer(uvicorn.Server):
    """Custom Uvicorn server with proper shutdown handling"""
    
    def install_signal_handlers(self):
        """Override signal handling to respect our shutdown_event"""
        # Don't let uvicorn install its own handlers; we handle shutdown
        pass


def run_fastapi_server():
    """Run FastAPI server with proper error handling"""
    global api_server
    
    try:
        config = uvicorn.Config(
            app=app,
            host=API_HOST,
            port=API_PORT,
            log_level="info",
            access_log=True,
        )
        api_server = UvicornServer(config=config)
        logger.info(f"FastAPI server starting on http://{API_HOST}:{API_PORT}")
        api_server.run()
    except Exception as e:
        logger.error(f"FastAPI server error: {str(e)}")
        logger.error(traceback.format_exc())
        # Don't exit; let the main thread detect this and handle it
    finally:
        logger.info("FastAPI server thread exiting")


def run_telegram_bot():
    """Run Telegram bot with proper error handling"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info("Initializing Telegram bot...")
            application = Application.builder().token(TOKEN).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", start_handler))
            application.add_handler(CommandHandler("help", help_handler))
            application.add_handler(CommandHandler("status", status_handler))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
            
            logger.info("Application initialized")
            logger.info("Starting bot polling...")
            
            # Run bot without closing the event loop (we manage it ourselves)
            # disable stop_signals to prevent the app from catching SIGTERM/SIGINT
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,  # Don't close the event loop
                stop_signals=(signal.SIGTERM,)  # Only respond to SIGTERM
            )
            
        except Exception as e:
            retry_count += 1
            logger.error(f"Telegram bot error (attempt {retry_count}/{max_retries}): {str(e)}")
            logger.error(traceback.format_exc())
            
            if retry_count >= max_retries:
                logger.error("Max retries exceeded, giving up")
                raise
            else:
                logger.info(f"Retrying in 5 seconds...")
                time.sleep(5)
    
    logger.info("Telegram bot thread exiting")


def main():
    """Main entry point with proper daemon management"""
    global api_thread
    
    logger.info("=" * 60)
    logger.info("Accessibility Auditor Bot + API (FIXED VERSION)")
    logger.info("=" * 60)
    
    # Start FastAPI in daemon thread
    logger.info("Starting FastAPI server in daemon thread...")
    api_thread = threading.Thread(target=run_fastapi_server, daemon=True, name="FastAPI")
    api_thread.start()
    
    # Give FastAPI time to start
    time.sleep(2)
    
    # Set signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Run bot in main thread
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("Shutting down...")
        shutdown_event.set()
        sys.exit(0)


if __name__ == "__main__":
    main()
