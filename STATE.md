# Accessibility Auditor — Project State
Last updated: 2026-03-26

## Project
- Name: Accessibility Auditor
- Repo: https://github.com/web3blind/accessibility-auditor
- Live: https://hexdrive.tech
- Telegram bot: @accessibilityAuditAgentBot
- Built by: Denis Skripnik (@denis_skripnik), blind developer

## Infrastructure
- Server: 151.245.136.199 (Nexus)
- Stack: FastAPI (Python) + Playwright + nginx
- nginx → localhost:3000
- SSL: Let's Encrypt, valid until 2026-06-14
- DNS: Cloudflare, A @ → 151.245.136.199 proxied

## Wallets (Base + Arc)
- Client wallet: 0x830D957413EEbC8244C1346e1B86d8408F42F92f (has ETH on Base, ~10 USDC on Arc)
- Server wallet: 0x69a01903E635587C3e28DaAfF5DB82B369447e76 (10 USDC on Arc)
- Keys: .env (EVM_PRIVATE_KEY) + wallets_x402.json (NOT in git)

## Arc Network Integration (Circle L1)
- Network: Arc Testnet (Chain ID: 5042002)
- RPC: https://rpc.testnet.arc.network
- Explorer: https://testnet.arcscan.app
- Gas token: USDC (native!) — not ERC-20, USDC IS the gas
- Faucet: https://faucet.circle.com/

### ERC-8004 AI Agent Identity
- Agent ID: #963 (AGENT NFT)
- Registry: 0x8004A818BFB912233c491871b3d84c89A494BD9e (IdentityRegistryUpgradeable)
- Registration TX: https://testnet.arcscan.app/tx/001f879dcfceaa3fcf8c5ffb9926c78cec4325ae67ab07c45082f1985178408d
- Agent URI: https://hexdrive.tech/api/x402/info
- On-chain metadata: name, description, service_url, api_endpoint, payment_protocol, standards, telegram_bot, github, developer
- Registration info: erc8004_registration.json (NOT in git)

### ERC-8004 Contracts (Arc Testnet)
- IdentityRegistry:   0x8004A818BFB912233c491871b3d84c89A494BD9e
- ReputationRegistry: 0x8004B663056A597Dffe9eCcC1965A193B7388713
- ValidationRegistry: 0x8004Cb1BF31DAf7788923b405b754f57acEB4272

## ENS / Basenames
- a11y-auditor.basetest.eth — Base Sepolia testnet ✅
  tx: https://sepolia.basescan.org/tx/c426a8e5c3e24153509bd79f60261bec4e0d472fde4311a91eeb7fb4904d5092
- a11y-auditor.base.eth — Base Mainnet ✅
  tx: https://basescan.org/tx/54f08793dba7a732510685c030c99bb1133160a57c5bf1722390cb0f9cc5103b
  View: https://www.base.org/name/a11y-auditor

## x402 Integration
- Paid endpoint: POST https://hexdrive.tech/api/audit/paid
- Price: 0.10 USDC on Base Sepolia (eip155:84532)
- Facilitator: https://x402.org/facilitator
- Discovery: GET https://hexdrive.tech/api/x402/info
- Free endpoint: POST https://hexdrive.tech/api/audit (Referer: hexdrive.tech required)

## OpenServ Integration
- Platform: https://platform.openserv.ai
- Agent submitted for review ✅
- SDK code: /root/.hermes/agents/accessibility-auditor/openserv/
- Running via pm2: `openserv-agent` (auto-restart enabled)
- API Key: 401ce02984e941d9b62616d1f5719dc8
- Auth Token: 08cb61ce-ca94-4523-bd5a-ac51b5c23409
- Capabilities: audit_website_free, get_payment_info, check_accessibility_score
- Logs: /root/.pm2/logs/openserv-agent-out.log

## Synthesis Hackathon
- Hackathon: https://synthesis.md
- Submit platform: Devfolio (synthesis.devfolio.co)
- Deadline: ~73 hours from 2026-03-20 (ends ~2026-03-23)

### Registration status ✅
- participantId: 4a1cf57038e04670bfb8fa2f1e9f71b2
- teamId: fbfad9fcf7cb44df8fe53d7e0d093ddd
- Agent name: Accessibility Auditor Agent
- agentHarness: claude-code
- onchain tx: https://basescan.org/tx/0x4c3b840f5fd2a6d494f0b44fc988fc79978b89d1bba1d49e30c5b875cf9093ec
- email: deniska299@gmail.com
- verification: tweet https://x.com/Denis_skripnik/status/2034883727814254747

### ⚠️ ПРОБЛЕМА: apiKey потерян
- apiKey формата sk-synth-... был возвращён один раз при /register/complete
- Терминал скрыл его как секрет, не сохранили
- Написали в Telegram группу хакатона: https://t.me/+3F5IzO_UmDBkMTM1
- Нужно получить переизданный ключ от организаторов
- БЕЗ НЕГО нельзя сабмитить проект через API

### Треки для участия
1. Base — Agent Services on Base — $5,000 (3 победителя по ~$1,666)
   Требования: x402 ✅, discoverable on Base ✅, agent coordination ✅
2. OpenServ — Ship Something Real — $4,500
   Требования: агент на OpenServ платформе ✅ (на review)
3. OpenServ — Best Build Story — $500
   Требования: написать X тред / статью об опыте (ЕЩЁ НЕ СДЕЛАНО)
4. Open Track — $28,300
   Требования: просто сабмит (ЕЩЁ НЕ СДЕЛАНО — нужен apiKey)

### Сабмит проекта (TODO)
Когда получим apiKey:
```bash
curl -X POST https://synthesis.devfolio.co/projects \
  -H "Authorization: Bearer sk-synth-..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Accessibility Auditor",
    "description": "...",
    "url": "https://hexdrive.tech",
    "repoUrl": "https://github.com/web3blind/accessibility-auditor",
    "tracks": ["base", "openserv", "open"]
  }'
```
(точную схему уточнить через curl -s https://synthesis.md/skill.md)

## Coinbase x402 Ecosystem PR
- PR: https://github.com/coinbase/x402/pull/1713
- Branch: add-accessibility-auditor в web3blind/x402
- Статус: открыт, ожидает ревью

## Secrets (NOT in git)
- wallets_x402.json — кошельки
- .env — TELEGRAM_BOT_TOKEN, EVM_PRIVATE_KEY, EVM_SERVER_ADDRESS
- erc8004_registration.json — агент ID и TX hash
- synthesis_registration.json — пустой (pendingId уже использован)
- openserv/.env — OPENSERV_API_KEY, OPENSERV_AUTH_TOKEN

## Running processes
- Python FastAPI: systemd service `accessibility-auditor`
- OpenServ agent: pm2 `openserv-agent`
- nginx: системный сервис
