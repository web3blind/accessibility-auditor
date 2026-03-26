#!/usr/bin/env python3
"""
Register Accessibility Auditor as an ERC-8004 AI Agent on Arc Testnet.

This mints an AgentIdentity NFT (AGENT token) on the IdentityRegistry contract.
The agent gets a unique on-chain identity with metadata stored on-chain.

Usage:
    python3 register_erc8004.py

ERC-8004 contracts on Arc Testnet:
- IdentityRegistry:   0x8004A818BFB912233c491871b3d84c89A494BD9e
- ReputationRegistry: 0x8004B663056A597Dffe9eCcC1965A193B7388713
- ValidationRegistry: 0x8004Cb1BF31DAf7788923b405b754f57acEB4272
"""

import json
import os
import sys
from web3 import Web3

# ── Configuration ──────────────────────────────────────────

ARC_RPC = os.getenv("ARC_TESTNET_RPC", "https://rpc.testnet.arc.network")
CHAIN_ID = int(os.getenv("ARC_TESTNET_CHAIN_ID", "5042002"))

# Load private key from .env or wallets_x402.json
PRIVATE_KEY = os.getenv("EVM_PRIVATE_KEY", "")
if not PRIVATE_KEY:
    wallets_path = os.path.join(os.path.dirname(__file__), "wallets_x402.json")
    if os.path.exists(wallets_path):
        with open(wallets_path) as f:
            wallets = json.load(f)
        PRIVATE_KEY = wallets["server"]["private_key"]

if not PRIVATE_KEY:
    print("ERROR: No private key found. Set EVM_PRIVATE_KEY or create wallets_x402.json")
    sys.exit(1)

# Contracts
IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"

# Agent metadata
AGENT_URI = "https://hexdrive.tech/api/x402/info"
AGENT_METADATA = [
    ("name", "Accessibility Auditor"),
    ("description", "WCAG 2.1 accessibility audit service with x402 payments. Built by @Denis_skripnik, blind developer."),
    ("service_url", "https://hexdrive.tech"),
    ("api_endpoint", "https://hexdrive.tech/api/audit/paid"),
    ("payment_protocol", "x402"),
    ("standards", "WCAG 2.1 AA"),
    ("telegram_bot", "@accessibilityAuditAgentBot"),
    ("github", "https://github.com/web3blind/accessibility-auditor"),
    ("developer", "Denis Skripnik (@Denis_skripnik)"),
]

# ── ABI ────────────────────────────────────────────────────

# Load full ABI from file if available, otherwise use minimal ABI
ABI_PATH = "/tmp/identity_registry_abi.json"
if os.path.exists(ABI_PATH):
    with open(ABI_PATH) as f:
        IDENTITY_ABI = json.load(f)
else:
    # Minimal ABI for registration
    IDENTITY_ABI = [
        {
            "inputs": [{"name": "agentURI", "type": "string"}],
            "name": "register",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"name": "agentId", "type": "uint256"}],
            "name": "getAgentWallet",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"name": "agentId", "type": "uint256"}, {"name": "metadataKey", "type": "string"}],
            "name": "getMetadata",
            "outputs": [{"name": "", "type": "bytes"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"name": "agentId", "type": "uint256"}, {"name": "metadataKey", "type": "string"}, {"name": "metadataValue", "type": "bytes"}],
            "name": "setMetadata",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"name": "agentId", "type": "uint256"}, {"name": "newURI", "type": "string"}],
            "name": "setAgentURI",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "name": "ownerOf",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "name": "tokenURI",
            "outputs": [{"name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": False, "name": "agentId", "type": "uint256"},
                {"indexed": False, "name": "agentURI", "type": "string"},
                {"indexed": False, "name": "owner", "type": "address"}
            ],
            "name": "Registered",
            "type": "event"
        },
    ]


