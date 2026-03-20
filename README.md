# Accessibility Auditor

WCAG 2.1 accessibility audit service for websites — with pay-per-use via [x402](https://x402.org) protocol.

Built by a blind developer for blind and low-vision users.

🤖 **[Telegram Bot: @accessibilityAuditAgentBot](https://t.me/accessibilityAuditAgentBot)** | 🌐 **[Web: hexdrive.tech](https://hexdrive.tech)**

## What It Does

Audits any website for WCAG 2.1 accessibility compliance. Returns a score (0–100), letter grade (A–F), and detailed issue breakdown across 12 categories:

- Semantic HTML structure
- Image alt text
- Link text quality
- Heading hierarchy
- Form accessibility (labels, IDs)
- Keyboard navigation
- ARIA attributes
- Media captions (video/iframe)
- Contrast ratio
- Language declaration
- Page structure and landmarks
- Responsive design (viewport)

## x402 Payment Integration

AI agents and developers can pay per audit via the [x402 protocol](https://x402.org) — no API keys, no subscriptions.

```
POST https://hexdrive.tech/api/audit/paid
Payment: 0.10 USDC on Base Sepolia (testnet)
Network: eip155:84532
Facilitator: https://x402.org/facilitator
```

Discovery endpoint:
```
GET https://hexdrive.tech/api/x402/info
```

Free audits are available via the web interface only (not via API).

### AgentKit Integration

Any [AgentKit](https://github.com/coinbase/agentkit)-powered agent can call this service directly:

```python
from agentkit_action_provider import accessibility_audit_action_provider
from coinbase_agentkit import AgentKit, AgentKitConfig

agent_kit = AgentKit(AgentKitConfig(
    wallet_provider=wallet_provider,
    action_providers=[accessibility_audit_action_provider()]
))
# Agent can now call: accessibility_paid_audit(url="https://example.com")
```

### Python client example

```python
from eth_account import Account
from x402.client import x402Client
from x402.http.clients.httpx import x402HttpxClient
from x402.mechanisms.evm.exact.client import ExactEvmScheme
from x402.mechanisms.evm.signers import EthAccountSigner

account = Account.from_key("YOUR_PRIVATE_KEY")
client = x402Client()
client.register("eip155:84532", ExactEvmScheme(signer=EthAccountSigner(account)))

async with x402HttpxClient(client) as http:
    response = await http.post(
        "https://hexdrive.tech/api/audit/paid",
        json={"url": "https://example.com"},
    )
    print(response.json())  # score, grade, issues, report_url
```

## Access

### Telegram Bot

Send any URL to [@accessibilityAuditAgentBot](https://t.me/accessibilityAuditAgentBot):

```
/start              — welcome and help
https://example.com — send a URL to audit
```

### Web Interface

Open [https://hexdrive.tech](https://hexdrive.tech), enter a URL and click **Analyze**.
Results appear at `https://hexdrive.tech/audits/<audit_id>`.

## How It Works

1. Request arrives via Telegram, web form, or paid API (`/api/audit/paid`).
2. For paid requests: x402 middleware intercepts, requires 0.10 USDC payment via EIP-3009.
3. On payment confirmation: headless Chromium (Playwright) fetches the full page.
4. BeautifulSoup runs 12 accessibility checks.
5. Score + HTML report generated, returned immediately for paid requests.

## Tech Stack

- **Python 3.12** / FastAPI / Uvicorn
- **Playwright** — headless Chromium for full page rendering
- **BeautifulSoup4** — HTML parsing and accessibility checks
- **x402** (`pip install x402[evm,fastapi]`) — HTTP payment protocol
- **python-telegram-bot 20.x** — Telegram integration
- **nginx** — reverse proxy with TLS
- **coinbase-agentkit** — AgentKit action provider

## Installation

```bash
git clone https://github.com/web3blind/accessibility-auditor.git
cd accessibility-auditor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Configure

```bash
export TELEGRAM_BOT_TOKEN="your_token"
export X402_SERVER_ADDRESS="your_wallet_address"   # receives payments
# Optional:
export X402_NETWORK="eip155:84532"                 # default: Base Sepolia
export X402_FACILITATOR_URL="https://x402.org/facilitator"
```

### Run

```bash
python3 bot_final.py
```

Starts Telegram bot + FastAPI server on `http://localhost:3000`.

## File Structure

```
accessibility-auditor/
├── bot_final.py                  # Telegram bot + FastAPI server + x402 middleware
├── agentkit_action_provider.py   # AgentKit action provider for AI agents
├── auditor.py                    # Core WCAG 2.1 checks
├── fetch_page.py                 # Playwright subprocess page fetcher
├── storage.py                    # Audit result persistence
├── report_generator.py           # HTML report generator
├── requirements.txt
├── nginx.conf
└── keep-alive.sh
```

## API Reference

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/audit/paid` | POST | x402 (0.10 USDC) | Full audit, returns JSON immediately |
| `/api/x402/info` | GET | none | Payment discovery info for agents |
| `/api/audit` | POST | none* | Submit audit (web UI only) |
| `/api/audit/{id}/status` | GET | none | Poll audit status + result |
| `/audits/{id}` | GET | none | HTML report |

*Free endpoint checks `Referer: hexdrive.tech` — not available for external API calls.

## Security

- No secrets in repository — `wallets_x402.json`, `.env`, `config.json` are all gitignored
- Audit results stored locally, not public by default
- All input validated before processing

---

Built with [Hermes Agent](https://nousresearch.com) · Real problem. Real solution.
