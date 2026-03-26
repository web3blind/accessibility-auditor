from web3 import Web3

w3 = Web3(Web3.HTTPProvider('https://mainnet.base.org'))

# Check error selector 0x59907813 - could be NameNotAvailable or other
# Let's decode the revert manually
# First check both controller contracts

for label, addr in [
    ("Old RegistrarController", "0x4cCb0BB02FCABA27e82a56646E81d8c5bC4119a5"),
    ("UpgradeableRegistrarController Proxy", "0xa7d2607c6BD39Ae9521e514026CBB078405Ab322"),
]:
    code = w3.eth.get_code(addr)
    print(f"{label}: {len(code)} bytes of bytecode")

# Try available() on both
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
]

for label, addr in [
    ("Old", "0x4cCb0BB02FCABA27e82a56646E81d8c5bC4119a5"),
    ("Upgradeable", "0xa7d2607c6BD39Ae9521e514026CBB078405Ab322"),
]:
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=CONTROLLER_ABI)
        avail = c.functions.available("a11y-auditor").call()
        price = c.functions.rentPrice("a11y-auditor", 365*24*3600).call()
        total = price[0] + price[1]
        print(f"{label} ({addr}): available={avail}, price={w3.from_wei(total,'ether')} ETH")
    except Exception as e:
        print(f"{label} ({addr}): ERROR - {e}")

# Check what error 0x59907813 is from RegistrarController errors
# Known errors from source:
# NameNotAvailable -> keccak256("NameNotAvailable(string)")[:4]
# DurationTooShort -> keccak256("DurationTooShort(uint256)")[:4]
# InsufficientValue -> keccak256("InsufficientValue()")[:4]
from eth_abi.packed import encode_packed
from web3 import Web3 as W3

errors = [
    "NameNotAvailable(string)",
    "DurationTooShort(uint256)",
    "InsufficientValue()",
    "AlreadyRegisteredWithDiscount(address)",
    "ResolverRequiredWhenDataSupplied()",
    "InactiveDiscount(bytes32)",
    "InvalidDiscount(bytes32,bytes)",
    "TransferFailed()",
]

print("\nError selectors:")
for e in errors:
    sel = W3.keccak(text=e)[:4].hex()
    marker = " <-- MATCH" if sel == "59907813" else ""
    print(f"  {sel}  {e}{marker}")
