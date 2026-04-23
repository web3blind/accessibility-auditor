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
CONFIG_PATH = Path("/root/accessibility-auditor-service/config.json")
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
        logging.FileHandler('/root/accessibility-auditor-service/bot.log'),
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


def _build_short_telegram_report(audit_result: dict, audit_link: str, source_url: str) -> str:
    """Compact bot summary. Full detail stays on the website report."""
    score = audit_result.get("score", 0)
    grade = audit_result.get("grade", "N/A")
    total = audit_result.get("total_issues", 0)
    critical = audit_result.get("critical", 0)
    warnings = audit_result.get("warnings", 0)
    info = audit_result.get("info", 0)
    domain = urlparse(source_url).netloc or source_url
    score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"

    report = [
        f"{score_emoji} *Accessibility Audit*",
        "",
        f"🌐 *Site:* {domain}",
        f"⭐ *Score:* {score}/100 ({grade})",
        f"📊 *Findings:* {total} total — 🔴 {critical} / 🟡 {warnings} / ℹ️ {info}",
        "",
    ]

    summary = (audit_result.get("summary") or {}).get("overall_assessment")
    if summary:
        report.extend([summary, ""])

    top_findings = audit_result.get("top_findings") or []
    if top_findings:
        report.append("*Top findings:*")
        for issue in top_findings[:5]:
            severity = issue.get("severity", "info")
            emoji = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "🔵"
            title = issue.get("title", "Issue")
            recommendation = issue.get("recommendation")
            report.append(f"{emoji} {title}")
            if recommendation:
                report.append(f"   💡 {recommendation}")
        report.append("")
    elif total == 0:
        report.extend(["✅ Автоматические проверки не нашли проблем.", ""])

    report.extend([
        "Полная подробная версия отчёта доступна на сайте:",
        audit_link,
        "",
        "_В Telegram показывается краткая версия, чтобы отчёт не обрезался._",
    ])

    text = "\n".join(report)
    if len(text) > 4000:
        text = text[:3850] + f"\n\nПолный отчёт: {audit_link}"
    return text


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
        "/status - Check bot status\n"
        "/arc - Arc Network info & agent identity\n\n"
        "*Questions?* Contact @web3blind",
        parse_mode="Markdown"
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    await update.message.reply_text(
        "✅ Bot is online and ready!\n\n"
        "Send a URL to start auditing."
    )


