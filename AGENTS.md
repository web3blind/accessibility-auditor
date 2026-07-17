# AGENTS.md

## Tone
- Пиши кратко, по делу, без воды.
- Для Дениса отделяй проверенные факты от предположений; не обещай деплой/фикс без реальной проверки.

## Project Context
- Что это: Accessibility Auditor — сервис аудита доступности сайтов по WCAG 2.1 с веб-интерфейсом, Telegram-ботом, API, x402 pay-per-audit, ERC-8004/Arc metadata, GenLayer provenance preview, локальным CLI/MCP и GitHub Action для статического аудита проектов.
- Repo: `https://github.com/web3blind/accessibility-auditor`.
- Live: `https://hexdrive.tech`.
- Telegram bot: `@accessibilityAuditAgentBot`.
- Основная рабочая директория Дениса: `/home/assistent/ai-projects/accessibility-auditor`.
- Production notes from repo docs mention `/root/accessibility-auditor-service` and older `~/.hermes/agents/accessibility-auditor`; do not assume local checkout equals production without checking the server/path first.

## Main Entrypoints
- `bot_final.py` — main combined Telegram bot + FastAPI server on `127.0.0.1:3000`; this is the live-style entrypoint to prefer over older split API code.
- `api.py` — older/separate FastAPI surface; useful for reference, but do not treat it as primary until runtime proves it is used.
- `auditor.py` — single-page website auditor: Playwright subprocess fetch via `fetch_page.py`, BeautifulSoup/static heuristics, normalized report generation.
- `fetch_page.py` — headless Chromium page fetcher used by `auditor.py`.
- `storage.py` — saves audit Markdown/JSON under `audits/`; generated audit data is gitignored.
- `report_generator.py` — HTML report renderer for stored audit results.
- `genlayer_adjudication.py` — optional GenLayer evidence/provenance bridge; must degrade to local deterministic preview when credentials/CLI are unavailable.
- `agentkit_action_provider.py` — Coinbase AgentKit action provider and client-side spending controls for paid x402 audits.
- `cli.py` — local CLI for URL, HTML file, inline HTML, project/path, batch, SARIF, PR markdown, CI summary, and GitHub annotations.
- `mcp_server.py` + `run_mcp_server.sh` — local-first MCP stdio server; raw private code/HTML should stay local.
- `project_auditor.py` — local project/static source scanning and platform detection for web, Android, iOS, Flutter, React Native, Electron, PyQt, and WPF.
- `review_exporter.py` — PR/CI/SARIF/GitHub annotation exporters.
- `openserv/src/agent.ts` — OpenServ SDK agent that calls the Python backend.
- `github-action/` — Docker-based GitHub Action wrapping the CLI.
- `web/index.html` — public frontend shell.
- `schemas/accessibility-audit-report.schema.json` — stable structured report contract.

## Repository Structure
- `tests/` — pytest coverage for rich reports, storage public filtering, GenLayer adjudication, AgentKit payment controls, CLI formats, project auditor, review exporter, and GitHub annotations.
- `schemas/` — report schema and compatibility notes. Preserve `findings`, `findings_by_severity`, `issues_by_category`, `mcp_payload`, `schema_version`, and `schema_id` compatibility unless intentionally migrating.
- `openserv/` — Node/TypeScript OpenServ adapter with its own `package.json`, `tsconfig.json`, lockfile, and `.env` ignored.
- `github-action/` — Dockerfile, `action.yml`, and shell entrypoint for CI usage.
- `web/` — static web UI assets.
- `audits/` — generated runtime reports, intentionally ignored.
- `venv/`, `.venv/`, `mcp_venv/`, `openserv/node_modules/`, `openserv/dist/`, `.playwright/` — local/generated dependencies, ignored.
- `PLAN.md` / `plan.md` — planning artifacts; inspect before implementing related work, but do not treat plans as completed code.
- `STATE.md` — useful product/integration state, but may contain time-sensitive infrastructure notes; verify live state before acting.

## Run And Validation
- Create Python env: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && playwright install chromium`.
- Run main service locally: `source venv/bin/activate && python3 -u bot_final.py`.
- Main service requires `TELEGRAM_BOT_TOKEN` or `/root/accessibility-auditor-service/config.json`; do not fake it in tests.
- Run CLI examples:
  - `python cli.py audit ./some-project --format json`
  - `python cli.py audit-url https://example.com --format json`
  - `python cli.py audit-html-file ./page.html --format pr-markdown`
  - `python cli.py audit ./some-project --format ci-summary --fail-threshold 70`
