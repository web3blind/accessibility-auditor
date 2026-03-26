from eth_account import Account
import json

with open('wallets_x402.json') as f:
    wallets = json.load(f)

print('Wallets in file:')
for k, v in wallets.items():
    print(f'  {k}:')
    if isinstance(v, dict):
        addr = v.get('address', 'N/A')
        pk = v.get('private_key', 'N/A')
        acc = Account.from_key(pk)
        print(f'    stored address: {addr}')
        print(f'    derived address: {acc.address}')
        print(f'    match: {addr.lower() == acc.address.lower()}')
