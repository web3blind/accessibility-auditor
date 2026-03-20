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
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# x402 payment integration
try:
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.http.types import RouteConfig
    from x402.mechanisms.evm.exact import ExactEvmServerScheme
    from x402.server import x402ResourceServer
    X402_ENABLED = True
except ImportError as _x402_err:
    X402_ENABLED = False
    logger_pre = logging.getLogger(__name__)
    logger_pre.warning(f"x402 not available: {_x402_err}")

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
        "♿ *Accessibility Auditor*\n\n"
        "Send me a website URL — I'll check it for accessibility issues.\n\n"
        "Accessibility matters for:\n"
        "👁 Blind and visually impaired users\n"
        "🦽 People with disabilities\n"
        "🤖 AI agents and web scrapers — they read your site as text, just like a screen reader\n"
        "🔍 Search engine crawlers (SEO)\n\n"
        "Poor markup = invisible content for all of the above.\n\n"
        "Example: https://example.com\n\n"
        "Web: https://hexdrive.tech",
        parse_mode="Markdown"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "📋 *How to use Accessibility Auditor:*\n\n"
        "1. Send any website URL\n"
        "2. Bot analyzes accessibility\n"
        "3. Get detailed report with score\n"
        "4. View results on web: https://hexdrive.tech\n\n"
        "*Why accessibility matters:*\n"
        "Not just for people with disabilities — AI agents, chatbots, and web scrapers "
        "all parse your site as plain text. Bad markup = broken experience for humans and machines alike.\n\n"
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
app = FastAPI(
    title="Accessibility Auditor",
    description="WCAG 2.1 accessibility auditing. Free: POST /api/audit. Paid via x402: POST /api/audit/paid",
    version="2.0.0"
)

# x402 setup - payment middleware for /api/audit/paid
_X402_SERVER_ADDRESS = os.getenv("X402_SERVER_ADDRESS", "0x69a01903E635587C3e28DaAfF5DB82B369447e76")
_X402_NETWORK = os.getenv("X402_NETWORK", "eip155:84532")  # Base Sepolia (public x402.org facilitator only supports testnet)
_X402_PRICE = "$0.10"
_X402_FACILITATOR = os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")

if X402_ENABLED:
    try:
        _x402_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=_X402_FACILITATOR))
        _x402_srv = x402ResourceServer(_x402_facilitator)
        _x402_srv.register(_X402_NETWORK, ExactEvmServerScheme())
        _x402_routes = {
            "POST /api/audit/paid": RouteConfig(
                accepts=[PaymentOption(
                    scheme="exact",
                    pay_to=_X402_SERVER_ADDRESS,
                    price=_X402_PRICE,
                    network=_X402_NETWORK,
                )],
                mime_type="application/json",
                description="Accessibility audit (WCAG 2.1) — pay per audit",
            ),
        }
        app.add_middleware(PaymentMiddlewareASGI, routes=_x402_routes, server=_x402_srv)
        logging.getLogger(__name__).info(
            f"x402 enabled: address={_X402_SERVER_ADDRESS}, price={_X402_PRICE}, network={_X402_NETWORK}"
        )
    except Exception as _xe:
        X402_ENABLED = False
        logging.getLogger(__name__).warning(f"x402 setup failed: {_xe}")


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
                const btn = event.target.querySelector('button');
                btn.disabled = true;
                btn.textContent = '⏳ Submitting...';

                try {
                    const response = await fetch('/api/audit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url })
                    });

                    const data = await response.json();
                    if (response.ok && data.audit_id) {
                        window.location.href = '/audits/' + data.audit_id + '/pending';
                    } else {
                        alert('Error: ' + (data.error || 'Unknown error'));
                        btn.disabled = false;
                        btn.textContent = '🚀 Analyze';
                    }
                } catch (e) {
                    alert('Error: ' + e.message);
                    btn.disabled = false;
                    btn.textContent = '🚀 Analyze';
                }
            }
        </script>
    </body>
    </html>
    """)


@app.get("/audits/{audit_id}/pending")
async def audit_pending(audit_id: str):
    """Waiting page — polls until audit is ready, then redirects"""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analyzing... — Accessibility Auditor</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 60px 40px;
            text-align: center;
            max-width: 480px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .spinner {{
            width: 64px;
            height: 64px;
            border: 6px solid #e9ecef;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 30px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        h1 {{ font-size: 1.6em; color: #333; margin-bottom: 12px; }}
        p {{ color: #666; font-size: 1em; line-height: 1.6; }}
        .dots::after {{
            content: '';
            animation: dots 1.5s steps(4, end) infinite;
        }}
        @keyframes dots {{
            0%   {{ content: ''; }}
            25%  {{ content: '.'; }}
            50%  {{ content: '..'; }}
            75%  {{ content: '...'; }}
        }}
        .elapsed {{ margin-top: 20px; color: #999; font-size: 0.85em; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="spinner"></div>
        <h1>Analyzing<span class="dots"></span></h1>
        <p>Running a full headless browser audit.<br>This usually takes 15–30 seconds.</p>
        <p class="elapsed" id="elapsed">Elapsed: 0s</p>
    </div>
    <script>
        const start = Date.now();
        const auditId = "{audit_id}";

        const timer = setInterval(() => {{
            const s = Math.floor((Date.now() - start) / 1000);
            document.getElementById('elapsed').textContent = 'Elapsed: ' + s + 's';
        }}, 1000);

        async function poll() {{
            try {{
                const r = await fetch('/api/audit/' + auditId + '/status');
                const d = await r.json();
                if (d.ready) {{
                    clearInterval(timer);
                    window.location.href = '/audits/' + auditId;
                    return;
                }}
            }} catch(e) {{}}
            setTimeout(poll, 2000);
        }}

        setTimeout(poll, 2000);
    </script>
</body>
</html>""")


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
async def submit_audit(request: AuditRequest, raw_request: Request):
    """Free audit — only accessible from the website UI (not for external agents/API clients).
    For programmatic access use POST /api/audit/paid (x402, 0.10 USDC on Base Mainnet).
    """
    # Only allow requests originating from hexdrive.tech itself
    referer = raw_request.headers.get("referer", "")
    origin = raw_request.headers.get("origin", "")
    allowed_host = "hexdrive.tech"
    if not any(allowed_host in h for h in [referer, origin]):
        return JSONResponse(
            {
                "error": "Free audit is only available via the website UI.",
                "paid_endpoint": "POST /api/audit/paid",
                "docs": "https://hexdrive.tech/api/x402/info",
            },
            status_code=403,
        )

    url = request.url.strip()

    if not is_valid_url(url):
        return JSONResponse({"error": "Invalid URL format"}, status_code=400)

    audit_id = storage.generate_id()

    async def run_audit_bg():
        try:
            result = await audit_website(url)
            storage.save_audit_with_id(audit_id, result)
        except Exception as e:
            logger.error(f"Background audit error: {e}")
            storage.save_audit_with_id(audit_id, {
                "url": url, "score": 0, "grade": "F (Fail)",
                "total_issues": 1, "critical": 1, "warnings": 0, "info": 0,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "issues_by_category": {"Network": [{"severity": "critical",
                    "title": "Audit Failed", "description": str(e),
                    "element": None, "recommendation": None}]}
            })

    asyncio.create_task(run_audit_bg())
    return {"audit_id": audit_id}


