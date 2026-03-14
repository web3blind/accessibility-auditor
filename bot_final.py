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
        
        # Build complete summary message with domain and rating
        score = audit_result.get("score", 0)
        issues = audit_result.get("issues", {})
        domain = urlparse(user_message).netloc or user_message
        
        summary = f"🔍 *{domain}*\n"
        summary += f"⭐️ *Rating: {score}%*\n\n"
        summary += "📊 *Issues Found:*\n"
        
        for category, count in issues.items():
            if count > 0:
                summary += f"• {category.title()}: {count}\n"
        
        summary += f"\n🌐 *View full report:*\n"
        summary += f"https://hexdrive.tech/audits/{audit_id}"
        
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
            .feature-item {
                display: flex;
                gap: 10px;
            }
            .feature-item::before {
                content: "✓";
                color: #667eea;
                font-weight: bold;
                min-width: 20px;
            }
            .about {
                background: #f9f9f9;
                padding: 20px;
                border-radius: 5px;
                margin: 30px 0;
                border-left: 4px solid #667eea;
            }
            .about p {
                margin-bottom: 10px;
            }
            .about p:last-child {
                margin-bottom: 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Accessibility Auditor</h1>
            <p class="subtitle">WCAG 2.1 & GOST Compliance Analysis</p>
            
            <div class="about">
                <p><strong>About:</strong> Autonomous AI agent analyzing websites for accessibility compliance. Built for blind and low-vision developers.</p>
                <p><strong>How to use:</strong> Enter any website URL below and get a detailed accessibility report.</p>
            </div>
            
            <form>
                <label for="url">Website URL:</label>
                <input type="url" id="url" name="url" placeholder="https://example.com" required>
                <button type="submit">Analyze Website</button>
            </form>
            
            <div class="features">
                <h2>Key Features</h2>
                <div class="feature-list">
                    <div class="feature-item">WCAG 2.1 AA compliance</div>
                    <div class="feature-item">Color contrast analysis</div>
                    <div class="feature-item">Alt text validation</div>
                    <div class="feature-item">Heading hierarchy</div>
                    <div class="feature-item">Keyboard navigation</div>
                    <div class="feature-item">Form labels</div>
                    <div class="feature-item">GOST compatibility</div>
                    <div class="feature-item">HTML reports</div>
                </div>
            </div>
        </div>
        
        <script>
            document.querySelector('form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const url = document.getElementById('url').value;
                const btn = e.target.querySelector('button');
                btn.disabled = true;
                btn.textContent = 'Analyzing...';
                
                try {
                    const response = await fetch('/api/audit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url })
                    });
                    const data = await response.json();
                    if (response.ok) {
                        window.location.href = data.url;
                    } else {
                        alert('Error: ' + (data.message || 'Unknown error'));
                        btn.disabled = false;
                        btn.textContent = 'Analyze Website';
                    }
                } catch (err) {
                    alert('Error: ' + err.message);
                    btn.disabled = false;
                    btn.textContent = 'Analyze Website';
                }
            });
        </script>
    </body>
    </html>
    """)


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
