# Accessibility Auditor Improvement Plan

## Scope
Improve the existing accessibility auditor so that:
- the website shows a more detailed, structured audit report
- the Telegram bot keeps a concise summary suitable for message limits
- the core rule set grows beyond the current minimal checks without pretending to fully automate all WCAG testing
- public-audit website UX matches backend behavior
- a local-first MCP server can expose the auditor to agents without sending company code/site data to a hosted service
- platform-aware local project audits cover mobile/desktop/web codebases more usefully
- batch MCP tools support multi-project/company workflows

## Non-goals
- Rewriting the whole service into a new architecture
- Building a hosted-only MCP/API gateway for private company code
- Implementing browser-driven runtime/manual checks beyond current static/rendered HTML heuristics
- Replacing Telegram bot transport or x402 integration

## Current findings
- Core auditor currently runs only 12 coarse checks and duplicates some logic (`lang` checked twice).
- Web UI promises public audit sharing, but `/api/audit` ignored `is_public`.
- Website asks for a detailed product story, but reports mostly list flat categories/issues.
- Bot previously dumped all categories/issues into one Telegram message and then truncated at 4000 chars.
- Report model lacked explicit metadata for quick vs full output, manual follow-up, or prioritized next steps.
- There was no local MCP server layer for privacy-sensitive company usage.
- Initial project MCP foundation existed, but platform-specific depth and multi-target workflows were still limited.

## Implementation phases

### Phase 1 — Expand and normalize audit output
- Refactor `auditor.py` report format to include:
  - executive summary
  - findings grouped by severity and category
  - passed checks
  - manual follow-up checks
  - prioritized next steps
  - audit mode metadata (`full` for site/API)
- Add practical high-value checks such as:
  - page title
  - skip link
  - landmark presence
  - duplicate IDs
  - buttons/links accessible names
  - iframe title
  - icon/button text issues
  - focus-outline removal heuristic
  - suspicious positive tabindex
  - autocomplete hints for personal data fields
  - missing labels including wrapped-label fallback

### Phase 2 — Improve site report presentation
- Upgrade `report_generator.py` to render:
  - executive summary
  - critical/warning/info sections
  - passed checks
  - manual verification section
  - next steps section
  - category navigation/summary blocks
- Update homepage copy in `web/index.html` so website clearly advertises full detailed audit.

### Phase 3 — Keep Telegram concise
- Change bot formatting to send:
  - top summary
  - top critical/warning findings only
  - explicit link to full web report
  - note that Telegram uses a short version while the web report is full

### Phase 4 — Fix API/UI mismatches
- Extend API request model to accept `is_public`.
- Pass public flag into storage and list endpoint.
- Ensure website recent-public-audits feature works against backend.

### Phase 5 — MCP-friendly structured schema
- Add `schema_version` and `schema_id` to report payloads.
- Add normalized `findings` array for tool/API consumers.
- Add `mcp_payload` shape as future MCP return contract.
- Publish JSON Schema file from the service.

### Phase 6 — Local-first MCP server
- Implement a stdio MCP server that runs on the same machine as the code/site being audited.
- Initial toolset:
  - `audit_url` — audits a URL locally and returns normalized findings
  - `audit_html_file` — audits a local HTML file path without uploading file contents to a remote service
  - `audit_html` — audits raw HTML passed by a local caller, returns only structured findings
  - `get_audit_schema` — returns the JSON schema for clients
- Keep outputs structured and minimized so agents do not need full source dumps.
- Document privacy model and local usage for companies.

### Phase 7 — Platform-aware MCP foundation
- Add `detect_target_type(path)` to classify local projects as web / Android / iOS / Flutter / React Native / Electron / PyQt / WPF / unknown.
- Add `audit_project_path(path)` that scans a local project directory, discovers relevant files, runs platform-appropriate static checks, and returns normalized structured findings.
- Keep this layer local-first so companies can audit private repos/build artifacts inside their own environment.
- Reuse the same normalized schema so future MCP/API consumers can handle all target types consistently.

### Phase 8 — Deeper mobile checks + batch workflows
- Add richer Android static checks:
  - unlabeled `TextView`/custom clickable containers
  - `importantForAccessibility` misuse review
  - `labelFor` / contentDescription / hint heuristics where useful
- Add richer Flutter checks:
  - `ExcludeSemantics`, `Semantics`, `Image.*`, `GestureDetector`, `InkWell`, `IconButton` heuristics
