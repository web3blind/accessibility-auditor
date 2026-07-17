# Accessibility Auditor Multi-Page x402Escrow Plan

> **For Hermes / future `/coding` session:** this is a planning artifact only. Do not implement from this chat. Use the `coding` workflow, inspect current files again, then implement task-by-task with tests.

**Date:** 2026-07-17

**Goal:** add a variable-size, multi-page Accessibility Auditor mode where agents can lock a maximum budget through Fortytwo x402Escrow, the service audits only discovered/allowed pages, settles the actual page-based cost, and refunds unused funds.

**Chosen project:** `/home/assistent/ai-projects/accessibility-auditor`

**Decision:** extend Accessibility Auditor with a separate multi-page audit mode instead of changing the existing single-page audit flow.

- Accessibility Auditor currently audits one URL/page, while real websites have many pages and the price naturally depends on how much of the site is scanned.
- x402Escrow is useful for this variable-size work: `max budget -> actual pages scanned -> actual cost settled -> remainder refunded`.

---

## Evidence from read-only project inspection

`AGENTS.md` now exists in this repository and is the local project guide for this checkout. It confirms the live service, main entrypoints, product boundaries, x402/Arc metadata, and the rule that production/payment actions require explicit approval.

Inspected files and relevant findings:

- `README.md`
  - Live service: `https://hexdrive.tech`
  - Existing paid endpoint: `POST /api/audit/paid`
  - Existing x402 discovery: `GET /api/x402/info`
  - Existing x402 price: `0.10 USDC` for a single page audit.
  - Existing ERC-8004 / Arc identity and AgentKit positioning.
- `STATE.md`
  - Current product already has x402, Arc Testnet, ERC-8004 identity, AgentKit/OpenServ notes, and GenLayer provenance state.
- `api.py`
  - Older/separate FastAPI API surface with `/api/audit` and `/api/audit/paid`.
  - Useful reference, but live combined bot/API appears to be `bot_final.py`.
- `bot_final.py`
  - Main combined Telegram bot + FastAPI server.
  - Loads `/root/accessibility-auditor-service/config.json` in production if present.
  - Current public/free web endpoint: `POST /api/audit` with same-site Referer/Origin gate.
  - Current paid endpoint: `POST /api/audit/paid`, protected by x402 middleware.
  - Current x402 route is fixed price: `_X402_PRICE = "$0.10"`.
  - x402 SDK route currently registers Base Sepolia facilitator support, while Arc Testnet is exposed in metadata/discovery but not facilitator-registered.
  - Current `/api/x402/info` discovery returns `pricing_model: pay_per_audit`, existing capabilities, ERC-8004 identity, and client spending-control suggestions.
- `auditor.py`
  - Core page auditor: Playwright/Chromium via `fetch_page.py`, then BeautifulSoup/static heuristics.
  - No normal LLM/model summarization detected.
  - Report builder already returns normalized fields: `schema_version`, `findings`, `summary`, `mcp_payload`, `top_findings`, `manual_checks`, `next_steps`.
- `storage.py`
  - Saves one audit report as Markdown + JSON under `audits/audit_<id>.md/json`.
  - Has `save_audit_with_id`, `save_audit`, `get_audit`, `list_audits`.
  - Multi-page reports will need either a new schema shape or compatible site-level wrapper around page reports.
- `report_generator.py`
  - Renders one report to HTML.
  - Already supports executive summary, GenLayer block, passed checks, manual checks, next steps, and findings by category.
  - Needs a separate site-level report renderer or a compatibility path for multi-page aggregation.
- `mcp_server.py`
  - Local-first MCP tools already exist for URL, HTML, local project path, batch local project path, SARIF, PR markdown, and CI summaries.
  - This is useful later for exposing multi-page audits to agents, but should not be the first integration point for hosted x402Escrow.
- `project_auditor.py`
  - Already handles local project/path batch scanning and aggregation for code/project audits.
  - Some aggregation patterns can inform multi-page site aggregation, but do not mix local code scanning with public website crawling.
- `agentkit_action_provider.py`
  - Existing AgentKit action is fixed-price x402 and includes max price / daily budget guards.
  - Future x402Escrow client action should reuse this safety-control style.
- `genlayer_adjudication.py`
  - Adds optional evidence/provenance after an audit.
  - Multi-page mode should initially keep GenLayer optional and probably disabled or summarized to one compact evidence object; do not block site audits on GenLayer.
