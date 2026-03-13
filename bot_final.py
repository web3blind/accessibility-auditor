#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction
from auditor import audit_website
from urllib.parse import urlparse

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/root/.hermes/agents/accessibility-auditor/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"START from {update.effective_user.id}")
    await update.message.reply_text(
        "🤖 Hermes Agent - Accessibility Auditor\n\n"
        "Analyzes websites for WCAG 2.1 compliance\n\n"
        "Usage:\n"
        "/audit https://example.com\n\n"
        "What we check:\n"
        "✅ Semantic HTML\n"
        "✅ Image alt text\n"
        "✅ Link quality\n"
        "✅ Heading structure\n"
        "✅ Forms\n"
        "✅ Keyboard navigation\n"
        "✅ And more..."
    )

async def audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /audit <URL>\nExample: /audit https://example.com")
        return

    url = context.args[0]
    
    if not is_valid_url(url):
        await update.message.reply_text(f"❌ Invalid URL: {url}")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    
    logger.info(f"AUDIT requested for {url}")
    await update.message.reply_text(f"🔍 Analyzing {url}...\n\nThis may take a moment...")
    
    try:
        result = await asyncio.to_thread(audit_website, url)
        
        score = result.get("score", 0)
        score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        
        report = f"{score_emoji} **WCAG 2.1 Score: {score}%**\n\n"
        
        checks = result.get("checks", [])
        passed = sum(1 for c in checks if c["status"] == "✅ Pass")
        failed = sum(1 for c in checks if c["status"] == "❌ Fail")
        
        report += f"Passed: {passed}/{len(checks)}\n"
        report += f"Failed: {failed}/{len(checks)}\n\n"
        
        report += "**Issues Found:**\n"
        for check in checks:
            if check["status"] != "✅ Pass":
                report += f"\n• {check['category']}: {check['status']}\n"
                report += f"  {check['recommendation']}\n"
        
        if len(report) > 4096:
            report = report[:4000] + "\n\n... (truncated)"
        
        await update.message.reply_text(report, parse_mode='MarkdownV2')
        logger.info(f"AUDIT completed for {url}")
        
    except Exception as e:
        logger.error(f"AUDIT error for {url}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error analyzing {url}:\n{str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audit", audit))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, audit))
    
    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
