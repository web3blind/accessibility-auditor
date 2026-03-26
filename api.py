#!/usr/bin/env python3
"""
FastAPI server for Accessibility Auditor
Provides REST API and serves web frontend

x402 payment integration:
- /api/audit/paid  - requires payment via x402 (0.10 USDC)
- /api/audit       - free endpoint (unchanged)

Supports multiple networks:
- Base Sepolia (testnet) - original
- Arc Testnet (Circle L1) - USDC as native gas token
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import logging
import json
from typing import Optional

from auditor import audit_website
from storage import AuditStorage
from report_generator import ReportGenerator

# x402 imports
try:
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.http.types import RouteConfig
    from x402.mechanisms.evm.exact import ExactEvmServerScheme
    from x402_config import (
        SERVER_EVM_ADDRESS, EVM_NETWORK,
        FACILITATOR_URL, AUDIT_PRICE_USD,
        get_network_config, NETWORKS, ACTIVE_NETWORK
    )
    X402_ENABLED = True
    x402_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))

    from x402.server import x402ResourceServer
    x402_server = x402ResourceServer(x402_facilitator)

    # Register all available networks
    for net_key, net_cfg in NETWORKS.items():
        x402_server.register(net_cfg["evm_network"], ExactEvmServerScheme())

    # Build payment options for all supported networks
    payment_options = []
    for net_key, net_cfg in NETWORKS.items():
        payment_options.append(
            PaymentOption(
                scheme="exact",
                pay_to=SERVER_EVM_ADDRESS,
                price=AUDIT_PRICE_USD,
                network=net_cfg["evm_network"],
            )
        )

    x402_routes = {
        "POST /api/audit/paid": RouteConfig(
            accepts=payment_options,
            mime_type="application/json",
            description="Accessibility audit report (WCAG 2.1 compliance check). Pay with USDC on Base Sepolia or Arc Testnet.",
        ),
    }

    _active_net = get_network_config()
    logging.getLogger(__name__).info(
        f"x402 enabled: server={SERVER_EVM_ADDRESS}, "
        f"active_network={_active_net['name']} ({EVM_NETWORK}), "
        f"price={AUDIT_PRICE_USD}, "
        f"supported_networks={list(NETWORKS.keys())}"
    )
except Exception as e:
    X402_ENABLED = False
    x402_routes = {}
    x402_server = None
    logging.getLogger(__name__).warning(f"x402 not available: {e}")


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
app = FastAPI(
    title="Accessibility Auditor API",
    description=(
        "WCAG 2.1 accessibility auditing service with x402 payments. "
        "Supports USDC on Base Sepolia and Arc Testnet (Circle L1). "
        "Free endpoint: /api/audit. Paid (x402): /api/audit/paid"
    ),
    version="3.0.0"
)
storage = AuditStorage()
report_gen = ReportGenerator()

# Serve static files if they exist
web_dir = Path("web")
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


# Apply x402 middleware (only intercepts /api/audit/paid)
if X402_ENABLED and x402_server:
    app.add_middleware(PaymentMiddlewareASGI, routes=x402_routes, server=x402_server)
    logger.info("x402 PaymentMiddlewareASGI registered")


class AuditRequest(BaseModel):
    """Request model for audit endpoint"""
    url: str


class AuditResponse(BaseModel):
    """Response model for audit endpoint"""
    audit_id: str
    message: str


@app.post("/api/audit")
async def create_audit(request: AuditRequest, background_tasks: BackgroundTasks) -> AuditResponse:
    """
    Start a new accessibility audit (FREE endpoint)
    Returns audit ID immediately (processing happens in background)
    """
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Normalize URL
    url = request.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Run audit and save immediately (synchronous for web requests)
    try:
        report = await audit_website(url)
        audit_id = storage.save_audit(report)

        return AuditResponse(
            audit_id=audit_id,
            message=f"Audit completed. View results at /audits/{audit_id}"
        )
    except Exception as e:
        logger.error(f"Audit failed for {url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")


@app.post("/api/audit/paid")
async def create_paid_audit(request: AuditRequest) -> dict:
    """
    Paid accessibility audit via x402 (0.10 USDC).

    Accepts payment on:
    - Base Sepolia (eip155:84532) - USDC ERC-20
    - Arc Testnet (eip155:5042002) - USDC native gas token

    Payment flow:
    1. Client sends POST request without payment header
    2. Server responds 402 with payment instructions for all supported networks
    3. Client pays on their preferred network and retries with X-PAYMENT header
    4. Middleware verifies payment, server runs audit and returns full report
    """
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Normalize URL
    url = request.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        report = await audit_website(url)
        audit_id = storage.save_audit(report)

        # Return full JSON report (paid clients get immediate full data)
        return {
            "audit_id": audit_id,
            "report_url": f"https://hexdrive.tech/audits/{audit_id}",
            "paid": True,
            "payment_networks": {
                net_key: net_cfg["name"]
                for net_key, net_cfg in NETWORKS.items()
            } if X402_ENABLED else {},
            **report
        }
    except Exception as e:
        logger.error(f"Paid audit failed for {url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")


@app.get("/audits/{audit_id}")
async def get_audit_html(audit_id: str) -> HTMLResponse:
    """
    Get audit report as beautiful HTML
    """
    report = storage.get_audit(audit_id)

    if not report:
        raise HTTPException(status_code=404, detail="Audit not found")

    html = report_gen.generate_html(report)
    return HTMLResponse(content=html)


@app.get("/")
async def serve_root() -> HTMLResponse:
    """
    Serve the main web interface
    """
    web_index = Path("web/index.html")

    if web_index.exists():
        return FileResponse(str(web_index), media_type="text/html")

    # Fallback if index.html doesn't exist yet
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Accessibility Auditor</title>
    </head>
    <body>
        <h1>Accessibility Auditor</h1>
        <p>Loading...</p>
    </body>
    </html>
    """)


@app.get("/api/audits")
async def list_audits(limit: int = 10):
    """
    List recent audits
    """
    return storage.list_audits(limit)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    active_net = get_network_config() if X402_ENABLED else {}
    return {
        "status": "ok",
        "x402_enabled": X402_ENABLED,
        "x402_server_address": SERVER_EVM_ADDRESS if X402_ENABLED else None,
        "x402_active_network": active_net.get("name") if X402_ENABLED else None,
        "x402_supported_networks": list(NETWORKS.keys()) if X402_ENABLED else [],
        "x402_price": AUDIT_PRICE_USD if X402_ENABLED else None,
    }


@app.get("/api/x402/info")
async def x402_info():
    """x402 payment info for this service — lists all supported networks"""
    if not X402_ENABLED:
        return {"enabled": False, "reason": "x402 SDK not available"}

    networks_info = {}
    for net_key, net_cfg in NETWORKS.items():
        networks_info[net_key] = {
            "name": net_cfg["name"],
            "evm_network": net_cfg["evm_network"],
            "chain_id": net_cfg["chain_id"],
            "explorer": net_cfg["explorer"],
            "faucet": net_cfg["faucet"],
            "usdc_is_native": net_cfg["usdc_is_native"],
        }

    return {
        "enabled": True,
        "paid_endpoint": "POST /api/audit/paid",
        "price": AUDIT_PRICE_USD,
        "pay_to": SERVER_EVM_ADDRESS,
        "facilitator": FACILITATOR_URL,
        "active_network": ACTIVE_NETWORK,
        "networks": networks_info,
        "description": (
            "Pay per accessibility audit. WCAG 2.1 compliance check with full JSON report. "
            "Accepts USDC on Base Sepolia (ERC-20) or Arc Testnet (native USDC gas token)."
        ),
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