- `requirements.txt`
  - No LLM SDK dependencies are currently present.
  - Core dependencies include BeautifulSoup, Telegram bot, FastAPI, uvicorn, pydantic, Playwright.
- `tests/`
  - Existing pytest tests cover rich report shape, report rendering, storage public filter, project auditor, CLI, GenLayer, and AgentKit payment controls.
  - New work should add focused tests first.

Live read-only probes:

- `https://hexdrive.tech/` returns 200.
- `https://hexdrive.tech/api/x402/info` returns 200 and current fixed-price x402 discovery.

---

## External documentation and references

Fortytwo x402Escrow:

- Overview: `https://docs.fortytwo.network/docs/x402escrow-overview`
- Quick Start: `https://docs.fortytwo.network/docs/x402escrow-quick-start`
- Core Concepts: `https://docs.fortytwo.network/docs/x402escrow-concepts`
- Integration Guide: `https://docs.fortytwo.network/docs/x402escrow-integration-guide`
- Contract Reference: `https://docs.fortytwo.network/docs/x402escrow-contract-reference`
- Security Model: `https://docs.fortytwo.network/docs/x402escrow-security`
- GitHub repo from docs: `https://github.com/Fortytwo-Network/fortytwo-x402Escrow`

Key Fortytwo concepts relevant to this plan:

- x402Escrow is for metered AI / agent services where actual cost is unknown at request time.
- Client signs an EIP-3009 authorization for a maximum USDC amount.
- Service/facilitator calls `settle()` to lock funds.
- Service performs the job and computes actual cost.
- Service calls `release(escrowId, actualCost)`.
- Contract pays the facilitator the actual cost and refunds the remainder to the client.
- If the service fails to release, the client can claim timeout refund.
- `settle()` and `release()` are gated by `FACILITATOR_ROLE`; a normal service wallet cannot call them on the official deployed contract unless a contract admin grants that role.
- Deployed contracts shown in Fortytwo docs:
  - Base: `0x9562f50f73d8ee22276f13a18d051456d8d137a0`
  - Base Sepolia: `0x9562f50f73d8ee22276f13a18d051456d8d137a0`
  - Monad: `0x9562f50f73d8ee22276f13a18d051456d8d137a0`

### Facilitator role blocker

The official Fortytwo contract is not a permissionless escrow router. It is an AccessControl contract:

- `FACILITATOR_ROLE = keccak256("FACILITATOR_ROLE")`.
- Initial facilitator is set at proxy initialization.
- Additional facilitators are added only by an address with `DEFAULT_ADMIN_ROLE` via `grantRole(FACILITATOR_ROLE, <address>)`.
- The repository tests confirm non-facilitators revert on `settle()` and `release()`.
- Quick Start documents role management with:

```bash
cast send <PROXY_ADDRESS> \
  "grantRole(bytes32,address)" \
  $(cast call <PROXY_ADDRESS> "FACILITATOR_ROLE()(bytes32)" --rpc-url base) \
  <NEW_FACILITATOR> \
  --private-key $ADMIN_KEY \
  --rpc-url base
```

Discord search notes as of 2026-07-17:

- Search for `x402` / `x402Escrow` finds announcement/contribution posts only.
- Search for `facilitator role`, `FACILITATOR_ROLE`, `grantRole`, and `allowlist` finds no public instructions/request pattern in the visible Fortytwo Discord channels.
- Search for `facilitator` returns one unrelated use of the English word, not x402Escrow onboarding.

Implementation implication:

- Do not assume Accessibility Auditor can use Fortytwo's official deployed escrow contract directly.
- The code plan must start with dry-run/local integration and treat live official-contract settlement as blocked until Fortytwo grants facilitator role or exposes a public relay/facilitator service.
- Viable paths are:
  1. request `FACILITATOR_ROLE` from Fortytwo for our service wallet after a working demo;
  2. deploy our own x402Escrow proxy where we control admin/facilitator roles;
  3. use normal fixed-price x402 for single-page audits and keep x402Escrow as a Fortytwo-specific optional demo until role access is resolved.

General protocol references:

- x402: `https://www.x402.org/`
- WCAG overview: `https://www.w3.org/WAI/standards-guidelines/wcag/`
- WCAG 2.1 recommendation: `https://www.w3.org/TR/WCAG21/`
- Sitemap protocol: `https://www.sitemaps.org/protocol.html`
- Robots exclusion protocol: `https://www.rfc-editor.org/rfc/rfc9309`
- EIP-3009: `https://eips.ethereum.org/EIPS/eip-3009`
- Base docs: `https://docs.base.org/`
- Monad docs: `https://docs.monad.xyz/`