async def arc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /arc command - show Arc Network integration info"""
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("https://rpc.testnet.arc.network"))

        wallet = os.getenv("EVM_SERVER_ADDRESS", os.getenv("X402_SERVER_ADDRESS", ""))
        if not wallet:
            return jsonify({"error": "EVM_SERVER_ADDRESS not configured"}), 500
        balance = w3.eth.get_balance(wallet)
        balance_usdc = float(Web3.from_wei(balance, "ether"))

        # Load agent registration info
        reg_path = os.path.join(os.path.dirname(__file__), "erc8004_registration.json")
        agent_info = ""
        if os.path.exists(reg_path):
            with open(reg_path) as f:
                reg = json.load(f)
            agent_id = reg.get("agent_id", "N/A")
            agent_info = (
                f"\n🤖 *ERC-8004 Agent Identity*\n"
                f"Agent ID: #{agent_id}\n"
                f"Registry: IdentityRegistry\n"
                f"Token: AGENT NFT\n"
                f"Explorer: [View Agent](https://testnet.arcscan.app/token/0x8004A818BFB912233c491871b3d84c89A494BD9e/instance/{agent_id})\n"
            )

        await update.message.reply_text(
            "🔵 *Arc Network Integration*\n\n"
            f"*Network:* Arc Testnet (Circle L1)\n"
            f"*Chain ID:* 5042002\n"
            f"*Gas Token:* USDC (native)\n"
            f"*Wallet:* `{wallet[:10]}...{wallet[-6:]}`\n"
            f"*Balance:* {balance_usdc:.4f} USDC\n"
            f"{agent_info}\n"
            "💳 *x402 Payment*\n"
            "Pay for audits with USDC on Arc Testnet!\n"
            "Endpoint: POST /api/audit/paid\n"
            "Price: $0.10 USDC\n\n"
            "🔗 [Arc Explorer](https://testnet.arcscan.app)\n"
            "🚰 [Get testnet USDC](https://faucet.circle.com/)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Arc Network info unavailable: {str(e)[:100]}\n\n"
            "Try again later."
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
        
        # Send compact bot summary. Full details stay on the web report.
        report = _build_short_telegram_report(audit_result, audit_link, user_message)
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
_X402_SERVER_ADDRESS = os.getenv("EVM_SERVER_ADDRESS", os.getenv("X402_SERVER_ADDRESS", ""))
_X402_PRICE = "$0.10"
_X402_FACILITATOR = os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")

# Supported networks
_X402_NETWORKS = {
    "base_sepolia": {
        "name": "Base Sepolia (testnet)",
        "evm_network": "eip155:84532",
        "chain_id": 84532,
        "usdc_is_native": False,
    },
    "arc_testnet": {
        "name": "Arc Testnet (Circle L1)",
        "evm_network": "eip155:5042002",
        "chain_id": 5042002,
        "usdc_is_native": True,
    },
}
_X402_ACTIVE = os.getenv("X402_NETWORK_KEY", "arc_testnet")
_X402_NETWORK = _X402_NETWORKS[_X402_ACTIVE]["evm_network"]

if X402_ENABLED:
    try:
        _x402_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=_X402_FACILITATOR))
        _x402_srv = x402ResourceServer(_x402_facilitator)

        # Register networks supported by the facilitator
        # NOTE: x402.org facilitator currently only supports Base Sepolia & Base Mainnet
        # Arc Testnet support is pending — we track it in _X402_NETWORKS for info
        _x402_facilitator_networks = ["base_sepolia"]  # Only register what facilitator supports
        _x402_payment_options = []
        for _nk in _x402_facilitator_networks:
            _nv = _X402_NETWORKS[_nk]
            _x402_srv.register(_nv["evm_network"], ExactEvmServerScheme())
            _x402_payment_options.append(PaymentOption(
                scheme="exact",
                pay_to=_X402_SERVER_ADDRESS,
                price=_X402_PRICE,
                network=_nv["evm_network"],
            ))

        _x402_routes = {
            "POST /api/audit/paid": RouteConfig(
                accepts=_x402_payment_options,
                mime_type="application/json",
                description="Accessibility audit (WCAG 2.1) — pay with USDC on Base Sepolia or Arc Testnet",
            ),
        }
        app.add_middleware(PaymentMiddlewareASGI, routes=_x402_routes, server=_x402_srv)
        logging.getLogger(__name__).info(
            f"x402 enabled: address={_X402_SERVER_ADDRESS}, price={_X402_PRICE}, "
            f"networks={list(_X402_NETWORKS.keys())}"
        )
    except Exception as _xe:
        X402_ENABLED = False
        logging.getLogger(__name__).warning(f"x402 setup failed: {_xe}")


@app.get("/")
async def root():
    """Homepage with form"""
    web_index = Path("/root/accessibility-auditor-service/web/index.html")
    if web_index.exists():
        return FileResponse(str(web_index), media_type="text/html")
    return HTMLResponse("<h1>Accessibility Auditor</h1><p>Frontend not found.</p>")


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
    is_public: bool = False


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
            storage.save_audit_with_id(audit_id, result, is_public=request.is_public)
        except Exception as e:
            logger.error(f"Background audit error: {e}")
            storage.save_audit_with_id(audit_id, {
                "url": url,
                "score": 0,
                "grade": "F (Fail)",
                "total_issues": 1,
                "critical": 1,
                "warnings": 0,
                "info": 0,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "summary": {"overall_assessment": "Аудит завершился ошибкой до формирования полного отчёта."},
                "findings_by_severity": {
                    "critical": [{
                        "category": "Network",
                        "severity": "critical",
                        "title": "Audit Failed",
                        "description": str(e),
                        "element": None,
                        "recommendation": "Проверьте доступность сайта и повторите попытку.",
                        "wcag": "N/A",
                    }],
                    "warning": [],
                    "info": [],
                },
                "issues_by_category": {"Network": [{
                    "category": "Network",
                    "severity": "critical",
                    "title": "Audit Failed",
                    "description": str(e),
                    "element": None,
                    "recommendation": "Проверьте доступность сайта и повторите попытку.",
                    "wcag": "N/A",
                }]},
                "passed_checks": [],
                "manual_checks": [],
                "next_steps": ["Повторить аудит после проверки сети/доступности URL."],
            }, is_public=request.is_public)

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
        "summary": result.get("summary", {}),
        "top_findings": result.get("top_findings", []),
        "issues_by_category": result.get("issues_by_category", {}),
    }


@app.get("/api/audits")
async def list_audits(limit: int = 10, public_only: bool = False):
    """List recent audits for the website gallery."""
    return storage.list_audits(limit=limit, public_only=public_only)


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
        storage.save_audit_with_id(audit_id, result, is_public=request.is_public)
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
    if not X402_ENABLED:
        return {"enabled": False, "reason": "x402 SDK not available"}

    networks_info = {}
    for nk, nv in _X402_NETWORKS.items():
        networks_info[nk] = {
            "name": nv["name"],
            "evm_network": nv["evm_network"],
            "chain_id": nv["chain_id"],
            "usdc_is_native": nv["usdc_is_native"],
        }

    return {
        "enabled": True,
        "paid_endpoint": "POST /api/audit/paid",
        "price": _X402_PRICE,
        "pay_to": _X402_SERVER_ADDRESS,
        "facilitator": _X402_FACILITATOR,
        "active_network": _X402_ACTIVE,
        "networks": networks_info,
        "erc8004_agent_id": 963,
        "erc8004_registry": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        "description": (
            "Accessibility Auditor — WCAG 2.1 compliance check with x402 payments. "
            "Accepts USDC on Base Sepolia (ERC-20) or Arc Testnet (native USDC gas token). "
            "ERC-8004 registered AI agent on Arc Network."
        ),
    }


@app.get("/schemas/accessibility-audit-report.schema.json")
async def get_accessibility_audit_schema():
    """Expose the MCP-friendly JSON schema for future MCP/API consumers."""
    schema_path = Path("/root/accessibility-auditor-service/schemas/accessibility-audit-report.schema.json")
    if not schema_path.exists():
        return JSONResponse({"error": "Schema not found"}, status_code=404)
    return JSONResponse(content=json.loads(schema_path.read_text(encoding="utf-8")))


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
            application.add_handler(CommandHandler("arc", arc_handler))
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