- Run MCP server: `./run_mcp_server.sh` (creates/uses `mcp_venv`, installs `mcp-requirements.txt`, installs Chromium, then runs `mcp_server.py`).
- OpenServ adapter: `cd openserv && npm install && npm run build`; runtime uses `npm run start` or `npm run dev`.
- Preferred Python validation for changed modules: `venv/bin/python -m py_compile <changed .py files>` or `.venv/bin/python -m py_compile ...` depending on the available env.
- Preferred tests: `venv/bin/python -m pytest` or `.venv/bin/python -m pytest`.
- Targeted regression examples:
  - `python -m pytest tests/test_accessibility_auditor.py`
  - `python -m pytest tests/test_cli.py tests/test_project_auditor.py tests/test_review_exporter.py`
  - `python -m pytest tests/test_genlayer_adjudication.py tests/test_agentkit_payment_controls.py`
- After report/schema/exporter changes, also validate JSON/SARIF output parses.

## Architecture And Data Flow
- Website/Telegram/free API flow: user URL -> `bot_final.py` route/handler -> `audit_website()` in `auditor.py` -> `fetch_page.py` Playwright render -> BeautifulSoup checks -> `AuditStorage` JSON/MD -> `ReportGenerator` HTML -> short Telegram/API summary.
- Paid flow: `POST /api/audit/paid` is protected by x402 middleware when x402 imports/config are available; keep single-page fixed-price x402 separate from any future multi-page escrow mode.
- Discovery flow: `GET /api/x402/info` should expose positive service capabilities, pay-per-audit metadata, ERC-8004 identity, and client spending-control suggestions.
- Local-first code-audit flow: `cli.py`/`mcp_server.py` -> `project_auditor.py` -> `review_exporter.py`/SARIF/CI output; do not send private source to hosted APIs.
- GenLayer flow: report -> compact evidence -> optional CLI/network adjudication; when disabled or unavailable, return the same public shape with local preview, not a hard failure.

## Product Boundaries
- Keep the canonical report rich; Telegram/bot output must stay a compact summary with score, grade, counts, top findings, and full report link.
- Hosted/public service is for public URL audits. For private code, prefer local CLI, local MCP, GitHub Action, or self-hosted deployment.
- Do not position a hosted API for uploading private source code as the main product.
- Keep simple x402 product model first: ERC-8004 identity + x402 pay-per-audit + client-side spending limits.
- Do not add subscription, split-payment, escrow, or Vyper contract production dependencies unless there is a concrete product requirement and explicit approval.
- If implementing future x402Escrow/multi-page mode, keep it separate from existing `/api/audit/paid`; do not replace the fixed-price single-page endpoint.

## Accessibility Report Contract
- Scoring formula is transparent: `max(0, 100 - critical*10 - warning*5 - info*1)`; do not inflate scores.
- Keep grade scale stable: A 90-100, B 80-89, C 70-79, D 60-69, F <60.
- Keep `findings` as the normalized list for API/MCP consumers.
- Keep `issues_by_category` and `findings_by_severity` for backward-compatible website/bot/report rendering.
- Keep `mcp_payload` as the transport-friendly subset for MCP-style tools.
- User-facing risk/status copy must not expose internal terms like artifact paths or JSON filenames.
- Client-facing summaries should use words like “risk summary/profile”; for old records say a new audit is needed for an актуальная сводка.

## File Ownership And Boundaries
- Do not change `bot_final.py` startup/config behavior casually: it mixes Telegram polling, FastAPI, x402 middleware, report routes, and production config fallback.
- Do not edit generated runtime files in `audits/`, logs, `.bot.pid`, `bot.pid`, or caches as source changes.
- Do not commit secrets or local credentials: `.env`, `config.json`, `wallets_x402.json`, `erc8004_registration.json`, `openserv/.env`, Synthesis files, private keys, tokens, and bot tokens are gitignored and must stay out of diffs.
- Public transaction hashes and explorer URLs are not secrets, but still inspect diffs before commit.
- `api.py` may lag behind `bot_final.py`; if adding endpoints, confirm which server is actually deployed before editing both.
- `STATE.md` can mention expired or stale infra values; verify SSL, DNS, service paths, wallets, and process managers live before operational changes.
- Do not run paid/live x402, on-chain, GenLayer, registration, or deployment actions without explicit approval.
- Do not deploy or restart production services until local tests and a concrete smoke plan pass.