---

## Product concept

### Existing mode: fixed-price single page

Keep this as-is:

```text
POST /api/audit/paid
0.10 USDC -> one page audit
```

This should remain normal x402, not x402Escrow.

### New mode: variable-size site audit

Add a new, separate mode:

```text
POST /api/x402escrow/site-audit
```

User/agent requests:

```json
{
  "url": "https://example.com",
  "max_pages": 30,
  "include_summary": true,
  "same_domain_only": true
}
```

High-level flow:

```text
1. Client asks for a multi-page site audit with max_pages and max budget.
2. Server returns / requires x402Escrow max-budget payment.
3. Client signs EIP-3009 authorization for max USDC.
4. Server locks funds through x402Escrow settle().
5. Server discovers allowed pages.
6. Server audits discovered pages with the existing auditor.py page audit.
7. Server aggregates page findings into a site-level report.
8. Server computes actual cost from pages successfully audited plus optional summary fee.
9. Server calls release(escrowId, actualCost).
10. Client gets site audit id, report URL, pages scanned, actual cost, refund amount, and escrow tx metadata.
```

Example pricing:

```text
base price per audited page: 0.10 USDC
site summary fee: 0.30 USDC if include_summary=true
max locked: 3.00 USDC
pages audited: 17
actual page cost: 1.70 USDC
summary fee: 0.30 USDC
actual settled: 2.00 USDC
refund: 1.00 USDC
```

---

## Scope

Build a multi-page public website audit mode for Accessibility Auditor with x402Escrow-compatible metered pricing.

Core scope:

1. Page discovery for a target site.
2. Multi-page audit orchestration using existing `audit_website(url)`.
3. Site-level aggregation and report format.
4. Site-level HTML report rendering.
5. Price calculation based on actually audited pages and optional summary fee.
6. x402Escrow integration path after local/dry-run validation.
7. Discovery metadata so agents can understand the new escrow mode.
8. Tests for discovery, pricing, aggregation, API contracts, and safety limits.

---

## Non-goals

Do not do these in the first implementation:

- Do not replace the existing single-page `/api/audit/paid` x402 endpoint.
- Do not remove or rewrite the existing Telegram bot flow.
- Do not add LLM summarization in the first pass unless explicitly approved later.
- Do not crawl arbitrary external domains.
- Do not build a full SEO crawler.
- Do not scan private/admin areas requiring login.
- Do not run destructive browser actions such as logout, checkout, delete, submit, payment, or account actions.
- Do not depend on GenLayer success for the audit to complete.
- Do not run paid/live escrow tests without explicit user approval.
- Do not deploy to production until local tests and a public smoke plan are done.

---

## Proposed architecture

### New modules

Recommended new files:

- `site_discovery.py`
  - URL normalization and same-domain checks.
  - Fetch and parse `sitemap.xml`.
  - Fallback crawl from homepage internal links.
  - Filtering for unsafe/unwanted URLs.
  - Page cap enforcement.
- `site_auditor.py`
  - Multi-page orchestration.
  - Calls existing `audit_website(url)` for each page.
  - Concurrency limit.
  - Error handling per page.
  - Aggregation into a site-level report.
- `pricing.py`
  - Central pricing calculation for site audits.
  - Converts pages/summary/max budget into actual settled amount.
  - Avoids duplicating money math in API routes.
- `x402escrow.py`
  - Fortytwo x402Escrow client/server helper functions.
  - Initially dry-run/mockable.
  - Later real `settle()` / `release()` support.

Recommended tests:

- `tests/test_site_discovery.py`
- `tests/test_site_auditor.py`
- `tests/test_site_pricing.py`
- `tests/test_x402escrow_contracts.py` or `tests/test_x402escrow_api_contract.py`

### Existing files to modify later

- `bot_final.py`
  - Add new API route(s) and discovery metadata after core modules are tested.
  - Keep existing `/api/audit`, `/api/audit/paid`, `/api/x402/info` behavior backward compatible.
- `report_generator.py`
  - Add site-level report rendering, or a separate `SiteReportGenerator` if cleaner.
- `storage.py`
  - Add site audit save/get/list helpers, or store site-level JSON with a type marker.
- `web/index.html`
  - Later optional UI addition for multi-page mode. Not required for API MVP.
- `README.md`
  - Document the new mode after it exists and is verified.
- `schemas/`
  - Add a site-audit JSON schema once the report shape is stable.
- `agentkit_action_provider.py`
  - Later add an escrow site-audit action with max-budget controls.
