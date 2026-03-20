"""
AgentKit Action Provider for Accessibility Auditor.

Allows any AgentKit-powered AI agent to run a paid WCAG 2.1 accessibility
audit via x402 (0.10 USDC on Base Mainnet). Free audits are only available
via the website UI at https://hexdrive.tech.

Usage:
    from agentkit_action_provider import accessibility_audit_action_provider
    from coinbase_agentkit import AgentKit, AgentKitConfig

    agent_kit = AgentKit(AgentKitConfig(
        wallet_provider=wallet_provider,
        action_providers=[
            accessibility_audit_action_provider(),
        ]
    ))
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

SERVER_URL = os.getenv("AUDIT_SERVER_URL", "https://hexdrive.tech")


# ── Schemas ────────────────────────────────────────────────────────────────────

class PaidAuditUrlSchema(BaseModel):
    url: str = Field(
        description="The URL of the website to audit for WCAG 2.1 accessibility compliance."
    )
    private_key: str = Field(
        description="EVM private key of the wallet to pay with (0.10 USDC on Base Mainnet)."
    )


# ── Paid audit action ──────────────────────────────────────────────────────────

def run_paid_accessibility_audit(args: dict[str, Any]) -> str:
    """
    Run a paid WCAG 2.1 accessibility audit via x402 (0.10 USDC on Base Mainnet).
    Automatically handles payment: signs EIP-3009 authorization and submits to facilitator.
    """
    import asyncio
    from eth_account import Account
    from x402.client import x402Client
    from x402.http.clients.httpx import x402HttpxClient
    from x402.mechanisms.evm.exact.client import ExactEvmScheme
    from x402.mechanisms.evm.signers import EthAccountSigner

    url = args["url"]
    private_key = args["private_key"]

    async def _pay_and_audit():
        account = Account.from_key(private_key)
        signer = EthAccountSigner(account)
        scheme = ExactEvmScheme(signer=signer)
        client = x402Client()
        client.register("eip155:84532", scheme)  # Base Sepolia

        async with x402HttpxClient(client) as http:
            response = await http.post(
                f"{SERVER_URL}/api/audit/paid",
                json={"url": url},
                timeout=90,
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "paid": True,
                    "payer": account.address,
                    "url": data.get("url", url),
                    "score": data.get("score"),
                    "grade": data.get("grade"),
                    "total_issues": data.get("total_issues"),
                    "critical": data.get("critical"),
                    "warnings": data.get("warnings"),
                    "issues_by_category": data.get("issues_by_category", {}),
                    "report_url": data.get("report_url"),
                    "audit_id": data.get("audit_id"),
                    "payment_network": data.get("payment_network"),
                }
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}

    try:
        result = asyncio.run(_pay_and_audit())
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ── AgentKit Action Provider ───────────────────────────────────────────────────

def accessibility_audit_action_provider():
    """
    Returns an AgentKit ActionProvider for accessibility auditing.

    Provides two actions:
    - accessibility_free_audit: Free WCAG 2.1 audit (no payment)
    - accessibility_paid_audit: Paid audit via x402 (0.10 USDC on Base Mainnet)

    Example:
        agent_kit = AgentKit(AgentKitConfig(
            wallet_provider=wallet_provider,
            action_providers=[accessibility_audit_action_provider()]
        ))
    """
    try:
        from coinbase_agentkit import ActionProvider, WalletProvider, create_action
        from coinbase_agentkit.network import Network

        class AccessibilityAuditActionProvider(ActionProvider):
            def __init__(self):
                super().__init__("accessibility-audit", [])

            @create_action(
                name="accessibility_paid_audit",
                description=(
                    "Run a PAID WCAG 2.1 accessibility audit on a website via x402 protocol. "
                    "Costs 0.10 USDC on Base Mainnet. Payment is automatic via EIP-3009. "
                    "Returns full audit report with score, grade, and issue details. "
                    "Requires a wallet private key with at least 0.10 USDC on Base Mainnet."
                ),
                schema=PaidAuditUrlSchema,
            )
            def paid_audit(self, args: dict[str, Any]) -> str:
                return run_paid_accessibility_audit(args)

            def supports_network(self, network: Network) -> bool:
                return True

        return AccessibilityAuditActionProvider()

    except ImportError:
        # coinbase-agentkit not installed — return a simple dict describing the actions
        # so the module can still be imported and used standalone
        return {
            "name": "accessibility-audit",
            "actions": {
                "accessibility_paid_audit": run_paid_accessibility_audit,
            },
            "description": "WCAG 2.1 accessibility audit service (paid, via x402). Install coinbase-agentkit for full AgentKit integration.",
        }


# ── Standalone usage (without AgentKit) ───────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python agentkit_action_provider.py <url> [--paid <private_key>]")
        print("Example (free):  python agentkit_action_provider.py https://example.com")
        print("Example (paid):  python agentkit_action_provider.py https://example.com --paid 0xabc...")
        sys.exit(1)

    target_url = sys.argv[1]

    if "--paid" not in sys.argv:
        print("Error: private key required. Use --paid <private_key>")
        print("Example: python agentkit_action_provider.py https://example.com --paid 0xabc...")
        sys.exit(1)

    idx = sys.argv.index("--paid")
    pk = sys.argv[idx + 1]
    print(f"Running PAID audit of {target_url} (0.10 USDC on Base Mainnet)...")
    result = run_paid_accessibility_audit({"url": target_url, "private_key": pk})

    print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
