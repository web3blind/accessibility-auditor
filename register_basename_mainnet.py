"""
Register a Base MAINNET basename.
Mainnet uses UpgradeableRegistrarController (proxy 0xa7d2...)
with extended RegisterRequest including coinTypes, signatureExpiry, signature.
Uses CLIENT wallet (0x830D).
"""
import json
from web3 import Web3
from eth_account import Account

# CONFIG
with open('wallets_x402.json') as f:
    wallets = json.load(f)

PRIVATE_KEY = wallets['client']['private_key']
NAME = "a11y-auditor"
DURATION = 365 * 24 * 3600  # 1 year

RPC_URL = "https://mainnet.base.org"

# UpgradeableRegistrarController Proxy (mainnet)
REGISTRAR_CONTROLLER = "0xa7d2607c6BD39Ae9521e514026CBB078405Ab322"
# Also try old controller as fallback
REGISTRAR_CONTROLLER_OLD = "0x4cCb0BB02FCABA27e82a56646E81d8c5bC4119a5"

L2_RESOLVER = "0xC6d566A56A1aFf6508b41f6c90ff131615583BCD"

# ABI for UpgradeableRegistrarController - extended RegisterRequest
UPGRADEABLE_ABI = [
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
                    {"name": "reverseRecord", "type": "bool"},
                    {"name": "coinTypes", "type": "uint256[]"},
                    {"name": "signatureExpiry", "type": "uint256"},
                    {"name": "signature", "type": "bytes"}
                ]
            }
        ],
        "outputs": []
    },
]

# ABI for old RegistrarController - simple RegisterRequest
OLD_ABI = [
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
]

def try_register(w3, controller_addr, abi, request, owner, value, account):
    controller = w3.eth.contract(
        address=Web3.to_checksum_address(controller_addr),
        abi=abi
    )
    nonce = w3.eth.get_transaction_count(owner)
    gas_price = w3.eth.gas_price

    try:
        gas_est = controller.functions.register(request).estimate_gas({
            'from': owner,
            'value': value
        })
        print(f"  Gas estimate: {gas_est}")
        gas_limit = int(gas_est * 1.2)
    except Exception as e:
        print(f"  Gas estimate failed: {e}")
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
    print(f"  Tx: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    return receipt, tx_hash

def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = Account.from_key(PRIVATE_KEY)
    owner = account.address

    print(f"Owner: {owner}")
    print(f"Chain ID: {w3.eth.chain_id}")
    bal = w3.eth.get_balance(owner)
    print(f"ETH balance: {w3.from_wei(bal, 'ether')} ETH")

    # Check availability and price on old controller (read is same)
    old_ctrl = w3.eth.contract(
        address=Web3.to_checksum_address(REGISTRAR_CONTROLLER_OLD),
        abi=OLD_ABI
    )
    avail = old_ctrl.functions.available(NAME).call()
    print(f"Name '{NAME}' available: {avail}")
    if not avail:
        print("ERROR: Name already taken!")
        return

    price = old_ctrl.functions.rentPrice(NAME, DURATION).call()
    total_price = price[0] + price[1]
    print(f"Price: {w3.from_wei(total_price, 'ether')} ETH")

    if bal < total_price:
        print(f"ERROR: Insufficient ETH. Need {w3.from_wei(total_price,'ether')} ETH")
        return

    value = int(total_price * 1.1)
    print(f"Sending: {w3.from_wei(value, 'ether')} ETH")

    # Try 1: UpgradeableRegistrarController with extended struct (empty signature = no discount)
    print(f"\n--- Attempt 1: UpgradeableRegistrarController ({REGISTRAR_CONTROLLER}) ---")
    request_v2 = (
        NAME,
        owner,
        DURATION,
        Web3.to_checksum_address(L2_RESOLVER),
        [],     # no resolver data
        True,   # set reverse record
        [],     # no coinTypes
        0,      # signatureExpiry = 0 (no signature)
        b""     # empty signature
    )
    try:
        receipt, tx_hash = try_register(w3, REGISTRAR_CONTROLLER, UPGRADEABLE_ABI, request_v2, owner, value, account)
        status = 'SUCCESS' if receipt.status == 1 else 'FAILED'
        print(f"  Status: {status}, gas used: {receipt.gasUsed}")
        print(f"  Tx: https://basescan.org/tx/{tx_hash.hex()}")
        if receipt.status == 1:
            print(f"\n✅ Registered: {NAME}.base.eth")
            print(f"   View: https://www.base.org/name/{NAME}")
            return
    except Exception as e:
        print(f"  Error: {e}")

    # Try 2: Old RegistrarController with simple struct
    print(f"\n--- Attempt 2: Old RegistrarController ({REGISTRAR_CONTROLLER_OLD}) ---")
    request_v1 = (
        NAME,
        owner,
        DURATION,
        Web3.to_checksum_address(L2_RESOLVER),
        [],
        True
    )
    # refresh nonce after failed tx
    try:
        receipt, tx_hash = try_register(w3, REGISTRAR_CONTROLLER_OLD, OLD_ABI, request_v1, owner, value, account)
        status = 'SUCCESS' if receipt.status == 1 else 'FAILED'
        print(f"  Status: {status}, gas used: {receipt.gasUsed}")
        print(f"  Tx: https://basescan.org/tx/{tx_hash.hex()}")
        if receipt.status == 1:
            print(f"\n✅ Registered: {NAME}.base.eth")
            print(f"   View: https://www.base.org/name/{NAME}")
        else:
            print(f"\n❌ Both attempts failed.")
    except Exception as e:
        print(f"  Error: {e}")
        print("\n❌ Registration failed.")

if __name__ == "__main__":
    main()