def main():
    # Connect
    w3 = Web3(Web3.HTTPProvider(ARC_RPC))
    if not w3.is_connected():
        print("ERROR: Cannot connect to Arc testnet")
        sys.exit(1)

    print(f"Connected to Arc Testnet (Chain ID: {w3.eth.chain_id})")

    # Setup account
    account = w3.eth.account.from_key(PRIVATE_KEY)
    wallet = account.address
    print(f"Wallet: {wallet}")

    balance = w3.eth.get_balance(wallet)
    balance_usdc = Web3.from_wei(balance, "ether")
    print(f"Balance: {balance_usdc} USDC (native)")

    if balance == 0:
        print("ERROR: No USDC for gas. Use https://faucet.circle.com/ to get testnet USDC.")
        sys.exit(1)

    # Setup contract
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(IDENTITY_REGISTRY),
        abi=IDENTITY_ABI
    )

    # Check if we already have an agent registered
    agent_count = contract.functions.balanceOf(wallet).call()
    print(f"\nExisting agent NFTs owned: {agent_count}")

    if agent_count > 0:
        print("You already have an agent identity! Checking details...")
        # We'd need to enumerate tokens - skip for now
        # The register function will still work (can have multiple agents)
        response = input("Register another agent? (y/N): ").strip().lower()
        if response != "y":
            print("Aborted.")
            return

    # Register agent with URI
    print(f"\nRegistering agent with URI: {AGENT_URI}")
    print("Building transaction...")

    # Use the register(string agentURI) overload
    # Function selector: 0x8ea42286
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price

    tx = contract.functions.register(AGENT_URI).build_transaction({
        "chainId": CHAIN_ID,
        "from": wallet,
        "nonce": nonce,
        "gasPrice": gas_price,
    })

    # Estimate gas
    try:
        gas_estimate = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas_estimate * 1.2)  # 20% buffer
        print(f"Estimated gas: {gas_estimate} (using {tx['gas']})")
    except Exception as e:
        print(f"Gas estimation failed: {e}")
        tx["gas"] = 300000  # Fallback
        print(f"Using fallback gas: {tx['gas']}")

    gas_cost_usdc = Web3.from_wei(tx["gas"] * gas_price, "ether")
    print(f"Gas cost: ~{gas_cost_usdc} USDC")

    # Sign and send
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    print("Sending transaction...")

    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"TX hash: {tx_hash.hex()}")
    print(f"Explorer: https://testnet.arcscan.app/tx/{tx_hash.hex()}")

    # Wait for receipt
    print("Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.status == 1:
        print(f"\nSUCCESS! Agent registered on Arc Testnet!")
        print(f"Block: {receipt.blockNumber}")
        print(f"Gas used: {receipt.gasUsed}")

        # Parse Registered event to get agentId
        try:
            registered_events = contract.events.Registered().process_receipt(receipt)
            if registered_events:
                agent_id = registered_events[0]["args"]["agentId"]
                print(f"Agent ID (token): {agent_id}")
                print(f"Agent URI: {registered_events[0]['args']['agentURI']}")
                print(f"Owner: {registered_events[0]['args']['owner']}")

                # Now set metadata
                print(f"\nSetting {len(AGENT_METADATA)} metadata entries...")
                for key, value in AGENT_METADATA:
                    value_bytes = value.encode("utf-8")
                    nonce = w3.eth.get_transaction_count(wallet)
                    meta_tx = contract.functions.setMetadata(
                        agent_id, key, value_bytes
                    ).build_transaction({
                        "chainId": CHAIN_ID,
                        "from": wallet,
                        "nonce": nonce,
                        "gasPrice": w3.eth.gas_price,
                        "gas": 200000,
                    })
                    signed_meta = w3.eth.account.sign_transaction(meta_tx, PRIVATE_KEY)
                    meta_hash = w3.eth.send_raw_transaction(signed_meta.raw_transaction)
                    meta_receipt = w3.eth.wait_for_transaction_receipt(meta_hash, timeout=30)
                    status = "OK" if meta_receipt.status == 1 else "FAIL"
                    print(f"  {status}: {key} = {value[:50]}...")

                # Save agent ID
                reg_info = {
                    "agent_id": agent_id,
                    "tx_hash": tx_hash.hex(),
                    "wallet": wallet,
                    "network": "arc_testnet",
                    "chain_id": CHAIN_ID,
                    "identity_registry": IDENTITY_REGISTRY,
                    "agent_uri": AGENT_URI,
                    "block_number": receipt.blockNumber,
                }
                reg_path = os.path.join(os.path.dirname(__file__), "erc8004_registration.json")
                with open(reg_path, "w") as f:
                    json.dump(reg_info, f, indent=2)
                print(f"\nRegistration info saved to: {reg_path}")

        except Exception as e:
            print(f"Event parsing error (agent still registered): {e}")
    else:
        print(f"\nFAILED! Transaction reverted.")
        print(f"Receipt: {receipt}")


if __name__ == "__main__":
    main()