- `mcp_server.py`
  - Later expose multi-page audit tool if useful, but not in the first hosted API MVP.

---

## Data model: site audit report

Suggested top-level shape:

```json
{
  "schema_version": "site-accessibility-audit/1.0.0",
  "audit_type": "site",
  "root_url": "https://example.com",
  "site_audit_id": "site_...",
  "timestamp": "...",
  "limits": {
    "max_pages_requested": 30,
    "max_pages_allowed": 50,
    "same_domain_only": true,
    "include_summary": true
  },
  "discovery": {
    "method": "sitemap_then_homepage_links",
    "candidate_urls": 42,
    "selected_urls": 30,
    "skipped_urls": [
      {"url": "...", "reason": "external_domain"}
    ]
  },
  "summary": {
    "pages_audited": 17,
    "pages_failed": 2,
    "overall_score": 74,
    "critical": 8,
    "warnings": 21,
    "info": 5,
    "overall_assessment": "..."
  },
  "repeated_issues": [
    {
      "rule_id": "images-missing-alt-text",
      "severity": "critical",
      "title": "Images missing alt text",
      "affected_pages": 12,
      "example_urls": ["https://example.com/", "https://example.com/pricing"]
    }
  ],
  "worst_pages": [
    {
      "url": "https://example.com/page",
      "score": 42,
      "critical": 3,
      "warnings": 4,
      "report_id": "..."
    }
  ],
  "page_reports": [
    {
      "url": "https://example.com/",
      "status": "ok",
      "score": 80,
      "critical": 1,
      "warnings": 2,
      "report_id": "..."
    }
  ],
  "pricing": {
    "currency": "USDC",
    "price_per_page": "0.10",
    "summary_fee": "0.30",
    "max_locked": "3.00",
    "actual_settled": "2.00",
    "refund": "1.00"
  },
  "escrow": {
    "mode": "dry_run|live",
    "network": "base|monad",
    "escrow_id": "...",
    "settle_tx": "...",
    "release_tx": "..."
  }
}
```

Compatibility rule:

- Do not force existing single-page reports into this shape.
- Add a clear `audit_type: "site"` so renderers/API clients can branch safely.

---

## Page discovery rules

MVP discovery order:

1. Normalize root URL.
2. Try `https://domain/sitemap.xml`.
3. Parse XML sitemap URLs if available.
4. If sitemap is absent or empty, fetch homepage and collect internal `<a href>` links.
5. Deduplicate and normalize URLs.
6. Keep only same registrable host/domain for MVP.
7. Remove fragments.
8. Strip or dedupe tracking query parameters where safe.
9. Exclude non-HTML resources by extension.
10. Exclude dangerous or irrelevant paths.
11. Cap to `max_pages` and global server max.

Suggested excluded path patterns:

```text
/logout
/signout
/delete
/remove
/cart
/checkout
/payment
/pay
/admin
/wp-admin
/account
/profile
/settings
/download
*.pdf
*.zip
*.mp4
*.mp3
*.png
*.jpg
*.jpeg
*.gif
*.webp
*.svg
```

Robots/sitemap posture:

- Respect sitemap as preferred source.
- Do not become a broad crawler.
- Consider `robots.txt` support after MVP or as a safe read-only filter if easy.

Limits:

- User-facing `max_pages`: 1-50 for MVP.
- Default `max_pages`: 10 or 20.
- Server hard cap: 50.
- Per-page timeout: reuse existing auditor timeout, or add lower site-audit timeout.
- Concurrency: 2-3 pages at a time to avoid overloading sites/server.

---

## Pricing model

### First pass: deterministic, no LLM

Use only page count and optional code-generated summary.

Suggested constants:

```text
SITE_AUDIT_PRICE_PER_PAGE_USDC = 0.10
SITE_AUDIT_SUMMARY_FEE_USDC = 0.30
SITE_AUDIT_MAX_PAGES = 50
SITE_AUDIT_MIN_CHARGE_USDC = 0.10
```

Actual cost formula:

```text
actual_cost = successful_pages * price_per_page
if include_summary and successful_pages > 1:
    actual_cost += summary_fee
actual_cost = min(actual_cost, max_locked)
```

Failed page policy for MVP:

- Do not charge for pages that fail before an audit report is produced.
- Record them in `pages_failed` with error reason.
- If every page fails, release zero or minimum charge only if explicitly approved later. Default: release zero for first implementation.

Why no model-based fee yet:

- Current codebase does not show OpenAI/Anthropic/LLM summarization dependencies for the auditor.
- Existing summary is deterministic in `auditor.py` / report aggregation.
- Adding LLM summary is a separate product decision and would add API keys, cost controls, prompt tests, and privacy claims.

### Later optional: AI summary

If explicitly approved later:

```text
actual_cost = page_cost + deterministic_summary_fee + optional_ai_summary_fee
```

But only after:

- model/provider is chosen;
- secret handling is defined;
- user copy clearly labels AI summary as optional;
- token/cost limits are implemented;
- tests cover opt-in/off behavior.

---

## x402Escrow integration strategy

### Phase 0: dry-run only

Before any real funds:

- Implement discovery, aggregation, pricing and API contract with `escrow.mode = "dry_run"`.
- Return fake/deterministic `escrow_id` for local tests.
- Validate all money math with `Decimal`, not floats.
- Do not call chain contracts.

### Phase 1: local contract helper

Add `x402escrow.py` with functions that can be unit-tested without network:

- parse payment authorization header;
- compute deterministic escrow id from client + nonce;
- build settle/release transaction payloads or call wrappers;
- parse event logs from a mocked receipt;
- handle timeout/refund metadata.

### Phase 2: real testnet/small amount

Only after explicit approval:

- Use Fortytwo docs and contract reference to wire `settle()` and `release()`.
- Use Base or Monad as Fortytwo-supported networks.
- Run one small controlled site audit.
- Verify:
  - funds locked;
  - release amount equals actual cost;
  - refund is visible or derivable;
  - report stores tx metadata.

### Phase 3: public discovery

Add an endpoint like:

```text
GET /api/x402escrow/info
```

or extend existing `/api/x402/info` without breaking old fields:

```json
{
  "escrow_enabled": true,
  "escrow_endpoint": "POST /api/x402escrow/site-audit",
  "pricing_model": "metered_per_page",
  "price_per_page": "$0.10",
  "summary_fee": "$0.30",
  "max_pages": 50,
  "networks": ["base", "monad"],
  "client_controls": [
    "max_pages",
    "max_budget_usdc",
    "same_domain_only",
    "allowed_domains",
    "human_approval_above_limit_usd"
  ]
}
```

Backward compatibility:

- Existing `/api/x402/info` clients must still see the old fixed-price single-audit fields.
- Do not rename `paid_endpoint`, `price`, `capabilities`, or ERC-8004 fields without a versioned contract.

---

## API design

### Dry-run / preview endpoint

Useful before payment:

```text
POST /api/site-audit/quote
```

Request:

```json
{
  "url": "https://example.com",
  "max_pages": 30,
  "include_summary": true,
  "same_domain_only": true
}
```

Response:

```json
{
  "root_url": "https://example.com",
  "max_pages": 30,
  "estimated_max_cost_usdc": "3.30",
  "price_per_page_usdc": "0.10",
  "summary_fee_usdc": "0.30",
  "hard_page_cap": 50,
  "payment_mode": "x402escrow",
  "note": "Final cost depends on pages actually audited. Unused escrow is refunded."
}
```

Important: quote should not perform a full crawl beyond cheap validation unless explicitly designed as a discovery preview.

### Paid escrow endpoint

```text
POST /api/x402escrow/site-audit
```

Request:

```json
{
  "url": "https://example.com",
  "max_pages": 30,
  "include_summary": true,
  "same_domain_only": true,
  "max_budget_usdc": "3.30"
}
```

Response:

```json
{
  "paid": true,
  "audit_type": "site",
  "site_audit_id": "site_abc123",
  "report_url": "https://hexdrive.tech/site-audits/site_abc123",
  "pages_audited": 17,
  "pages_failed": 2,
  "actual_settled_usdc": "2.00",
  "refund_usdc": "1.30",
  "escrow": {
    "network": "base",
    "escrow_id": "...",
    "settle_tx": "...",
    "release_tx": "..."
  }
}
```

### Report routes

Add routes such as:

```text
GET /site-audits/{site_audit_id}
GET /api/site-audits/{site_audit_id}
GET /api/site-audits/{site_audit_id}/status
```

Whether processing should be synchronous or background:

- For MVP, prefer background processing like current free audit flow if multi-page scanning can exceed HTTP timeouts.
- The escrow lifecycle must be robust if the background task fails: release zero or safe actual amount; never leave funds locked without a recovery path.

---

## UX / product copy

Public explanation:

```text
Multi-page accessibility audit with refundable budget.
Lock a maximum amount with x402Escrow. The auditor scans only allowed pages on your site, charges by the pages actually audited, and refunds unused funds automatically.
```

