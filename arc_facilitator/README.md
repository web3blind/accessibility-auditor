# Arc exact-EVM x402 facilitator

Isolated Node 22+ service. No edits to `bot_final.py`, `api.py` or escrow endpoints. Uses the official `@x402/core` and `@x402/evm` **2.28.0**, with pinned `viem` **2.57.3** and SQLite **better-sqlite3 12.6.2**; `package-lock.json` locks transitive dependencies. No Python package/environment changes.

## Private production integration

See `../ARC_X402_DEPLOYMENT.md` for the verified live deployment. For the self-hosted loopback facilitator, configure `X402_FACILITATOR_URL=http://127.0.0.1:3402` and `X402_PRIVATE_FACILITATOR_TOKEN` in the auditor environment. The token is restricted to this exact endpoint and cannot be combined with Circle credentials. Production payment offers list only `arc_mainnet`; temporarily enabling testnet is for explicit tests only. Preserve escrow configuration separately. Production overrides differ from example defaults; use the verified handoff rather than copying test defaults blindly.

## Source and on-chain contract provenance

This facilitator is an **off-chain server**, not a newly deployed Solidity
contract. Its complete service, gas/nonce ledger, configuration, tests and
payment client are in this directory. `package.json` has `private: true` only
to prevent accidental npm publication; it does not hide the GitHub source.

The fixed-price Arc payment calls `transferWithAuthorization` on the existing
USDC ERC-20 interface at `0x3600000000000000000000000000000000000000`.
There is no additional facilitator contract, Permit2 deployment or escrow
contract in this fixed-price flow. The existing Base multi-page escrow is a
separate product and is not replaced by this service.

Upstream and contract references:

- [Official x402 SDK source](https://github.com/x402-foundation/x402), packages
  `@x402/core` and `@x402/evm`, pinned to `2.28.0` in the lockfile.
- [Arc official contract addresses](https://docs.arc.io/arc/references/contract-addresses).
- [USDC on Arc mainnet explorer](https://explorer.arc.io/address/0x3600000000000000000000000000000000000000).
- [Circle stablecoin contract source](https://github.com/circlefin/stablecoin-evm),
  including [EIP3009.sol](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/v2/EIP3009.sol)
  and [FiatTokenV2_2.sol](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/v2/FiatTokenV2_2.sol).
- [EIP-3009 specification](https://eips.ethereum.org/EIPS/eip-3009).

Circle's source is an upstream reference, **not a claimed byte-for-byte source
verification of Arc's deployed native USDC implementation**. Live checks in
`src/probe.js` verify chain ID, address code, decimals, EIP-712 domain and the
actual EIP-3009 call behavior; successful production receipts provide payment
execution evidence. Secret env files, keys, tokens, SQLite state and dependencies
are excluded from the repository.

## Protocol and restrictions

- `GET /supported`: official x402 v2 `kinds`, `extensions`, `signers` response. Only configured, startup-probed networks are advertised.
- `POST /verify`, `POST /settle`: JSON `{x402Version:2,paymentPayload:{x402Version:2,accepted:{...},payload:{signature,authorization}},paymentRequirements:{...}}`; return SDK-compatible verification/settlement objects, invalid payment responses HTTP 200. Both require `Authorization: Bearer <ARC_FACILITATOR_API_TOKEN>`.
- Loopback only: `127.0.0.1:3402`. Keep it private behind the existing application's custom HTTPFacilitatorClient. Parent must send the Bearer token for verify/settle (do not assume default SDK client auth). No browser CORS/public settlement endpoint.
- Only `exact`, Arc `eip155:5042` and `eip155:5042002`, USDC `0x3600000000000000000000000000000000000000` (6 decimals), EIP712 `USDC`/`2`, configured merchant recipients, amount at most `100000` ($0.10 default).
- Only deployed asset + EOA EIP3009 65-byte signatures. Reject Permit2, contract/7702 payers, wallet deployment, extensions, arbitrary transactions, domain mismatch and authorizations over 300 seconds. Verification and settlement simulation use the SDK, not custom cryptography.
- Dedicated facilitator private key only; not the merchant/payer key. `ARC_SETTLEMENT_ENABLED=false` is the default. Secrets and raw RPC errors are never logged by the service or diagnostic clients; standalone error handlers emit sanitized messages.

## Read-only verification

```bash
cd /home/assistent/ai-projects/accessibility-auditor/arc_facilitator
npm ci --no-audit --no-fund
npm test
ARC_MAINNET_RPC_URL=https://rpc.drpc.mainnet.arc.io npm run probe
ARC_MAINNET_RPC_URL=https://rpc.drpc.mainnet.arc.io node src/live-readonly.js
npm audit --omit=dev
```

`probe` calls eth_chainId, token metadata, DOMAIN_SEPARATOR, authorizationState and an intentionally expired transferWithAuthorization using eth_call, requiring the explicit `FiatTokenV2: authorization is expired` revert. These are read-only, not transactions. `live-readonly.js` runs actual local HTTP endpoints backed by live Arc RPCs and SDK verification, using ephemeral unfunded accounts with settlement disabled.

Live-proven endpoints: mainnet `https://rpc.mainnet.arc.io` returned chain 5042 and valid metadata/domain/EIP3009 revert; mainnet primary later rate-limited (-32005). `https://rpc.drpc.mainnet.arc.io` passed the full local HTTP smoke. Testnet `https://rpc.testnet.arc.io` returned chain 5042002. Do not use guessed `rpc.arc.io` or `rpc.arc.network`. Startup fails closed if chain/USDC/EIP3009 checks fail. Public primary rate limits are a real operational consideration; use the configurable dedicated/provider endpoint rather than weakening startup checks.

## Gas and replay safety

Gas limit 200000; transaction maxFeePerGas 10000000000 wei; worst-case reservation 0.002 native USDC/attempt (native 18 decimals, ERC20 6). Daily cap 0.01 USDC, at most five such reserved attempts/day. Reservations are not refunded, including reverted/ambiguous attempts, so the cap is conservative. Gas estimate, fee estimate, balance, current chain ID and budget must pass before the SDK may submit. Overrides are hard-bounded by config validation; never broaden them without checking the user's budget.

Durable SQLite WAL/FULL journal reserves each `network:asset:payer:authorizationNonce` before settling; duplicates cannot submit twice. A single pending claim blocks all other transactions across processes sharing the DB, serializing the dedicated wallet nonce. Use exactly one service and one DB for this wallet. Never operate the wallet in another process or copy/delete its database. A crash or ambiguous error after RPC submission leaves the claim pending, blocking automatic retries. No automatic replay/timeout resubmission and no cached successful payment reuse.

Recovery is deliberately manual: stop the service, back up DB/WAL/SHM, inspect pending rows' transaction hashes plus wallet pending/latest nonce and USDC authorizationState. Resolve/confirm the original transaction before marking the pending row done. Never delete the authorization row or reset daily reservations. If transaction hash was not durably recorded, reconcile wallet nonce/history first. An invalid/failed authorization remains consumed in the local ledger; client needs a new signature/nonce.

## aaPanel production handoff (not executed here)

1. Copy only this directory, excluding node_modules/state/secrets, to `/www/wwwroot/hexdrive.tech/arc_facilitator`.
2. Discover the actual Node >=22/npm binaries on the server, then `npm ci --omit=dev --no-audit --no-fund` and `npm test` there. Native SQLite may need compiler tooling if no prebuilt binary matches.
3. Parent securely populates `/root/.config/auditor-arc-facilitator.env` (0600), based on `env.example`, with a fresh dedicated wallet and random token. Do not store them in the repository. Set `ARC_DB_PATH=/var/lib/auditor-arc-facilitator/facilitator.sqlite`.
4. Provision unprivileged system user/group `auditor-arc`, ensure read/traverse permissions for the source/dependencies. Review provided `auditor-arc-facilitator.service`, especially real Node binary and paths, then install under `/etc/systemd/system/`. The system manager reads the root-only env file before dropping privileges.
5. Keep settlement disabled. Parent may then run `systemctl daemon-reload; systemctl enable --now auditor-arc-facilitator`, check `systemctl status`, journal, `/health`, and `/supported`. Service's state directory is managed by systemd; source stays read-only. No nginx edits or public port are needed.
6. Parent selectively sets production's facilitator URL to `http://127.0.0.1:3402` and adds Bearer auth, verifies metadata and the existing $0.10 fixed-price route; preserve the other escrow facilitator/endpoint. Production app uses Python x402 2.9.0: same v2 wire protocol, but parent must smoke-test the actual middleware/client after the selective patch.
7. Enable settlements only once wallet provisioning, budget, test validation and payment-route integration are approved. Parent handles funding and live paid test; this work did not deploy, fund or transact.

Manual launch (parent only; env file trusted and shell-compatible):

```bash
cd /www/wwwroot/hexdrive.tech/arc_facilitator
set -a
. /root/.config/auditor-arc-facilitator.env
set +a
node src/server.js
```

## One-shot approved paid client (not run with --pay here)

`node src/paid-client.js` probes the exact production URL and validates a $0.10 Arc offer without signing. Parent may set `ARC_CLIENT_PRIVATE_KEY` securely in environment, `ARC_CLIENT_NETWORK=eip155:5042` and run `node src/paid-client.js --pay` **once** after its funding/budget checks. It uses the official ExactEvmScheme client, requests `https://example.com` with `is_public:false`, disallows redirects and unapproved offers, signs exactly 100000 ERC20 units, and prints settlement/result, never the key or signature. It has no automatic paid retry/funding logic. If a paid request times out, investigate settlement before trying again. The parent's 0.15-USDC inclusive funding/gas budget includes funding-transfer costs outside this client; this client does not calculate or authorize those transfers.
