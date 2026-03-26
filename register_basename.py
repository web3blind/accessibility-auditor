"""
Register a Base Sepolia basename.
Base uses RegistrarController with RegisterRequest struct (no commit/reveal).
Uses CLIENT wallet (0x830D) which has 0.03 ETH.
"""
import json
import os
from web3 import Web3
from eth_account import Account

# CONFIG
with open('wallets_x402.json') as f:
    wallets = json.load(f)

PRIVATE_KEY = wallets['client']['private_key']
NAME = "a11y-auditor"
DURATION = 365 * 24 * 3600  # 1 year

RPC_URL = "https://sepolia.base.org"
REGISTRAR_CONTROLLER = "0x49ae3cc2e3aa768b1e5654f5d3c6002144a59581"
L2_RESOLVER = "0x6533C94869D28fAA8dF77cc63f9e2b2D6Cf77eBA"

# ABI based on actual RegistrarController.sol source
CONTROLLER_ABI = [
    {
        "name": "available",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "name", "type": "string"}],
        "outputs": [{"name": "", "type": "bool"}]
    },
    {
        "name": "rentPrice",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "duration", "type": "uint256"}
        ],
        "outputs": [
            {"components": [
                {"name": "base", "type": "uint256"},
                {"name": "premium", "type": "uint256"}
            ], "name": "price", "type": "tuple"}
        ]
    },
    {
        "name": "register",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "request",
                "type": "tuple",
                "components": [
                    {"name": "name", "type": "string"},
                    {"name": "owner", "type": "address"},
                    {"name": "duration", "type": "uint256"},
                    {"name": "resolver", "type": "address"},
                    {"name": "data", "type": "bytes[]"},
                    {"name": "reverseRecord", "type": "bool"}
                ]
            }
        ],
        "outputs": []
    },
    {
        "name": "valid",
        "type": "function",
        "stateMutability": "pure",
        "inputs": [{"name": "name", "type": "string"}],
        "outputs": [{"name": "", "type": "bool"}]
    }
]

def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = Account.from_key(PRIVATE_KEY)
    owner = account.address

    print(f"Owner: {owner}")
    print(f"Chain ID: {w3.eth.chain_id}")
    bal = w3.eth.get_balance(owner)
    print(f"ETH balance: {w3.from_wei(bal, 'ether')} ETH")

    controller = w3.eth.contract(
        address=Web3.to_checksum_address(REGISTRAR_CONTROLLER),
        abi=CONTROLLER_ABI
    )

    # Check validity and availability
    try:
        valid = controller.functions.valid(NAME).call()
        print(f"Name valid: {valid}")
    except Exception as e:
        print(f"valid() error: {e}")

    avail = controller.functions.available(NAME).call()
    print(f"Name '{NAME}' available: {avail}")
    if not avail:
        print("ERROR: Name already taken!")
        return

    # Get price
    price = controller.functions.rentPrice(NAME, DURATION).call()
    total_price = price[0] + price[1]
    print(f"Price: {w3.from_wei(total_price, 'ether')} ETH ({total_price} wei)")

    if bal < total_price:
        print(f"ERROR: Insufficient balance. Need {w3.from_wei(total_price, 'ether')} ETH")
        return

    # Build RegisterRequest
    request = (
        NAME,
        owner,
        DURATION,
        Web3.to_checksum_address(L2_RESOLVER),
        [],     # no extra resolver data
        True    # set reverse record
    )

    # Add 10% buffer to value
    value = int(total_price * 1.1)
    print(f"\nSending tx with {w3.from_wei(value, 'ether')} ETH...")

    nonce = w3.eth.get_transaction_count(owner)
    gas_price = w3.eth.gas_price
    print(f"Gas price: {w3.from_wei(gas_price, 'gwei')} gwei")

    # Estimate gas first
    try:
        gas_est = controller.functions.register(request).estimate_gas({
            'from': owner,
            'value': value
        })
        print(f"Gas estimate: {gas_est}")
        gas_limit = int(gas_est * 1.2)
    except Exception as e:
        print(f"Gas estimate failed: {e}")
        gas_limit = 400000

    tx = controller.functions.register(request).build_transaction({
        'from': owner,
        'nonce': nonce,
        'gas': gas_limit,
        'gasPrice': gas_price,
        'value': value,
        'chainId': w3.eth.chain_id,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Tx hash: {tx_hash.hex()}")
    print("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    status = 'SUCCESS' if receipt.status == 1 else 'FAILED'
    print(f"Status: {status}")
    print(f"Gas used: {receipt.gasUsed}")
    print(f"Tx: https://sepolia.basescan.org/tx/{tx_hash.hex()}")

    if receipt.status == 1:
        print(f"\n✅ Registered: {NAME}.basetest.eth")
        print(f"Owner: {owner}")
    else:
        print(f"\n❌ Registration failed.")

if __name__ == "__main__":
    main()