Avoid claiming:

- “full WCAG certification”;
- “complete accessibility compliance”;
- “all pages and all issues found”.

Keep honest language:

- automated checks catch common issues;
- manual screen-reader and keyboard verification is still required;
- dynamic/authenticated flows are not covered by public crawling.

---

## Security and safety requirements

Crawler safety:

- Same-domain only for MVP.
- Strict page cap.
- No form submission.
- No clicks beyond normal page load.
- Exclude logout/delete/payment/admin paths.
- Exclude non-HTML files.
- Limit concurrency.
- Per-page timeout.
- Record skipped URLs and reasons.

Payment safety:

- Use `Decimal` for USDC values.
- Do not print private keys, payment signatures, raw auth headers, or wallet secrets.
- Store only safe public tx metadata.
- If audit fails before work is done, release zero when possible.
- Add a recovery command/runbook for settled-but-unreleased escrows.
- Do not run live settlement from tests.

Production safety:

- Do not deploy until local test suite passes.
- Do not alter existing single-page x402 endpoint behavior.
- Back up production files before modifying `/root/accessibility-auditor-service` or `/www/wwwroot/hexdrive.tech`.
- Verify public endpoints after deploy.

---

## Implementation phases

### Phase 1 — Discovery and pricing foundation, no payments

Outcome:

- `site_discovery.py` returns a safe, capped URL list.
- `pricing.py` computes max/actual costs deterministically.
- Unit tests prove domain filtering, skip rules, caps, and price math.

Tasks:

1. Add `site_discovery.py` with URL normalization helpers.
2. Add tests for same-domain matching and URL normalization.
3. Add sitemap parsing helper using stdlib XML parser.
4. Add tests for sitemap parsing and cap enforcement.
5. Add homepage-link extraction helper using BeautifulSoup.
6. Add tests for fallback homepage discovery with internal/external/dangerous links.
7. Add `pricing.py` with `Decimal`-based cost functions.
8. Add tests for page-only, page+summary, zero-success, and max-budget cases.

Validation commands:

```bash
pytest tests/test_site_discovery.py tests/test_site_pricing.py -v
python -m py_compile site_discovery.py pricing.py
```

### Phase 2 — Multi-page audit aggregation, no payments

Outcome:

- `site_auditor.py` can audit a list of URLs using existing `audit_website`.
- Site-level report aggregates page results.
- Failed pages do not crash the whole site audit.

Tasks:

1. Add `site_auditor.py` with `audit_site(root_url, max_pages, include_summary)`.
2. Add injectable page-audit function for tests to avoid real network/Playwright.
3. Aggregate counts: pages audited, pages failed, critical/warning/info totals.
4. Compute repeated issues by `rule_id` and affected pages.
5. Compute worst pages by score/critical count.
6. Add deterministic site-level summary without LLM.
7. Add tests with fake page reports.
8. Add tests for partial failure behavior.

Validation commands:

```bash
pytest tests/test_site_auditor.py -v
python -m py_compile site_auditor.py
```

### Phase 3 — Site report storage and HTML rendering

Outcome:

- Site reports can be saved and loaded separately from single-page audits.
- Site report has an HTML view.

Tasks:

1. Extend `storage.py` with site audit save/get methods or create `site_storage.py`.
2. Add tests for saving/loading site reports.
3. Add `generate_site_html(report)` in `report_generator.py` or a new `site_report_generator.py`.
4. Render summary, pages audited/failed, repeated issues, worst pages, and per-page links.
5. Add tests for site report HTML key sections.

Validation commands:

```bash
pytest tests/test_site_storage.py tests/test_site_report_generator.py -v
python -m py_compile storage.py report_generator.py
```

### Phase 4 — Dry-run API route

Outcome:

- API route exists for dry-run/preview without real escrow.
- Existing routes remain unchanged.

Tasks:

1. Add request/response models in `bot_final.py` or a small route module if refactoring is safe.
2. Add `POST /api/site-audit/quote`.
3. Add dry-run `POST /api/x402escrow/site-audit` behind an env flag such as `X402ESCROW_DRY_RUN=1`.
4. Return `escrow.mode = dry_run` and deterministic fake escrow id.
5. Add tests for route contract using FastAPI test client if feasible.
6. Verify existing `/api/audit/paid` and `/api/x402/info` output shape remains compatible.

Validation commands:

```bash
pytest tests/test_x402escrow_api_contract.py -v
python -m py_compile bot_final.py
```

