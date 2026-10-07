# Arc x402 production handoff

Verified deployment: 2026-10-07. This supersedes historical x402 network notes in STATE.md.

## Live product

- Fixed-price endpoint: `POST https://hexdrive.tech/api/audit/paid`.
- Price: 0.10 USDC. Production offers only Arc mainnet (`eip155:5042`).
- Discovery: `GET https://hexdrive.tech/api/x402/info`.
- Without a payment: HTTP 402 and a v2 `payment-required` header.
- Existing multi-page Base escrow is unchanged; its configuration remains separate.
- GenLayer discovery, homepage and an existing stored report were checked after activation.

## Runtime ownership

- Auditor: `accessibility-auditor.service`, app `/www/wwwroot/hexdrive.tech` (historical `/root/accessibility-auditor-service` symlink), Python venv, upstream port 3005.
- Facilitator: `auditor-arc-facilitator.service`, source `/opt/accessibility-auditor-arc`, unprivileged `auditor-arc`, private listener `127.0.0.1:3402`.
- Dedicated Node 22.22.1 binary copied into the facilitator directory because aaPanel's Node directories deny traversal to the unprivileged user. Do not relax global aaPanel permissions.
- Root-only facilitator env: `/root/.config/auditor-arc-facilitator.env`. Dedicated wallet and random API token stay there, never in Git.
- Auditor `.env` references `X402_PRIVATE_FACILITATOR_TOKEN` and `X402_FACILITATOR_URL=http://127.0.0.1:3402`; the helper rejects use of this token with any other URL or mixed Circle credentials.
- SQLite nonce ledger: `/var/lib/auditor-arc-facilitator/facilitator.sqlite`. Preserve DB/WAL/SHM for recovery; never reset to retry an ambiguous payment.
- Effective gas bounds: gas limit 150000, maxFeePerGas 40000000000 wei, conservative daily reservations 0.020 native USDC. Test reservations were preserved. Wallet funding is finite; replenishment is not automated.
- Exact prechange backups: `/root/auditor-arc-backups/20261007T064011Z`.

## Execution evidence

- Local Python targeted tests: 39 passed. Facilitator Node tests: 11 passed locally and on the server. Dependency audit: zero vulnerabilities at verification.
- Unauthenticated facilitator verify/settle: HTTP 401.
- Testnet: 200 response, successful settlement, report https://hexdrive.tech/audits/dece9565 . Transaction `0x71321c5d578a683027cdf85aed6d89b96dd47f836801314c6c0ef1baf696d5bb`.
- Mainnet: 200 response, successful settlement, report https://hexdrive.tech/audits/872548f6 . Transaction `0x558e568b63d2ca8acb4c9df6057ed59c0b126bb7ffc4e5fdd9f7172728170b9a`.
- Mainnet receipt status 1; USDC Transfer event payer-to-merchant amount 100000 units. Gas used 91677.
- Actual mainnet fees, including two funding transfers: 0.002673540134727447 USDC. The 0.10 USDC test payment returned to the merchant. Remaining dedicated mainnet facilitator balance at verification: 0.023166459907314553 USDC.
- Both reports return 200 with rendered audit content. Both service units are active/running. Testnet payment offers were removed after testing.

## External constraints

Circle Console signin/signup did not render the login form; its auth redirect returned to signin, and a separate HTTP fetch returned 403 Lockout. No Google login or Circle API key was obtained. The approved self-hosted fallback is the deployed implementation. No grant application was submitted and no repository push was performed during this change.