## Project Conventions
- Python code is currently simple module-per-feature, no package directory; imports are local module imports from repo root.
- Keep report dictionaries backward-compatible; many surfaces read top-level keys like `url`, `score`, `grade`, `total_issues`, `critical`, `warnings`, `info`, `issues_by_category`, `summary`, `top_findings`, `manual_checks`, and `findings`.
- Favor deterministic local fallbacks for optional integrations so the public service still returns useful results when x402/GenLayer/OpenServ dependencies are missing.
- CLI exit codes: `0` pass, `1` fail threshold/critical findings, `2` usage/rendering error.
- Exporters should avoid embedding raw source code; use file paths, line numbers, rule IDs, and recommendations.
- For local project audits, keep platform-specific static heuristics honest: many runtime/screen-reader issues need manual follow-up.
- In Telegram Markdown strings, keep output short enough to avoid truncation and include the full report URL.
- For OpenServ code, use the backend URL from `BACKEND_URL` with `http://localhost:3000` fallback and keep secrets in `openserv/.env`.

## Config And Secrets
- Python runtime env/config:
  - `TELEGRAM_BOT_TOKEN` for bot startup.
  - `X402_SERVER_ADDRESS`, `EVM_SERVER_ADDRESS`, `X402_NETWORK`, `X402_FACILITATOR_URL` for payments/metadata depending on code path.
  - `GENLAYER_ENABLED`, `GENLAYER_CONTRACT_ADDRESS`, `GENLAYER_NETWORK`, `GENLAYER_CLI_WORKDIR`, and keystore password envs for real GenLayer calls.
- Production `bot_final.py` first checks `/root/accessibility-auditor-service/config.json`; local runs usually use env vars.
- Never print private keys, tokens, wallet JSON contents, or keystore passwords.
- If a diff shows a real secret, treat it as compromised; remove it and tell Denis plainly.

## Deployment And Operations Notes
- Live architecture from docs: Internet -> nginx TLS for `hexdrive.tech` -> localhost:3000 running `bot_final.py`.
- `nginx.conf`, `DEPLOYMENT.md`, `start_bot.sh`, `keep-alive.sh`, and `KEEP_ALIVE_README.md` document the historical deployment.
- `keep-alive.sh` uses `$HOME/.hermes/agents/accessibility-auditor`, PID tracking, log rotation, `.env` loading, and cron-style restart; verify path before relying on it.
- Before changing production, inspect current process manager and logs. Repo docs mention both systemd `accessibility-auditor` and pm2 `openserv-agent`; do not assume.
- After API/report changes, smoke-check `/`, `/api/x402/info`, free web audit behavior, paid route metadata, and an existing `/audits/<id>` report when safe.

## Update Rules
- If changing `auditor.py` output shape, update `schemas/accessibility-audit-report.schema.json`, `schemas/README.md`, `report_generator.py`, CLI/MCP adapters, and tests.
- If changing project-audit findings, update `project_auditor.py`, `review_exporter.py`, schema expectations, CLI tests, and GitHub Action behavior when relevant.
- If changing x402 discovery/payment behavior, update README, AgentKit provider, `/api/x402/info` tests, and client spending-control docs/examples.
- If changing Telegram report text, keep website canonical report rich and verify the Telegram summary remains compact.
- If changing OpenServ capabilities, update `openserv/src/agent.ts`, run `npm run build`, and keep `openserv/.env` ignored.
- If changing deployment scripts, update `DEPLOYMENT.md` or `KEEP_ALIVE_README.md` with the real path/process manager.
- Before committing, run `git status`, inspect `git diff`, and search the diff for secrets; generated caches/logs/audits should not be staged.

## Known Pitfalls
- `bot_final.py` exits immediately without token/config, so import/startup tests need monkeypatching or targeted module tests.
- `auditor.py` looks for `venv/bin/python3` beside the repo for `fetch_page.py`; if absent it falls back to `sys.executable`.
- Playwright/Chromium must be installed in the active environment for live URL audits.
- `report_generator.py` and `storage.py` assume specific legacy top-level report keys; schema changes can break existing HTML/report routes.
- `api.py` references `x402_config.py`, which is gitignored; do not rely on it in fresh checkouts.
- `STATE.md` includes public wallet addresses/tx hashes and secret file names; do not copy secrets from local ignored files into docs.
- `PLAN.md` is currently untracked in this checkout; preserve it unless Denis asks to commit/remove it.