### Phase 5 — x402Escrow contract helper, still no live payment by default

Outcome:

- x402Escrow helper is testable and disabled unless configured.

Tasks:

1. Add `x402escrow.py` with config loading and disabled-by-default behavior.
2. Implement `compute_escrow_id(client, nonce)` per Fortytwo docs.
3. Add typed helpers for settle/release parameters.
4. Add tests for escrow id and validation.
5. Add error types for settle/release/refund states.
6. Add recovery/runbook notes to README or deployment docs.

Validation commands:

```bash
pytest tests/test_x402escrow_contracts.py -v
python -m py_compile x402escrow.py
```

### Phase 6 — Live testnet integration, only after explicit approval

Outcome:

- One tiny controlled live escrow flow can be executed and verified, but only after the facilitator-role path is resolved.

Tasks:

1. Confirm network, contract address, facilitator wallet, USDC source, and whether this is the official Fortytwo contract or our own deployed proxy.
2. Check `hasRole(FACILITATOR_ROLE, <service_wallet>)` before attempting `settle()`.
3. If the official Fortytwo contract returns `false`, do not run live settlement; either:
   - request `FACILITATOR_ROLE` from Fortytwo with the service wallet and demo description; or
   - deploy our own x402Escrow proxy for the demo where we control admin/facilitator roles.
4. Add env vars for escrow contract/network, never hardcode secrets.
5. Run one small live request on a test domain with `max_pages=1` or `2` only after role check passes.
6. Verify settle tx, release tx, actual cost, refund, report URL.
7. Store only safe tx metadata.
8. Document observed network behavior and any Fortytwo-specific quirks.

Hard stop:

- Ask Denis before any live payment/settlement test.
- Ask Denis before requesting facilitator role in Discord or from the Fortytwo team.
- Ask Denis before deploying our own escrow proxy.

### Phase 7 — Docs and public packaging

Outcome:

- Project has a clear Fortytwo-facing demo story.

Tasks:

1. Update `README.md` with multi-page x402Escrow mode.
2. Add a concise technical sequence diagram.
3. Add `/api/x402escrow/info` docs and examples.
4. Add copy for Fortytwo Discord/contribution post.
5. Optional: add a small public page explaining multi-page audit pricing.

---

## Implementation progress in this checkout

Completed locally on 2026-07-17:

- Phase 1 foundation implemented:
  - `site_discovery.py` for conservative same-site discovery via sitemap and homepage links.
  - `site_pricing.py` for Decimal-based quote and settlement/refund math.
- Phase 2 aggregation implemented:
  - `site_auditor.py` orchestrates capped multi-page audits, records per-page failures, repeated issues, worst pages, and site-level summary.
- Phase 3 storage/rendering implemented:
  - `AuditStorage.save_site_audit*()` / `get_site_audit()` save separate `site_audit_*.json/md` files.
  - `ReportGenerator.generate_site_html()` renders a site-level report.
- Phase 4 dry-run API implemented in `bot_final.py`:
  - `POST /api/site-audit/quote`
  - `GET /api/x402escrow/info`
  - `POST /api/x402escrow/site-audit` in dry-run mode
  - `GET /site-audits/{site_audit_id}` and `GET /api/site-audits/{site_audit_id}`
- Phase 5 helper scaffold implemented:
  - `x402escrow.py` exposes dry-run Fortytwo-shaped metadata and deterministic escrow IDs.

Validation run after this implementation and the follow-up cap/Markdown/payment-gate update:

```bash
.venv/bin/python -m py_compile site_discovery.py site_pricing.py site_auditor.py x402escrow.py storage.py report_generator.py bot_final.py
.venv/bin/python -m pytest -q
# 63 passed
```

Follow-up adjustments from Denis:

- Confirmed product boundary: public website and Telegram bot remain single-page/free; multi-page is for Fortytwo x402Escrow paid agent flow only.
- Raised hard page cap from 50 to 100.
- Added runtime guards for large jobs:
  - per-page timeout is accepted in the API and clamped to 5-90 seconds;
  - total site-audit duration is accepted in the API and clamped to 30-1800 seconds;
  - `audit_site()` records timed-out/skipped pages instead of hanging the whole job;
  - network/browser fetch failures are treated as failed pages and are not billed as successful audits.
- Added Markdown delivery for agents:
  - `GET /site-audits/{site_audit_id}.md` returns `text/markdown`;
  - `GET /api/site-audits/{site_audit_id}/markdown` returns `{format, content}`;
  - `POST /api/x402escrow/site-audit` accepts `output_format: "markdown"` and includes a `markdown` field plus Markdown URLs.
