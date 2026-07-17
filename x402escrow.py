"""Fortytwo x402Escrow helpers for metered site-audit payments.

Production policy: no multi-page audit work before funds are locked. Dry-run is
available only when the operator explicitly enables it for local testing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from site_pricing import build_site_audit_quote, parse_usdc

FORTYTWO_ESCROW_CONTRACTS = {
    # Fortytwo docs list the same deployed proxy address on Base and Monad.
    "base": "0x9562f50f73d8ee22276f13a18d051456d8d137a0",
    "monad": "0x9562f50f73d8ee22276f13a18d051456d8d137a0",
}

CHAIN_IDS = {
    "base": 8453,
    "monad": 143,
}

USDC_DECIMALS = 6

X402_ESCROW_ABI = [
    {
        "type": "function",
        "name": "settle",
        "inputs": [
            {"name": "client", "type": "address"},
            {"name": "maxAmount", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"},
        ],
        "outputs": [{"name": "escrowId", "type": "bytes32"}],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "release",
        "inputs": [
            {"name": "escrowId", "type": "bytes32"},
            {"name": "facilitatorAmount", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "getEscrow",
        "inputs": [{"name": "escrowId", "type": "bytes32"}],
        "outputs": [{
            "name": "",
            "type": "tuple",
            "components": [
                {"name": "client", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "refundAt", "type": "uint256"},
                {"name": "canRefund", "type": "bool"},
                {"name": "timeUntilRefund", "type": "uint256"},
            ],
        }],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "hasRole",
        "inputs": [
            {"name": "role", "type": "bytes32"},
            {"name": "account", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
    {
        "type": "event",
        "name": "Deposited",
        "inputs": [
            {"name": "escrowId", "type": "bytes32", "indexed": True},
            {"name": "client", "type": "address", "indexed": True},
            {"name": "amount", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
    {
        "type": "event",
        "name": "Released",
        "inputs": [
            {"name": "escrowId", "type": "bytes32", "indexed": True},
            {"name": "facilitator", "type": "address", "indexed": True},
            {"name": "toFacilitator", "type": "uint256", "indexed": False},
            {"name": "toClient", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
]


@dataclass(frozen=True)
class X402EscrowConfig:
    enabled: bool
    dry_run: bool
    network: str
    chain_id: int | None
    contract_address: str
    service_url: str
    rpc_url: str | None
    facilitator_private_key: str | None

    @property
    def has_live_credentials(self) -> bool:
        return bool(self.rpc_url and self.facilitator_private_key and self.contract_address)


def load_x402escrow_config() -> X402EscrowConfig:
    network = os.getenv("X402ESCROW_NETWORK", "base").lower()
    contract = os.getenv("X402ESCROW_CONTRACT_ADDRESS", FORTYTWO_ESCROW_CONTRACTS.get(network, ""))
    chain_id = os.getenv("X402ESCROW_CHAIN_ID")
    return X402EscrowConfig(
        enabled=os.getenv("X402ESCROW_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
        dry_run=os.getenv("X402ESCROW_DRY_RUN", "true").lower() not in {"0", "false", "no", "off"},
        network=network,
        chain_id=int(chain_id) if chain_id else CHAIN_IDS.get(network),
        contract_address=contract,
        service_url=os.getenv("AUDIT_SERVICE_URL", "https://hexdrive.tech"),
        rpc_url=os.getenv("X402ESCROW_RPC_URL"),
        facilitator_private_key=os.getenv("X402ESCROW_FACILITATOR_PRIVATE_KEY"),
    )


def usdc_to_units(amount_usdc: str | Decimal) -> int:
    amount = parse_usdc(str(amount_usdc)) if not isinstance(amount_usdc, Decimal) else amount_usdc
    return int(amount * (10 ** USDC_DECIMALS))


def units_to_usdc(units: int) -> str:
    return f"{(Decimal(int(units)) / Decimal(10 ** USDC_DECIMALS)).quantize(Decimal('0.000001'))}"


def _require_web3():
    try:
        from web3 import Web3  # type: ignore
    except ImportError as exc:
        raise RuntimeError("web3 is required for live Fortytwo x402Escrow settlement; install requirements.txt") from exc
    return Web3


def _web3_and_contract(cfg: X402EscrowConfig):
    Web3 = _require_web3()
    if not cfg.rpc_url:
        raise RuntimeError("X402ESCROW_RPC_URL is required for live Fortytwo x402Escrow settlement")
    if not cfg.contract_address:
        raise RuntimeError("X402ESCROW_CONTRACT_ADDRESS is required for live Fortytwo x402Escrow settlement")
    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url))
    if not w3.is_connected():
        raise RuntimeError("Could not connect to X402ESCROW_RPC_URL")
    contract = w3.eth.contract(address=Web3.to_checksum_address(cfg.contract_address), abi=X402_ESCROW_ABI)
    return Web3, w3, contract


def _facilitator_account(w3: Any, cfg: X402EscrowConfig):
    if not cfg.facilitator_private_key:
        raise RuntimeError("X402ESCROW_FACILITATOR_PRIVATE_KEY is required for live settlement")
    return w3.eth.account.from_key(cfg.facilitator_private_key)


def compute_escrow_id(client: str, nonce: str, root_url: str = "") -> str:
    """Compute a deterministic local dry-run escrow id.

    Fortytwo's on-chain id is keccak256(abi.encodePacked(client, nonce)). Live
    settlement returns the actual bytes32 escrow id from the contract/logs.
    """
    digest = hashlib.sha256(f"{client.lower()}|{nonce}|{root_url}".encode("utf-8")).hexdigest()[:24]
    return f"escrow_{digest}"


def x402escrow_dry_run_requests_allowed() -> bool:
    """Whether the paid multi-page endpoint may run without an X-PAYMENT header."""
    return os.getenv("X402ESCROW_ALLOW_DRY_RUN_REQUESTS", "false").lower() in {"1", "true", "yes", "on"}


def x402escrow_live_enabled() -> bool:
    return os.getenv("X402ESCROW_LIVE", "false").lower() in {"1", "true", "yes", "on"}


def parse_x_payment_header(header_value: str | None) -> dict[str, Any] | None:
    """Parse JSON or base64-encoded JSON X-PAYMENT authorization payload."""
    if not header_value:
        return None
    raw = header_value.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return json.loads(base64.b64decode(padded).decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid X-PAYMENT header: {exc}") from exc


def _require_auth_field(auth: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in auth and auth[name] not in (None, ""):
            return auth[name]
    raise ValueError(f"X-PAYMENT is missing required field: {names[0]}")


def normalize_payment_authorization(auth: dict[str, Any]) -> dict[str, Any]:
    """Normalize x402Escrow payment authorization fields for contract calls."""
    return {
        "client": _require_auth_field(auth, "client", "from", "payer"),
        "maxAmount": int(_require_auth_field(auth, "maxAmount", "max_amount", "amount", "value")),
        "validAfter": int(_require_auth_field(auth, "validAfter", "valid_after")),
        "validBefore": int(_require_auth_field(auth, "validBefore", "valid_before")),
        "nonce": _require_auth_field(auth, "nonce"),
        "v": int(_require_auth_field(auth, "v")),
        "r": _require_auth_field(auth, "r"),
        "s": _require_auth_field(auth, "s"),
    }


def build_x402escrow_payment_required(root_url: str, max_budget_usdc: str, max_pages: int, include_summary: bool) -> dict[str, Any]:
    """Return an x402-shaped 402 body for Fortytwo escrow clients."""
    cfg = load_x402escrow_config()
    amount_units = usdc_to_units(max_budget_usdc)
    return {
        "x402Version": 2,
        "error": "Payment required",
        "payment_mode": "x402escrow",
        "resource": {
            "url": f"{cfg.service_url}/api/x402escrow/site-audit",
            "description": "Metered multi-page accessibility audit with Fortytwo x402Escrow",
            "mimeType": "application/json",
        },
        "accepts": [{
            "scheme": "exact",
            "network": cfg.network,
            "chainId": cfg.chain_id,
            "contract": cfg.contract_address,
            "amount": str(amount_units),
            "asset": "USDC",
            "maxAmountUSDC": max_budget_usdc,
            "extra": {
                "escrowType": "fortytwo-x402Escrow",
                "maxPages": max_pages,
                "includeSummary": include_summary,
                "authorizationTarget": cfg.contract_address,
                "refundPolicy": "release actual page cost; unused escrow refunded automatically",
            },
        }],
    }


def check_facilitator_role() -> dict[str, Any]:
    """Check whether configured facilitator address has FACILITATOR_ROLE."""
    cfg = load_x402escrow_config()
    Web3, w3, contract = _web3_and_contract(cfg)
    account = _facilitator_account(w3, cfg)
    role = Web3.keccak(text="FACILITATOR_ROLE")
    has_role = bool(contract.functions.hasRole(role, account.address).call())
    return {
        "network": cfg.network,
        "chain_id": cfg.chain_id,
        "contract_address": cfg.contract_address,
        "facilitator_address": account.address,
        "has_facilitator_role": has_role,
    }


def settle_x402escrow_authorization(authorization: dict[str, Any], root_url: str) -> dict[str, Any]:
    """Lock max authorized USDC in Fortytwo x402Escrow before running work."""
    cfg = load_x402escrow_config()
    auth = normalize_payment_authorization(authorization)
    Web3, w3, contract = _web3_and_contract(cfg)
    account = _facilitator_account(w3, cfg)

    role = Web3.keccak(text="FACILITATOR_ROLE")
    if not contract.functions.hasRole(role, account.address).call():
        raise RuntimeError("Configured facilitator wallet does not have FACILITATOR_ROLE on the x402Escrow contract")

    nonce = auth["nonce"]
    if isinstance(nonce, str) and nonce.startswith("0x"):
        nonce_arg = nonce
    else:
        nonce_arg = "0x" + str(nonce).removeprefix("0x")
    tx = contract.functions.settle(
        Web3.to_checksum_address(auth["client"]),
        auth["maxAmount"],
        auth["validAfter"],
        auth["validBefore"],
        nonce_arg,
        auth["v"],
        auth["r"],
        auth["s"],
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": cfg.chain_id,
    })
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError("x402Escrow settle transaction failed")

    escrow_id = None
    for log in receipt.logs:
        if log["address"].lower() == cfg.contract_address.lower():
            try:
                event = contract.events.Deposited().process_log(log)
                escrow_id = event["args"]["escrowId"].hex()
                break
            except Exception:
                continue
    if escrow_id is None:
        # fallback to contract formula: keccak256(abi.encodePacked(client, nonce))
        nonce_bytes = Web3.to_bytes(hexstr=nonce_arg)
        escrow_id = Web3.keccak(Web3.to_bytes(hexstr=auth["client"]) + nonce_bytes).hex()

    return {
        "mode": "live",
        "status": "settled",
        "network": cfg.network,
        "chain_id": cfg.chain_id,
        "contract_address": cfg.contract_address,
        "facilitator_address": account.address,
        "client": auth["client"],
        "max_amount_units": str(auth["maxAmount"]),
        "max_amount_usdc": units_to_usdc(auth["maxAmount"]),
        "escrow_id": escrow_id,
        "settle_tx": receipt.transactionHash.hex(),
        "release_tx": None,
        "root_url": root_url,
        "created_at": datetime.now().isoformat(),
    }


def release_x402escrow(escrow_id: str, facilitator_amount_usdc: str | Decimal) -> dict[str, Any]:
    """Release actual cost to facilitator and refund the remainder to the client."""
    cfg = load_x402escrow_config()
    Web3, w3, contract = _web3_and_contract(cfg)
    account = _facilitator_account(w3, cfg)
    amount_units = usdc_to_units(facilitator_amount_usdc)
    tx = contract.functions.release(escrow_id, amount_units).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": cfg.chain_id,
    })
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError("x402Escrow release transaction failed")
    return {
        "status": "released",
        "escrow_id": escrow_id,
        "release_tx": receipt.transactionHash.hex(),
        "facilitator_amount_units": str(amount_units),
        "facilitator_amount_usdc": units_to_usdc(amount_units),
        "released_at": datetime.now().isoformat(),
    }


def get_x402escrow_status(escrow_id: str) -> dict[str, Any]:
    cfg = load_x402escrow_config()
    _, _, contract = _web3_and_contract(cfg)
    view = contract.functions.getEscrow(escrow_id).call()
    return {
        "escrow_id": escrow_id,
        "client": view[0],
        "amount_units": str(view[1]),
        "amount_usdc": units_to_usdc(view[1]),
        "refund_at": int(view[2]),
        "can_refund": bool(view[3]),
        "time_until_refund": int(view[4]),
    }


def build_x402escrow_info() -> dict[str, Any]:
    cfg = load_x402escrow_config()
    return {
        "enabled": cfg.enabled,
        "dry_run": cfg.dry_run,
        "live_enabled": x402escrow_live_enabled(),
        "live_ready": cfg.has_live_credentials,
        "escrow_endpoint": "POST /api/x402escrow/site-audit",
        "quote_endpoint": "POST /api/site-audit/quote",
        "report_endpoint_template": f"{cfg.service_url}/site-audits/{{site_audit_id}}",
        "pricing_model": "metered_per_page",
        "price_per_page": "$0.10",
        "summary_fee": "$0.30",
        "max_pages": 100,
        "networks": {
            "base": {"chain_id": CHAIN_IDS["base"], "contract_address": FORTYTWO_ESCROW_CONTRACTS["base"]},
            "monad": {"chain_id": CHAIN_IDS["monad"], "contract_address": FORTYTWO_ESCROW_CONTRACTS["monad"]},
        },
        "active_network": cfg.network,
        "chain_id": cfg.chain_id,
        "contract_address": cfg.contract_address,
        "client_controls": [
            "max_pages",
            "max_budget_usdc",
            "allowed_domains",
            "same_domain_only",
            "human_approval_above_limit_usd",
        ],
        "operator_env_required_for_live": [
            "X402ESCROW_LIVE=true",
            "X402ESCROW_RPC_URL",
            "X402ESCROW_FACILITATOR_PRIVATE_KEY",
            "X402ESCROW_NETWORK or X402ESCROW_CHAIN_ID",
            "X402ESCROW_CONTRACT_ADDRESS set to your deployed Fortytwo x402Escrow proxy",
        ],
        "facilitator_role_note": (
            "The configured facilitator address must have FACILITATOR_ROLE on the configured x402Escrow contract. "
            "Fortytwo's public Discord guidance says external facilitators are not supported on the official contract, "
            "so production deployments should use their open-source x402Escrow implementation with your own proxy/admin/facilitator."
        ),
        "description": (
            "Fortytwo x402Escrow-compatible metered multi-page accessibility audit. "
            "Clients lock a maximum USDC budget; the service charges only pages actually audited and reports the refund."
        ),
    }


def build_dry_run_escrow(root_url: str, max_budget_usdc: str, client: str = "dry-run-client") -> dict[str, Any]:
    nonce = hashlib.sha256(f"{root_url}|{max_budget_usdc}".encode("utf-8")).hexdigest()[:16]
    cfg = load_x402escrow_config()
    return {
        "mode": "dry_run",
        "status": "not_settled",
        "network": cfg.network,
        "chain_id": cfg.chain_id,
        "contract_address": cfg.contract_address,
        "escrow_id": compute_escrow_id(client=client, nonce=nonce, root_url=root_url),
        "settle_tx": None,
        "release_tx": None,
        "created_at": datetime.now().isoformat(),
        "note": "Dry-run escrow metadata only; no funds were locked or released.",
    }
