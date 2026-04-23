# MCP-friendly report schema notes

This service now emits a stable structured report shape intended to survive a future MCP/API extraction without breaking downstream consumers.

Primary schema file:
- schemas/accessibility-audit-report.schema.json

Key compatibility decisions:
- `findings` is the normalized list for MCP/API clients.
- `findings_by_severity` and `issues_by_category` remain for existing site/bot/report rendering.
- `mcp_payload` is a transport-friendly subset that mirrors what an MCP tool could return directly.
- `schema_version` and `schema_id` are included in every report.
- project/path audits use the same `findings` contract, with `platform`, `file_path`, `line`, `confidence`, and `requires_manual_check` fields where relevant.

Recommended future MCP tool contract:
- tool: `accessibility_audit`
- input:
  - `target` (URL initially)
  - optional `mode` (`quick` or `full`)
- output:
  - `mcp_payload`

Current local-first MCP tools:
- `audit_url`
- `audit_html_file`
- `audit_html`
- `detect_target_type`
- `audit_project_path`
- `detect_many_target_types`
- `audit_many_project_paths`
- `export_project_path_sarif`
- `export_many_projects_sarif`
- `get_audit_schema`

Why both top-level report and `mcp_payload` exist:
- top-level report keeps backwards compatibility for website/report rendering
- `mcp_payload` gives a cleaner tool-oriented contract for future MCP exposure