- Added x402Escrow payment gate:
  - `POST /api/x402escrow/site-audit` returns HTTP 402 payment requirements when `X-PAYMENT` is absent;
  - local dry-run requests require explicit operator env `X402ESCROW_ALLOW_DRY_RUN_REQUESTS=1`;
  - if `X-PAYMENT` is present but live settlement is not configured, the route returns 501 and does not run the audit;
  - live `settle()` / `release()` / `getEscrow()` scaffolding is implemented with `web3`, pending-escrow persistence, and `/api/x402escrow/facilitator-status` role check;
  - production activation now requires only env secrets/params plus confirmed `FACILITATOR_ROLE`.
- Fortytwo docs/repo findings:
  - docs list deployed x402Escrow contracts on Base and Monad at `0x9562f50f73d8ee22276f13a18d051456d8d137a0`;
  - repo deployment docs also mention `base_sepolia` and `monad_testnet`, but public docs' deployed-contract table points to Base/Monad explorers;
  - `FACILITATOR_ROLE` can call `settle()` and `release()`; `DEFAULT_ADMIN_ROLE` can grant/revoke roles;
  - if Accessibility Auditor is not an admin of Fortytwo's deployed contract, it must request facilitator role from Fortytwo or deploy its own escrow instance.
- Live dry-run smoke against `https://fortytwo.network` with `max_pages=1` through the API route completed locally:
  - pages audited: 1;
  - pages failed: 0;
  - score: 75, grade: C;
  - dry-run pricing: max locked 0.40 USDC, actual settled 0.10 USDC, refund 0.30;
  - Markdown field and Markdown URL were returned.

Still not done:

- No live Fortytwo escrow `settle()` / `release()` calls.
- No production deploy.
- No live paid/on-chain test.
- No Telegram multi-page UX.

---

## Test strategy

Run focused tests during implementation, then full project tests.

Likely commands:

```bash
python -m py_compile auditor.py fetch_page.py storage.py report_generator.py bot_final.py
pytest tests/test_accessibility_auditor.py tests/test_project_auditor.py tests/test_cli.py -v
pytest tests/test_site_discovery.py tests/test_site_pricing.py tests/test_site_auditor.py -v
pytest tests/test_x402escrow_api_contract.py tests/test_x402escrow_contracts.py -v
```

If Playwright/browser tests are added, keep them separate from pure unit tests and do not require external sites for the default suite.

---

## Completion contract

### Outcome

Accessibility Auditor supports a new multi-page site audit mode that is suitable for x402Escrow metered billing, without breaking the existing single-page x402 audit.

### Verification

Implementation is not complete until these are true:

- Discovery unit tests pass.
- Pricing unit tests pass and use `Decimal`.
- Aggregation tests pass for multi-page success and partial failure.
- API contract tests pass for quote/dry-run escrow route.
- Existing tests still pass for single-page auditor/report/storage/CLI.
- Existing `https://hexdrive.tech/api/x402/info` compatibility is preserved after deploy.
- If live escrow is enabled, a real small-amount test verifies settle and release txs.

### Constraints

- No production deploy without backup and public smoke.
- No live paid/escrow test without explicit approval.
- No secrets in repo, logs, PLAN, README, tests, or output fixtures.
- No broad crawler behavior.
- No LLM summary in MVP unless separately approved.

### Boundaries

In scope:

- `/home/assistent/ai-projects/accessibility-auditor`
- Hosted Accessibility Auditor service on `hexdrive.tech` only after explicit deploy phase.
- Fortytwo x402Escrow integration only for multi-page site audit.

Out of scope:

- Telegram bot multi-page UX in MVP.
- Login/private area auditing.
- Production live payment tests without approval.

### Stop when

Stop and ask Denis if:

- Fortytwo docs/API behavior differs from this plan.
- A live payment/settlement test is needed.
- The implementation requires adding an LLM provider/API key.
- The crawler would need to access authenticated or destructive flows.
- Existing production x402 endpoint would need a breaking change.

---

## Recommended next `/coding` prompt

Use this in the project topic when ready:

```text
/coding В проекте /home/assistent/ai-projects/accessibility-auditor реализуй Phase 1 из PLAN.md: site_discovery.py + pricing.py, только dry-run/no payments. Сначала перечитай PLAN.md и текущие файлы. Делай TDD, не трогай production и не меняй существующий /api/audit/paid.
```