@app.get("/api/audit/{audit_id}/status")
async def audit_status(audit_id: str):
    """Check if audit is ready, and return full result if so (for polling)"""
    result = storage.get_audit(audit_id)
    if result is None:
        return {"status": "pending", "ready": False}
    if result.get("error"):
        return {"status": "error", "error": result["error"]}
    return {
        "status": "complete",
        "ready": True,
        "audit_id": audit_id,
        "url": result.get("url"),
        "score": result.get("score"),
        "grade": result.get("grade"),
        "total_issues": result.get("total_issues"),
        "critical": result.get("critical"),
        "warnings": result.get("warnings"),
        "info": result.get("info"),
        "issues_by_category": result.get("issues_by_category", {}),
    }


@app.post("/api/audit/paid")
async def submit_paid_audit(request: AuditRequest):
    """
    Paid accessibility audit via x402 (0.10 USDC on Base Mainnet).
    x402 middleware intercepts this route — client must pay before getting response.
    On successful payment, runs full audit and returns JSON report.
    """
    url = request.url.strip()
    if not is_valid_url(url):
        return JSONResponse({"error": "Invalid URL format"}, status_code=400)

    try:
        result = await audit_website(url)
        audit_id = storage.generate_id()
        storage.save_audit_with_id(audit_id, result)
        return {
            "paid": True,
            "audit_id": audit_id,
            "report_url": f"https://hexdrive.tech/audits/{audit_id}",
            "payment_network": _X402_NETWORK if X402_ENABLED else "disabled",
            **result
        }
    except Exception as e:
        logger.error(f"Paid audit error for {url}: {e}")
        return JSONResponse({"error": f"Audit failed: {e}"}, status_code=500)


@app.get("/api/x402/info")
async def x402_info():
    """x402 payment info — discovery endpoint for AI agents"""
    return {
        "enabled": X402_ENABLED,
        "paid_endpoint": "POST /api/audit/paid",
        "price": _X402_PRICE if X402_ENABLED else None,
        "network": _X402_NETWORK if X402_ENABLED else None,
        "network_name": "Base Mainnet" if _X402_NETWORK == "eip155:8453" else "Base Sepolia (testnet)",
        "pay_to": _X402_SERVER_ADDRESS if X402_ENABLED else None,
        "facilitator": _X402_FACILITATOR if X402_ENABLED else None,
        "token": "USDC" if _X402_NETWORK == "eip155:8453" else "testUSDC",
        "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" if _X402_NETWORK == "eip155:8453" else "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "description": "Accessibility audit service. WCAG 2.1 compliance check. Pay per request via x402. Free audits available at https://hexdrive.tech (website only).",
    }


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
            # Ensure there's an event loop in this thread (needed when uvicorn runs in another thread)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("loop closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
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