- Add richer React Native checks:
  - `accessible`, `accessibilityLabel`, `accessibilityRole`, `accessibilityHint` heuristics
- Add file/line hints to findings where practical.
- Add batch MCP tools:
  - `audit_many_project_paths`
  - `detect_many_target_types`

### Phase 9 — PHP/HTML folder support + CI exports
- Treat PHP site folders as web targets when scanning local project paths.
- Scan `*.php` alongside HTML/JSX/TSX for common web accessibility issues.
- Improve iOS heuristics for Swift/SwiftUI/UIKit accessibility metadata.
- Add SARIF/CI-friendly export so findings can plug into code-review and CI pipelines.
- Expose MCP tools for SARIF export from a single project and from batched project audits.

### Phase 10 — Validation
- Add focused unit tests for auditor/storage/report generator/API behavior.
- Add tests for MCP-facing audit helpers where feasible.
- Run pytest for the new tests.

### Phase 11 — PR / CI Integration Layer
- Add `review_exporter.py` to produce GitHub/GitLab-friendly markdown:
  - `export_report_to_pr_markdown` — per-file grouped findings, executive summary, next steps, manual-check notice
  - `export_project_path_to_pr_markdown` — wrapper for local project paths
  - `export_many_projects_to_pr_markdown` — batch multi-project PR comment
- Add compact CI summary markdown:
  - `export_report_to_ci_summary` — top issues, score/grade, pass/warn/fail status
  - `export_project_path_to_ci_summary` — wrapper
  - `export_many_projects_to_ci_summary` — multi-project table for CI dashboards
- Expose four new MCP tools:
  - `export_project_path_pr_markdown`
  - `export_many_projects_pr_markdown`
  - `export_project_path_ci_summary`
  - `export_many_projects_ci_summary`
- Add tests for all review exporter variants.
- Update `health_check` tool list.
- `auditor.py`
- `project_auditor.py`
- `review_exporter.py`
- `mcp_server.py`
- `report_generator.py`
- `api.py`
- `bot_final.py`
- `web/index.html`
- `storage.py` (only if needed for metadata support)
- `tests/` new targeted tests
- `mcp_server.py`
- `schemas/`
- `README.md` and/or dedicated MCP docs
- `requirements.txt`
- `cli.py`
- `github-action/`

### Phase 12 — CLI Wrapper
- Add `cli.py` standalone CLI for running audits without MCP:
  - `audit <path>...` — local project(s) with auto-detection
  - `audit-url <url>` — public URL audit
  - `audit-html-file <path>` — single HTML file
  - `audit-html [html]` — raw HTML (or stdin)
- Support output formats: `json`, `sarif`, `pr-markdown`, `ci-summary`, `github-annotations`
- Support `--output`, `--quiet`, `--fail-threshold`, `--max-files`, `--max-findings`
- Exit codes: 0 = pass, 1 = fail (score below threshold or critical issues), 2 = usage error
- Add tests for CLI commands and exit codes.
- Update README.md with CLI examples.

### Phase 13 — GitHub Action + Inline Annotations
- Add GitHub Actions workflow-command annotations format:
  - `export_findings_to_github_annotations` — `::error/::warning/::notice` commands
  - Proper escaping of `%`, `\r`, `\n` per GitHub spec
  - Per-file, per-line annotations for PR diffs
- Add GitHub Action wrapper:
  - `github-action/action.yml` — action metadata
  - `github-action/Dockerfile` — self-contained container
  - `github-action/entrypoint.sh` — entrypoint script
- Update CLI to support `--format github-annotations`
- Add tests for annotation generation.
- Update README.md with workflow example.

## Risks / assumptions
- Existing saved audit JSON files may not contain new fields; renderers should tolerate missing keys.
- Telegram formatting must stay under message limits.
- HTML heuristics should remain honest: manual/runtime-only checks must be labeled as such.
- MCP server should be optional: if `mcp` SDK is missing, the core website/bot must still work.
- Static source analysis for mobile/desktop finds only a subset of real accessibility issues and must keep manual-check language explicit.

## Definition of done
- Website report is visibly more detailed than Telegram output.
- Bot returns a short readable summary plus web link.
- API accepts and persists public-audit flag.
- Auditor returns richer structure with more than the current 12 coarse checks.
- A local stdio MCP server exists for private company/local usage.
- MCP tools return structured findings using the normalized schema.
- Platform-aware local project audits work for major app stacks.
- Batch MCP tools support multi-project workflows.
- Tests pass for the modified core behavior.
